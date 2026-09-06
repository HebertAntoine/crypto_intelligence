# Crypto Intelligence - outil personnel d'analyse. N'execute aucun ordre.

PY := .venv/bin/python
PIP := .venv/bin/pip
RUFF := .venv/bin/ruff
PYTEST := .venv/bin/pytest
NODE_BIN := $(HOME)/.local/opt/node22/bin
export PYTHONPATH := backend

.DEFAULT_GOAL := help
.PHONY: help install install-backend install-frontend init-db serve dev frontend \
        collect analyze report ingest import-etf evaluate providers \
        test lint typecheck check clean mock stop \
        backfill research daily scheduler coverage \
        research-export audit import-oi

help:  ## Affiche cette aide
	@echo "Crypto Intelligence - commandes disponibles"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Demarrage rapide :  make install && make backfill && make serve"
	@echo "                    puis, dans un autre terminal :  make frontend"

install: install-backend install-frontend init-db  ## Installe tout (backend + frontend + base)

install-backend:  ## Cree le venv et installe les dependances Python
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[dev]"
	@echo "Backend installe."

install-frontend:  ## Installe les dependances du frontend
	@if [ -x "$(NODE_BIN)/npm" ]; then \
	  cd frontend && PATH="$(NODE_BIN):$$PATH" npm install --no-fund --no-audit; \
	else \
	  cd frontend && npm install --no-fund --no-audit; \
	fi
	@echo "Frontend installe."

init-db:  ## Cree les tables de la base
	$(PY) -m crypto_intel.cli init-db

serve:  ## Lance l'API backend (http://127.0.0.1:8100)
	$(PY) -m crypto_intel.cli serve

dev:  ## Lance l'API en mode rechargement automatique
	$(PY) -m crypto_intel.cli serve --reload

frontend:  ## Lance le frontend (http://localhost:5273)
	@if [ -x "$(NODE_BIN)/npm" ]; then \
	  cd frontend && PATH="$(NODE_BIN):$$PATH" npm run dev; \
	else \
	  cd frontend && npm run dev; \
	fi

mock:  ## Lance l'API en MOCK_MODE (aucun reseau, aucune cle)
	MOCK_MODE=true $(PY) -m crypto_intel.cli serve

collect:  ## Collecte et stocke les donnees (option: ASSET=BTC)
	$(PY) -m crypto_intel.cli collect $(if $(ASSET),--asset $(ASSET))

analyze:  ## Analyse complete en console (option: ASSET=BTC)
	$(PY) -m crypto_intel.cli analyze $(if $(ASSET),--asset $(ASSET))

report:  ## Genere le rapport texte (options: ASSET=BTC OUT=rapport.txt)
	$(PY) -m crypto_intel.cli report $(if $(ASSET),--asset $(ASSET)) $(if $(OUT),--out $(OUT))

ingest:  ## Ingere les documents de knowledge/ (cours, PDF, notes)
	$(PY) -m crypto_intel.cli ingest-knowledge

import-etf:  ## Importe les flux ETF depuis un CSV (FILE=chemin.csv, sinon tout le dossier)
	$(PY) -m crypto_intel.cli import-etf $(if $(FILE),--file $(FILE))

evaluate:  ## Evalue les rapports passes face aux prix reellement observes
	$(PY) -m crypto_intel.cli evaluate

backfill:  ## Importe l'historique (idempotent). Options: ASSET=BTC TF=1d DAYS=3600
	$(PY) -m crypto_intel.cli backfill $(if $(ASSET),--asset $(ASSET)) $(if $(TF),--timeframe $(TF)) $(if $(DAYS),--days $(DAYS))

research:  ## Lance toutes les etudes (ETF, events, regimes, features, calibration)
	$(PY) -m crypto_intel.cli research $(if $(ASSET),--asset $(ASSET)) $(if $(OUT),--out $(OUT))

research-quick:  ## Etudes rapides seulement (sans walk-forward ni feature importance)
	$(PY) -m crypto_intel.cli research --quick $(if $(ASSET),--asset $(ASSET))

research-export:  ## Lance les etudes et exporte CSV + JSON + Markdown
	$(PY) -m crypto_intel.cli research-export $(if $(ASSET),--asset $(ASSET)) $(if $(OUT),--out $(OUT))

audit:  ## Audite chaque score face aux rendements futurs (verdicts par actif)
	$(PY) -m crypto_intel.cli audit $(if $(ASSET),--asset $(ASSET)) $(if $(OUT),--out $(OUT))

import-oi:  ## Importe l'historique d'open interest depuis data/imports/open_interest/
	$(PY) -m crypto_intel.cli import-oi $(if $(PATH_),--path $(PATH_))

daily:  ## Genere le rapport quotidien global (option: OUT=daily.txt)
	$(PY) -m crypto_intel.cli daily $(if $(OUT),--out $(OUT))

scheduler:  ## Lance le scheduler au premier plan (Ctrl+C pour arreter)
	$(PY) -m crypto_intel.cli scheduler

coverage:  ## Affiche la profondeur historique disponible par donnee
	$(PY) -m crypto_intel.cli coverage

providers:  ## Affiche l'etat de chaque source de donnees
	$(PY) -m crypto_intel.cli providers

test:  ## Lance les tests (hors ligne, sans cle API)
	$(PYTEST) -q

test-verbose:  ## Lance les tests en mode detaille
	$(PYTEST) -v

lint:  ## Verifie le style et corrige ce qui peut l'etre
	$(RUFF) check backend tests --fix
	$(RUFF) check backend tests

typecheck:  ## Verifie les types du frontend
	@if [ -x "$(NODE_BIN)/npx" ]; then \
	  cd frontend && PATH="$(NODE_BIN):$$PATH" npx tsc --noEmit; \
	else \
	  cd frontend && npx tsc --noEmit; \
	fi

check: lint test typecheck  ## Lint + tests + typecheck

build-frontend:  ## Build de production du frontend
	@if [ -x "$(NODE_BIN)/npm" ]; then \
	  cd frontend && PATH="$(NODE_BIN):$$PATH" npm run build; \
	else \
	  cd frontend && npm run build; \
	fi

stop:  ## Arrete le backend qui ecoute sur le port 8100
	@PID=$$(ss -lptn 'sport = :8100' 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1); \
	if [ -n "$$PID" ]; then kill $$PID && echo "backend arrete ($$PID)"; else echo "aucun backend sur le port 8100"; fi

clean:  ## Supprime les caches (conserve la base et tes documents)
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache data/cache
	@echo "Caches supprimes. La base de donnees et knowledge/ sont intacts."
