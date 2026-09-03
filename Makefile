.PHONY: install venv lint test data train score serve portal all clean

# Repo interpreter: `python` may not exist on macOS — default to the venv.
# Override anytime: make portal PYTHON=python3
PYTHON ?= .venv/bin/python
CONFIG ?= config.yaml

venv:
	python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt

install:
	$(PYTHON) -m pip install -r requirements.txt

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m black --check src/ tests/

format:
	$(PYTHON) -m ruff check --fix src/ tests/
	$(PYTHON) -m black src/ tests/

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

data:
	$(PYTHON) -m src.generator.generate --config $(CONFIG)

features:
	$(PYTHON) -m src.features.build --scoring-date $$($(PYTHON) -c "import yaml; print(yaml.safe_load(open('$(CONFIG)'))['scoring']['scoring_date'])") --config $(CONFIG)

train:
	$(PYTHON) -m src.models.train --config $(CONFIG)

score:
	$(PYTHON) -m src.scoring.score --scoring-date $$($(PYTHON) -c "import yaml; print(yaml.safe_load(open('$(CONFIG)'))['scoring']['scoring_date'])") --config $(CONFIG)

policy:
	$(PYTHON) -m src.policy.engine --scoring-date $$($(PYTHON) -c "import yaml; print(yaml.safe_load(open('$(CONFIG)'))['scoring']['scoring_date'])") --config $(CONFIG)

serve:
	uvicorn src.serving.api:app --host 0.0.0.0 --port 8000 --reload

portal:
	$(PYTHON) frontend/app.py

all: data features train score policy
	@echo "Pipeline complete. Outputs in data/outputs/"

clean:
	rm -rf data/raw data/processed data/outputs models/*.pkl models/*.json models/global_shap.csv
	@echo "Cleaned all generated data and model artifacts."
