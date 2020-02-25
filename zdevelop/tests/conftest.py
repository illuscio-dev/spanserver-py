import pytest
import pathlib
import os

from spanserver import SpanAPI


@pytest.fixture
def api():
    return SpanAPI(
        title="TestAPI",
        description="An API for Testing Things",
        version="1.0.0",
        openapi="3.0.0",
    )


@pytest.fixture
def openapi_save_path():
    path = pathlib.Path("./zdevelop/tests/api_spec.yaml")
    try:
        os.remove(str(path))
    except FileNotFoundError:
        pass

    yield path

    try:
        os.remove(str(path))
    except FileNotFoundError:
        pass


@pytest.fixture
def redoc_save_path():
    path = pathlib.Path("./zdevelop/tests/redoc.html")
    try:
        os.remove(str(path))
    except FileNotFoundError:
        pass

    yield path

    try:
        os.remove(str(path))
    except FileNotFoundError:
        pass
