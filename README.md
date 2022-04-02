To test with coverage:

pytest --cov=lib --cov-report=html tests

Test with no log interference:

pytest -p no:logging -s

Test specific file (append this to the end of pytest command):

./tests/test_lib.py::TestDataDrivenDesign::test_textSearcher