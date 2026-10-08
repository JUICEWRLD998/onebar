test:
	python -m pytest --cov=onebar --cov-report=term-missing

test-live:
	ONEBAR_LIVE=1 python -m pytest
