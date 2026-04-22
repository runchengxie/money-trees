DATA ?= data_small.parquet
OUTPUT ?= artifacts/template-smoke
SMOKE_CONFIGS = \
	--config configs/market/us.yaml \
	--config configs/model/rf.yaml \
	--config configs/backtest/smoke.yaml

.PHONY: install test smoke convert

install:
	uv sync --dev

test:
	uv run pytest -q

smoke:
	uv run treealpha-backtest $(SMOKE_CONFIGS) --data $(DATA) --output-dir $(OUTPUT)

convert:
	uv run python scripts/convert_pickle_to_parquet.py --input $(INPUT)
