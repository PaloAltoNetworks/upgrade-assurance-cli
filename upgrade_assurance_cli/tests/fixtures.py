import os
import pathlib

import pytest

@pytest.fixture
def report_store():
    fp = os.path.join(
        os.path.dirname(__file__), 'test_data'
    )
    return pathlib.Path(fp)

@pytest.fixture
def readiness_report():
    fp = os.path.join(
        os.path.dirname(__file__),
        os.path.join('test_data', 'readiness_1.1.1.1.json')
    )
    return pathlib.Path(fp)