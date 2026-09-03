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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from src.services import store, risk_service, intervention_service, model_service

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("PREDELINQ_SECRET", "predelinq-prod-change-me")
app.config["SESSION_PERMANENT"] = False

USERS = {
    "bank@bank.com": {"pw": generate_password_hash("bank123"), "role": "bank", "name": "Collections Analyst"},
    "risk@bank.com": {"pw": generate_password_hash("risk123"), "role": "risk", "name": "Risk Manager"},
    "customer@customer.com": {"pw": generate_password_hash("cust123"), "role": "customer",
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


# ---------------- bank ----------------
@app.route("/bank")
@login_required("bank", "risk")
def bank():
    summary = risk_service.portfolio_summary()
    scores, sd = store.get_scores()
    mix = summary.get("mix", {})
    # tier trend: red/amber share + top reasons
    top_alerts, _ = intervention_service.queue_with_actions(limit=10)
    return render_template("bank.html", summary=summary, mix=mix, top_alerts=top_alerts,
                           scoring_date=sd, role=session.get("role"))


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
