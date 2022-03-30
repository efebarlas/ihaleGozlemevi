To test with coverage:
pytest --cov=lib --cov-report=html tests
Test with logs enabled:
pytest --capture=no --log-cli-level=INFO