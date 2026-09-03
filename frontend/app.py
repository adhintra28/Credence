"""Production portal (Flask) — bank console + customer self-service.

Run: python frontend/app.py -> http://127.0.0.1:5000
Logins: bank@bank.com/bank123 (analyst) | risk@bank.com/risk123 (manager) |
        customer@customer.com/cust123 (demo C000000)

Pages:
  Bank: /bank (portfolio) | /bank/queue | /bank/customer/<id> (360) |
        /bank/model (health+fairness) | /bank/interventions
  Customer: /customer (score, reasons, offers, history)
JSON API for integrations: FastAPI at src/serving/api.py (:8000).
"""
import functools
import os
import sys
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import logging as _logging
    _logging.getLogger("dotenv.main").setLevel(_logging.CRITICAL)  # don't spam parse warnings
    from dotenv import load_dotenv
    load_dotenv()  # local dev: read .env if present (never required in production)
except Exception:
    pass

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth

from src.services import store, risk_service, intervention_service, model_service

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("PREDELINQ_SECRET", "predelinq-prod-change-me")
app.config["SESSION_PERMANENT"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True  # live template edits without restart

# Behind Render/Railway proxies the app sees http; trust X-Forwarded-Proto so
# url_for(_external=True) yields https for the OAuth redirect.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# --- Google SSO ---
def google_redirect_uri():
    """Exact callback URL Google redirects to. OAUTH_REDIRECT_URI wins because
    the console registration must match byte-for-byte; otherwise derive the
    host from the request (ProxyFix keeps https behind Render/Railway)."""
    uri = os.environ.get("OAUTH_REDIRECT_URI")
    if uri:
        return uri
    return url_for("auth_callback", _external=True)

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


def load_banks():
    """Load bank name -> domain mapping from banks.yaml."""
    bank_list = {}
    banks_yaml = os.path.join(os.path.dirname(__file__), "banks.yaml")
    try:
        with open(banks_yaml, "r") as f:
            data = yaml.safe_load(f)
            for region, banks in data.items():
                if banks:
                    for bank_id, domain in banks.items():
                        name = bank_id.replace("_", " ").title()
                        bank_list[bank_id] = {"name": name, "domain": domain}
    except Exception as e:
        print(f"Warning: could not load banks.yaml: {e}")
    return bank_list


BANKS = load_banks()

USERS = {
    "bank@bank.com": {"pw": generate_password_hash("bank123", method="pbkdf2:sha256"), "role": "bank", "name": "Collections Analyst"},
    "risk@bank.com": {"pw": generate_password_hash("risk123", method="pbkdf2:sha256"), "role": "risk", "name": "Risk Manager"},
    "customer@customer.com": {"pw": generate_password_hash("cust123", method="pbkdf2:sha256"), "role": "customer",
                              "name": "Demo Customer", "customer_id": "C000000"},
}


def login_required(*roles):
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **k):
            if "role" not in session:
                return redirect(url_for("login"))
            if roles and session["role"] not in roles:
                # customers stay on /customer, staff on /bank
                return redirect(url_for("customer") if session["role"] == "customer" else url_for("bank"))
            return fn(*a, **k)
        return wrap
    return deco


@app.context_processor
def inject_sidebar_counts():
    """Sidebar badges + topbar cycle info, tolerant of missing data."""
    try:
        s = risk_service.portfolio_summary()
        return {"sidebar_counts": {"alerts": s.get("alerts", 0), "red": s.get("red", 0),
                                   "scoring_date": s.get("scoring_date", "")}}
    except Exception:
        return {"sidebar_counts": {}}


@app.route("/", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        u = USERS.get(email)
        if u and check_password_hash(u["pw"], pw):
            session.clear()
            session.update({"role": u["role"], "email": email, "name": u.get("name", email),
                            "cid": u.get("customer_id", "")})
            # allow demo customer-id override: customer@C000123? keep simple via form field
            cid_override = request.form.get("customer_id", "").strip()
            if u["role"] == "customer" and cid_override:
                session["cid"] = cid_override
            if session["role"] == "customer":
                return redirect(url_for("customer"))
            return redirect(url_for("bank"))
        err = "Invalid credentials. Try bank@bank.com / bank123, risk@bank.com / risk123, customer@customer.com / cust123."
    return render_template("login.html", err=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- Google SSO ----------------
@app.route("/login/bank", methods=["GET", "POST"])
def login_bank():
    """Bank employee selects their institution, then goes to Google SSO."""
    if request.method == "POST":
        session["sso_role"] = "bank"
        session["selected_bank"] = request.form.get("bank_id")
        return redirect(url_for("google_auth"))
    return render_template("bank_login.html", banks=BANKS)


@app.route("/login/customer", methods=["GET", "POST"])
def login_customer():
    """Customer selects their bank to link (Paytm/UPI style), then Google SSO."""
    if request.method == "POST":
        session["sso_role"] = "customer"
        session["selected_bank"] = request.form.get("bank_id")
        return redirect(url_for("google_auth"))
    return render_template("customer_login.html", banks=BANKS)


@app.route("/auth/google")
def google_auth():
    if not (google.client_id and google.client_secret):
        return render_template("error.html",
            msg="Google SSO is not configured. Set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET (see docs/SSO_SETUP.md). The password "
                "logins keep working without them.")
    return google.authorize_redirect(google_redirect_uri())


@app.route("/auth/callback")
def auth_callback():
    try:
        token = google.authorize_access_token()
    except Exception as e:
        # consent denied, expired state, or token exchange failure
        return render_template("error.html",
            msg="Sign-in did not complete (cancelled or timed out). Please try again.")
    # Google only stamps token["userinfo"] when a nonce was sent; fetch it
    # explicitly from the userinfo endpoint with the access token instead.
    try:
        import requests as _req
        resp = _req.get("https://openidconnect.googleapis.com/v1/userinfo",
                        headers={"Authorization": f"Bearer {token.get('access_token', '')}"},
                        timeout=10)
        user_info = resp.json()
    except Exception:
        user_info = token.get("userinfo") or {}
    if not user_info or not user_info.get("email"):
        return render_template("error.html",
            msg="Could not read your Google profile. Please try logging in again.")

    email = user_info.get("email", "").lower()
    name = user_info.get("name", email)
    sso_role = session.get("sso_role")
    bank_id = session.get("selected_bank")

    if not sso_role or not bank_id or bank_id not in BANKS:
        return render_template("error.html",
            msg="Invalid session state. Please try logging in again.")

    bank_info = BANKS[bank_id]

    if sso_role == "bank":
        # Strict domain validation for bank employees
        if not email.endswith(bank_info["domain"]):
            return render_template("error.html",
                msg=f"Unauthorized: Your email ({email}) must end with "
                    f"'{bank_info['domain']}' to access {bank_info['name']} portal.")
        session.clear()
        session.update({"role": "bank", "email": email, "name": name,
                        "bank": bank_info["name"]})
        return redirect(url_for("bank"))

    elif sso_role == "customer":
        # Any Google email is accepted for customers
        session.clear()
        session.update({"role": "customer", "email": email, "name": name,
                        "cid": "C000000", "bank": bank_info["name"]})
        return redirect(url_for("customer"))

    return redirect(url_for("login"))


# ---------------- bank ----------------
@app.route("/bank")
@login_required("bank", "risk")
def bank():
    summary = risk_service.portfolio_summary()
    scores, sd = store.get_scores()
    mix = summary.get("mix", {})
    # tier trend: red/amber share + top reasons
    top_alerts, _ = intervention_service.queue_with_actions(limit=10)
    signals = risk_service.signal_distribution(sd)
    health = model_service.model_health(sd)
    stats = intervention_service.acceptance_stats()
    return render_template("bank.html", summary=summary, mix=mix, top_alerts=top_alerts,
                           scoring_date=sd, role=session.get("role"), signals=signals,
                           health=health, stats=stats)


@app.route("/bank/queue", methods=["GET", "POST"])
@login_required("bank", "risk")
def queue():
    msg = None
    if request.method == "POST":
        cid = request.form.get("customer_id", "")
        action = request.form.get("action", "")
        note = request.form.get("note", "")
        if cid and action:
            out = intervention_service.analyst_action(cid, action, None, session.get("email", ""), note)
            msg = out.get("error", f"{action} recorded for {cid}") if isinstance(out, dict) and "error" in out else f"{action} recorded for {cid}"
    tier = request.args.get("tier") or None
    view = request.args.get("view", "open")
    q = request.args.get("q", "")
    recs, sd = intervention_service.queue_with_actions(None, tier, view, 200)
    if q:
        ql = q.lower()
        recs = [r for r in recs if ql in str(r.get("customer_id", "")).lower()
                or ql in str(r.get("top_reason", "")).lower()]
    return render_template("queue.html", alerts=recs, scoring_date=sd, msg=msg,
                           tier=tier or "", view=view, q=q)


@app.route("/bank/customer/<cid>", methods=["GET", "POST"])
@login_required("bank", "risk")
def customer360(cid):
    msg = None
    if request.method == "POST":
        offer = request.form.get("offer", "")
        channel = request.form.get("channel", "call")
        if offer:
            out = intervention_service.create_offer(cid, offer, channel, session.get("email", ""))
            msg = out.get("error", f"Offer '{offer}' recorded for {cid}") if isinstance(out, dict) and "error" in out else f"Offer recorded for {cid}"
    ctx = risk_service.customer_360(cid)
    return render_template("customer360.html", cid=cid, ctx=ctx, msg=msg,
                           offers=intervention_service.OFFER_CHOICES)


@app.route("/bank/model")
@login_required("bank", "risk")
def model_health():
    return render_template("model.html", health=model_service.model_health(),
                           fairness=model_service.fairness_audit(),
                           thresholds=store.get_thresholds())


@app.route("/bank/interventions")
@login_required("bank", "risk")
def interventions():
    status = request.args.get("status") or None
    rows = intervention_service.list_interventions(None, status, 200)
    return render_template("interventions.html", rows=rows,
                           stats=intervention_service.acceptance_stats(), status=status or "")


# ---------------- customer ----------------
@app.route("/customer", methods=["GET", "POST"])
@login_required("customer")
def customer():
    cid = session.get("cid", "C000000")
    msg = None
    if request.method == "POST":
        decision = request.form.get("decision", "")
        offer = request.form.get("offer", "")
        if decision in ("accepted", "declined", "accept", "decline"):
            out = intervention_service.respond_to_offer(cid, decision, cid)
            msg = out.get("error", f"Response '{decision}' recorded. Our team will confirm before your EMI date.") \
                if isinstance(out, dict) and "error" in out else \
                f"Thank you — '{decision}' recorded. Our team will confirm before your EMI date. No late fee for this request."
        elif offer:
            out = intervention_service.create_offer(cid, offer, "app", cid)
            msg = out.get("error", f"Request received: {offer}. Our team will confirm.") \
                if isinstance(out, dict) and "error" in out else \
                f"Request received: {offer}. Our team will confirm before your EMI date. No late fee for this request."
    ctx = risk_service.customer_360(cid)
    return render_template("customer.html", cid=cid, ctx=ctx, msg=msg,
                           offers=intervention_service.OFFER_CHOICES)


@app.route("/healthz")
def healthz():
    s, sd = store.get_scores()
    return {"status": "ok", "scoring_date": sd, "n_scores": len(s)}


@app.route("/__live")
def live_hash():
    """Live-reload signal: hash of template/app mtimes + git HEAD.

    The dashboard polls this every 2s and reloads when the hash changes, so
    UI edits (and commits) appear without a manual refresh. No-op for CI/tests.
    """
    import hashlib
    h = hashlib.sha256()
    base = os.path.join(os.path.dirname(__file__), "templates")
    try:
        for root, _, files in os.walk(base):
            for f in sorted(files):
                p = os.path.join(root, f)
                h.update(f"{p}:{os.path.getmtime(p)}".encode())
        h.update(f"{os.path.getmtime(__file__)}".encode())
        head = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".git", "HEAD"), "rb").read()
        h.update(head)
    except Exception:
        pass
    return {"hash": h.hexdigest()[:16]}


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", "5000")))
