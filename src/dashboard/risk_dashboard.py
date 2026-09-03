"""Risk dashboard (Plotly + Dash) — 4-tab analytical console per PRD FR-7.

Run: python -m src.dashboard.risk_dashboard -> http://127.0.0.1:8050
Tabs: Portfolio | Customer 360 | Alerts queue | Model health
Operational portal (login/offers/approve) lives in frontend/app.py (:5000);
machine API lives in src/serving/api.py (:8000).
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, dash_table

from src.services import store, risk_service, model_service

app = Dash(__name__)
app.title = "Pre-Delinquency Risk Dashboard"


def build_portfolio():
    summary = risk_service.portfolio_summary()
    scores, sd = store.get_scores()
    if len(scores) == 0:
        return html.P("No scores yet — run python run_all.py")
    donut = dcc.Graph(figure=px.pie(scores, names="tier", title=f"Risk mix ({sd}, n={len(scores)})",
                                    color="tier", color_discrete_map={"Green": "green", "Amber": "orange", "Red": "red"}))
    hist = dcc.Graph(figure=px.histogram(scores, x="score", color="tier", nbins=30,
                                         title=f"Score distribution (flagged {summary.get('flagged_rate',0):.1%}, thresholds {store.get_thresholds()})"))
    # flagged-vs-DPD lift proxy: precision by tier using labels
    labels = store.get_labels()
    lift_fig = {}
    if len(labels):
        lab = labels.set_index("customer_id")["label_28d"].to_dict()
        rows = []
        for tier in ("Green", "Amber", "Red"):
            ids = scores[scores["tier"] == tier]["customer_id"]
            rate = float(pd.Series([lab.get(c, 0) for c in ids]).mean()) if len(ids) else 0.0
            rows.append({"tier": tier, "default_rate": rate, "n": len(ids)})
        lift = pd.DataFrame(rows)
        lift_fig = dcc.Graph(figure=px.bar(lift, x="tier", y="default_rate", text="n",
                                           title="Flagged-vs-DPD lift: 28d default rate by tier (proxy)"))
    # PR curve proxy
    pr_fig = {}
    try:
        from sklearn.metrics import precision_recall_curve
        lab = labels.set_index("customer_id")["label_28d"].to_dict()
        y = [int(lab.get(c, 0)) for c in scores["customer_id"]]
        p = scores["score"].values
        if len(set(y)) > 1:
            prec, rec, _ = precision_recall_curve(y, p)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=rec, y=prec, mode="lines", name="PR"))
            fig.update_layout(title="PR curve (labels join proxy)", xaxis_title="recall", yaxis_title="precision")
            pr_fig = dcc.Graph(figure=fig)
    except Exception:
        pass
    return html.Div([
        html.P(f"scored {summary.get('n')} · Red {summary.get('red')} · Amber {summary.get('amber')} · "
               f"expected loss Rs.{summary.get('expected_loss_total','-')} · base default {summary.get('base_default_rate','-')}"),
        donut, hist, lift_fig, pr_fig])


def layout():
    scores, sd = store.get_scores()
    cust_opts = [{"label": c, "value": c} for c in (scores["customer_id"].head(200).tolist() if len(scores) else [])]
    health = model_service.model_health()
    fair = model_service.fairness_audit()
    alerts, _ = store.get_alerts()
    return html.Div([
        html.H2("Pre-Delinquency Risk Dashboard"),
        html.P(f"Source: {sd} | customers={len(scores)} alerts={len(alerts)} | portal :5000 · api :8000/docs"),
        dcc.Tabs([
            dcc.Tab(label="Portfolio", children=[build_portfolio()]),
            dcc.Tab(label="Customer 360", children=[
                html.Div([dcc.Dropdown(id="c360-id", options=cust_opts, placeholder="Search customer_id e.g. C000010"),
                          html.Div(id="c360-out")])]),
            dcc.Tab(label="Alerts queue", children=[
                html.Div([dash_table.DataTable(
                    id="queue-table",
                    columns=[{"name": c, "id": c} for c in
                             (["customer_id", "tier", "score", "top_reason", "emi_amount", "expected_loss", "action"]
                              if len(alerts) else ["note"])],
                    data=alerts.head(200).to_dict("records") if len(alerts) else [],
                    filter_action="native", sort_action="native", page_size=20,
                    export_format="csv"),
                    html.P("CSV export built-in · Approve/Snooze in portal /bank/queue or POST /api/alerts/{id}/action")])]),
            dcc.Tab(label="Model health", children=[
                html.Pre(json.dumps({k: v for k, v in health.items() if k != "global_shap"}, indent=2)[:4000]),
                html.H4("Fairness (80% rule)"),
                html.Pre(json.dumps(fair, indent=2)[:4000]),
            ]),
        ]),
    ])


app.layout = layout()


@app.callback(Output("c360-out", "children"), Input("c360-id", "value"))
def render_360(cid):
    if not cid:
        return html.P("Pick a customer.")
    ctx = risk_service.customer_360(cid)
    s, feats, tl = ctx["score"], ctx["features"], ctx["timeline"]
    figs = []
    if tl.get("balance"):
        b = pd.DataFrame(tl["balance"])
        fig = px.line(b, x="t", y="balance", title=f"{cid} balance (120d) + salary markers")
        for m in tl.get("salary_markers", []):
            fig.add_vline(x=m["t"], line_dash="dash", annotation_text=f"salary {m['amount']:.0f}")
        figs.append(dcc.Graph(figure=fig))
    if tl.get("utility"):
        u = pd.DataFrame(tl["utility"])
        figs.append(dcc.Graph(figure=px.scatter(u, x="t", y="day", size="amount", title="Utility timing strip (day-of-month)")))
    # SHAP waterfall proxy: top feature magnitudes as bar
    if feats:
        items = sorted([(k, abs(float(v))) for k, v in feats.items()
                        if isinstance(v, (int, float)) and k not in ("tenure_months",)], key=lambda x: -x[1])[:8]
        figs.append(dcc.Graph(figure=px.bar(pd.DataFrame(items, columns=["feature", "abs_value"]),
                                            x="abs_value", y="feature", orientation="h", title="Top signal magnitudes (SHAP proxy)")))
    emi_tbl = dash_table.DataTable(columns=[{"name": c, "id": c} for c in
                                            (["due_date", "amount_due", "amount_paid", "dpd_days", "bounce_flag"]
                                             if ctx["emi"] else ["note"])],
                                   data=[{k: str(v) for k, v in e.items()} for e in ctx["emi"][:12]] or [{"note": "no emi"}])
    reasons = ", ".join(s.get("reasons_list", [])) if s else "no score"
    return html.Div([html.H4(f"{cid}: {s.get('tier','-')} {s.get('score','-')} — {reasons}")] + figs +
                    [html.H4("EMI schedule"), emi_tbl,
                     html.P("Offers: use portal /bank/customer/{} or POST /api/interventions".format(cid))])


if __name__ == "__main__":
    app.run(debug=True, port=8050)
