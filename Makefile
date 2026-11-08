PY ?= python
export JRR_ROOT := $(CURDIR)
export JRR_DUCKDB := $(CURDIR)/data/warehouse/jrr.duckdb
export PYTHONPATH := $(CURDIR)/src

.PHONY: install snapshot pipeline dbt test lint dashboard terraform-validate docker ci

install:
	$(PY) -m pip install -r requirements.txt

snapshot:
	$(PY) -m jrr.build_snapshot --download

pipeline:
	$(PY) -m jrr.pipeline

dbt:
	dbt build --project-dir dbt_project --profiles-dir dbt_project

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check src tests feast_repo

terraform-validate:
	terraform -chdir=infra/terraform fmt -check
	terraform -chdir=infra/terraform init -backend=false
	terraform -chdir=infra/terraform validate

docker:
	docker build -t jobs-risk-radar:local .

ci: lint pipeline test terraform-validate
