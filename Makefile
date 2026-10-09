test:
	python -m pytest --cov=onebar --cov-report=term-missing

test-live:
	ONEBAR_LIVE=1 python -m pytest

data:
	python scripts/build_dataset.py locations
	python scripts/build_dataset.py situations
	python scripts/build_dataset.py paraphrase
	python scripts/build_dataset.py teacher
	python scripts/build_dataset.py assemble

eval:
	python eval/run_eval.py --system template
	python eval/run_eval.py --system base
	python eval/run_eval.py --system large
	python eval/table.py

train:
	python train/sft.py --dry-run
	python train/sft.py
