"""One-command batch pipeline: generate -> features -> train -> score -> policy.
Usage: python run_all.py [--skip-generate] [--config config.yaml]
"""
import argparse
import subprocess
import sys
import yaml

STEPS = [
    ("generate", [sys.executable, "-m", "src.generator.generate", "--config", "{cfg}"]),
    ("train", [sys.executable, "-m", "src.models.train", "--config", "{cfg}"]),
    ("score", [sys.executable, "-m", "src.scoring.score", "--scoring-date", "{sd}", "--config", "{cfg}"]),
    ("policy", [sys.executable, "-m", "src.policy.engine", "--scoring-date", "{sd}", "--config", "{cfg}"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--skip-generate", action="store_true")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    sd = cfg["scoring"]["scoring_date"]
    for name, cmd in STEPS:
        if name == "generate" and a.skip_generate:
            print("-- skip generate"); continue
        cmd = [c.format(cfg=a.config, sd=sd) for c in cmd]
        print(f"\n===== {name}: {' '.join(cmd)} =====")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            sys.exit(r.returncode)
    print("\nDONE. Outputs in data/outputs/. Frontend: python frontend/app.py | Dash: python -m src.dashboard.risk_dashboard")


if __name__ == "__main__":
    main()
