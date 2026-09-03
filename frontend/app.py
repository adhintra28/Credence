"""Frontend (BASIC, separate from risk dashboard) — role login -> redirect.
Bank page: portfolio table + alerts. Customer page: my score, reasons, offers.
Run: python frontend/app.py  -> http://127.0.0.1:5000
Login: bank@bank.com / bank123  |  customer@customer.com / cust123 (uses C000000)
Full styling later; logic kept intentionally simple per request.
"""
import os
import glob
import json
import pandas as pd
from flask import Flask, request, redirect, session, render_template

app = Flask(__name__, template_folder="templates")
app.secret_key = "predelinq-dev-only"

USERS = {
    "bank@bank.com": {"pw": "bank123", "role": "bank"},
    "customer@customer.com": {"pw": "cust123", "role": "customer", "customer_id": "C000000"},
}


def latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


@app.route("/", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        u = USERS.get(request.form.get("email", ""))
        if u and u["pw"] == request.form.get("password", ""):
            session.update({"role": u["role"], "cid": u.get("customer_id", "")})
            return redirect("/bank" if u["role"] == "bank" else "/customer")
        err = "Invalid credentials. Try bank@bank.com / bank123 or customer@customer.com / cust123."
    return render_template("login.html", err=err)


@app.route("/bank")
def bank():
    if session.get("role") != "bank":
        return redirect("/")
    f = latest("data/outputs/risk_scores_*.csv")
    a = latest("data/outputs/alerts_*.csv")
    scores = pd.read_csv(f) if f and os.path.exists(f) else pd.DataFrame()
    alerts = pd.read_csv(a) if a and os.path.exists(a) else pd.DataFrame()
    mix = scores["tier"].value_counts().to_dict() if len(scores) else {}
    return render_template("bank.html", mix=mix, alerts=alerts.head(50).to_dict("records") if len(alerts) else [],
                           n=len(scores), src=os.path.basename(f) if f else "no scores yet — run pipeline")


@app.route("/customer", methods=["GET", "POST"])
def customer():
    if session.get("role") != "customer":
        return redirect("/")
    cid = session.get("cid", "C000000")
    msg = None
    if request.method == "POST":
        choice = request.form.get("offer", "payment-holiday")
        os.makedirs("data/outputs", exist_ok=True)
        with open("data/outputs/intervention_log.csv", "a") as fh:
            if os.path.getsize("data/outputs/intervention_log.csv") == 0 if os.path.exists("data/outputs/intervention_log.csv") else True:
                fh.write("customer_id,date,offer,channel\n")
            import datetime
            fh.write(f"{cid},{datetime.date.today().isoformat()},{choice},app\n")
        msg = f"Request received: {choice}. Our team will confirm before your EMI date. No late fee for this request."
    f = latest("data/outputs/risk_scores_*.csv")
    row = {}
    if f and os.path.exists(f):
        df = pd.read_csv(f)
        hit = df[df["customer_id"] == cid]
        if len(hit):
            row = hit.iloc[0].to_dict()
            try:
                row["reasons"] = json.loads(row.get("reasons", "[]"))
            except Exception:
                row["reasons"] = []
    return render_template("customer.html", cid=cid, row=row, msg=msg)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
