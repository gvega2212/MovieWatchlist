.PHONY: test test-cov
test:
	pytest -q

test-cov:
	pytest --cov=app_core --cov=movie_api --cov=models \
	       --cov-report=term-missing --cov-report=html --cov-report=xml \
	       --cov-fail-under=70 -q
