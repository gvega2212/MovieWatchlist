.PHONY: test test-cov lint

test:
	pytest

test-cov:
	pytest --cov=app_core --cov=models --cov-report=term-missing --cov-fail-under=70
