"""Risk dashboard (Visualization stack: Plotly + Dash) — bank analytics view.
Run: python -m src.dashboard.risk_dashboard  -> http://127.0.0.1:8050
Separate from frontend/ (basic login portal). This is the analytical console.
"""
import glob
import os
import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html

app = Dash(__name__)
app.title = "Pre-Delinquency Risk Dashboard"


def latest(pattern):
    fs = sorted(glob.glob(pattern))
    return fs[-1] if fs else None


def load():
    f = latest("data/outputs/risk_scores_*.csv")
    a = latest("data/outputs/alerts_*.csv")
    return (pd.read_csv(f) if f and os.path.exists(f) else pd.DataFrame(),
            pd.read_csv(a) if a and os.path.exists(a) else pd.DataFrame(),
            os.path.basename(f) if f else "no data — run pipeline")


scores, alerts, src = load()
tier_fig = px.pie(scores, names="tier", title=f"Risk mix ({src})",
                  color="tier", color_discrete_map={"Green": "green", "Amber": "orange", "Red": "red"}) if len(scores) else {}
hist_fig = px.histogram(scores, x="score", color="tier", nbins=30, title="Score distribution") if len(scores) else {}

app.layout = html.Div([
    html.H2("Pre-Delinquency Risk Dashboard"),
    html.P(f"Source: {src} | customers={len(scores)} alerts={len(alerts)}"),
    dcc.Graph(figure=tier_fig), dcc.Graph(figure=hist_fig),
    html.H3("Top alerts"),
    html.Pre(alerts.head(20).to_string() if len(alerts) else "no alerts yet"),
])

if __name__ == "__main__":
    app.run(debug=True, port=8050)
