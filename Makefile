.PHONY: help install install-ml install-dev install-demo dev demo-models demo-api frontend test lint format eval docker-build docker-smoke clean

help:
	@echo "make install       core dependencies (offline-capable)"
	@echo "make install-ml    add OpenAI client and local-model libraries"
	@echo "make install-dev   add test and lint tooling"
	@echo "make dev           run the API on http://127.0.0.1:8000 (lexical only, no auth)"
	@echo "make install-demo  core plus fastembed (ONNX embeddings) for the demo configuration"
	@echo "make demo-models   download the ONNX MiniLM model into data/models/fastembed (once)"
	@echo "make demo-api      run the API exactly as the public demo does (needs API_KEY)"
	@echo "make frontend      run the Next.js demo frontend on http://localhost:3000"
	@echo "make test          run the test suite"
	@echo "make lint          black/isort/flake8/mypy/bandit checks"
	@echo "make publication-check  scan tracked public text for prohibited coaching material"
	@echo "make format        apply black and isort"
	@echo "make eval          offline evaluation run (lexical, no key)"
	@echo "make docker-build  build the runtime image"
	@echo "make docker-smoke  build then ingest/search inside a container"

install:
	pip install -r requirements.txt

install-ml:
	pip install -r requirements-ml.txt

install-dev:
	pip install -r requirements-dev.txt

dev:
	uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

install-demo:
	pip install -r requirements-demo.txt

demo-models:
	python scripts/setup/init_models.py --fastembed --fastembed-cache-dir ./data/models/fastembed

# Same settings as the Hugging Face Space (deploy/space/demo.env) with local
# paths. API_KEY must be set in the environment (16+ characters).
demo-api:
	APP_ENV_FILE=deploy/space/demo.env DATA_DIR=./data/demo \
	FASTEMBED_CACHE_DIR=./data/models/fastembed DEMO_SEED_DIR=./data/samples \
	HF_HUB_OFFLINE=1 uvicorn src.api.main:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm install && npm run dev

test:
	pytest tests -q

lint:
	black --check src tests eval
	isort --check-only src tests eval
	flake8 src tests eval
	mypy src
	bandit -r src -ll -q

publication-check:
	python scripts/check_publication.py

format:
	black src tests eval
	isort src tests eval

eval:
	python -m eval.run_eval --embedding none

docker-build:
	docker build -f docker/Dockerfile --target runtime -t doc-intel:local .

docker-smoke: docker-build
	bash scripts/docker/smoke_test.sh doc-intel:local

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage
