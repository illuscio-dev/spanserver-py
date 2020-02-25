import pytest
import json
import dataclasses
import uuid
import grahamcracker
from typing import List

from requests import Response
from spanserver import test_utils, MimeType

from spantools import errors_api, PagingResp, DEFAULT_ENCODERS

encode_bson = DEFAULT_ENCODERS[MimeType.BSON]


@dataclasses.dataclass
class Name:
    first: str
    last: str


@grahamcracker.schema_for(Name)
class NameSchema(grahamcracker.DataSchema[Name]):
    pass


class TestValidateResponse:
    def test_basic_response(self):
        r = Response()
        r.status_code = 200

        test_utils.validate_response(r)

    def test_basic_response_custom_status(self):
        r = Response()
        r.status_code = 201

        test_utils.validate_response(r, valid_status_codes=201)

    def test_basic_response_custom_status_tuple(self):
        r = Response()
        r.status_code = 201

        test_utils.validate_response(r, valid_status_codes=(200, 201))

    def test_basic_response_status_raises(self):
        r = Response()
        r.status_code = 201

        with pytest.raises(test_utils.StatusMismatchError):
            test_utils.validate_response(r)

    def test_basic_response_status_raises_tuple(self):
        r = Response()
        r.status_code = 400

        with pytest.raises(test_utils.StatusMismatchError):
            test_utils.validate_response(r, valid_status_codes=(200, 201))

    def test_validate_text(self):
        r = Response()
        r.status_code = 200
        r._content = "test text".encode()

        test_utils.validate_response(r, text_value="test text")

    def test_validate_text_raises(self):
        r = Response()
        r.status_code = 200
        r._content = "test text bad".encode()

        with pytest.raises(test_utils.TextValidationError):
            test_utils.validate_response(r, text_value="test text")

    def test_validate_text_not_text(self):
        r = Response()
        r.status_code = 200
        r._content = bytes(10)

        with pytest.raises(test_utils.TextValidationError):
            test_utils.validate_response(r, text_value="test text")

    def test_validate_headers(self):
        r = Response()
        r.status_code = 200
        r.headers = {"fake": "header"}

        test_utils.validate_response(r, expected_headers={"fake": "header"})

    def test_validate_headers_missing(self):
        r = Response()
        r.status_code = 200
        r.headers = {"fake": "header"}

        with pytest.raises(test_utils.HeadersMismatchError):
            test_utils.validate_response(r, expected_headers={"missing": "header"})

    def test_validate_headers_wrong(self):
        r = Response()
        r.status_code = 200
        r.headers = {"fake": "header"}

        with pytest.raises(test_utils.HeadersMismatchError):
            test_utils.validate_response(r, expected_headers={"fake": "wrong"})

    def test_validate_data_schema(self):
        r = Response()
        r.status_code = 200
        r._content = json.dumps({"first": "Harry", "last": "Potter"}).encode()

        name: Name = test_utils.validate_response(r, data_schema=NameSchema())
        assert name == Name("Harry", "Potter")

    def test_data_schema_bson(self):
        r = Response()
        r.status_code = 200
        r._content = encode_bson({"first": "Harry", "last": "Potter"})
        r.headers = {"Content-Type": "application/bson"}

        name: Name = test_utils.validate_response(r, data_schema=NameSchema())
        assert name == Name("Harry", "Potter")

    def test_data_schema_bson_many(self):
        r = Response()
        r.status_code = 200
        r._content = encode_bson(
            [
                {"first": "Harry", "last": "Potter"},
                {"first": "Hermione", "last": "Granger"},
            ]
        )
        r.headers = {"Content-Type": "application/bson"}

        names: List[Name] = test_utils.validate_response(
            r, data_schema=NameSchema(many=True)
        )
        assert names[0] == Name("Harry", "Potter")
        assert names[1] == Name("Hermione", "Granger")
        assert len(names) == 2

    def test_data_schema_bson_many_single(self):
        r = Response()
        r.status_code = 200
        r._content = encode_bson([{"first": "Harry", "last": "Potter"}])
        r.headers = {"Content-Type": "application/bson"}

        names: List[Name] = test_utils.validate_response(
            r, data_schema=NameSchema(many=True, normalize_many=True)
        )
        assert names[0] == Name("Harry", "Potter")
        assert len(names) == 1

    def test_validate_data_load_error(self):
        r = Response()
        r.status_code = 200
        r._content = bytes(10)

        with pytest.raises(test_utils.ContentDecodeError):
            test_utils.validate_response(r, data_schema=NameSchema())

    def test_validate_data_validation_error(self):
        r = Response()
        r.status_code = 200
        r._content = json.dumps({"first": "Harry"}).encode()

        with pytest.raises(test_utils.DataValidationError):
            test_utils.validate_response(r, data_schema=NameSchema())

    def test_validate_paging(self):
        r = Response()
        r.status_code = 200
        r.headers = {
            "paging-next": "www.url.com/next",
            "paging-previous": "www.url.com/previous",
            "paging-offset": 5,
            "paging-limit": 5,
            "paging-current-page": 2,
            "paging-total-pages": 10,
            "paging-total-items": 50,
        }

        expected_paging = PagingResp(
            next="www.url.com/next",
            previous="www.url.com/previous",
            offset=5,
            limit=5,
            current_page=2,
            total_pages=10,
            total_items=50,
        )

        test_utils.validate_response(r, expected_paging=expected_paging)

    def test_validate_paging_raises(self):
        r = Response()
        r.status_code = 200
        r.headers = {
            "paging-next": "www.url.com/next",
            "paging-previous": "www.url.com/previous",
            "paging-offset": 5,
            "paging-limit": 5,
            "paging-current-page": 2,
            "paging-total-pages": 10,
            "paging-total-items": 50,
        }

        expected_paging = PagingResp(
            next="www.url.com/next",
            previous="www.url.com/previous",
            offset=0,
            limit=5,
            current_page=2,
            total_pages=10,
            total_items=50,
        )

        with pytest.raises(test_utils.PagingMismatchError):
            test_utils.validate_response(r, expected_paging=expected_paging)

    def test_validate_paging_no_urls(self):
        r = Response()
        r.status_code = 200
        r.headers = {
            "paging-next": "www.url.com/next",
            "paging-previous": "www.url.com/previous",
            "paging-offset": 5,
            "paging-limit": 5,
            "paging-current-page": 2,
            "paging-total-pages": 10,
            "paging-total-items": 50,
        }

        expected_paging = PagingResp(
            next=None,
            previous=None,
            offset=5,
            limit=5,
            current_page=2,
            total_pages=10,
            total_items=50,
        )

        test_utils.validate_response(
            r, expected_paging=expected_paging, paging_urls=False
        )

    def test_validate_paging_no_urls_raises(self):
        r = Response()
        r.status_code = 200
        r.headers = {
            "paging-next": "www.url.com/next",
            "paging-previous": "www.url.com/previous",
            "paging-offset": 5,
            "paging-limit": 5,
            "paging-current-page": 2,
            "paging-total-pages": 10,
            "paging-total-items": 50,
        }

        expected_paging = PagingResp(
            next=None,
            previous=None,
            offset=5,
            limit=5,
            current_page=2,
            total_pages=10,
            total_items=50,
        )

        with pytest.raises(test_utils.PagingMismatchError):
            test_utils.validate_response(r, expected_paging=expected_paging)


class TestValidateError:
    def test_validate_error(self):
        r = Response()
        r.status_code = errors_api.NothingToReturnError.http_code
        r.headers = {
            "error-name": errors_api.NothingToReturnError.__name__,
            "error-code": errors_api.NothingToReturnError.api_code,
            "error-message": "some message",
            "error-id": str(uuid.uuid4()),
        }

        test_utils.validate_error(r, errors_api.NothingToReturnError)

    def test_status_mismatch(self):
        r = Response()
        r.status_code = 200
        r.headers = {
            "error-name": errors_api.NothingToReturnError.__name__,
            "error-code": errors_api.NothingToReturnError.api_code,
            "error-message": "some message",
            "error-id": str(uuid.uuid4()),
        }

        with pytest.raises(test_utils.StatusMismatchError):
            test_utils.validate_error(r, errors_api.NothingToReturnError)

    def test_validate_error_wrong_error(self):
        r = Response()
        r.status_code = 200
        r.headers = {
            "error-name": errors_api.NothingToReturnError.__name__,
            "error-code": errors_api.NothingToReturnError.api_code,
            "error-message": "some message",
            "error-id": str(uuid.uuid4()),
        }

        with pytest.raises(test_utils.WrongExceptionError):
            test_utils.validate_error(r, errors_api.InvalidMethodError)

    def test_validate_error_no_error(self):
        r = Response()
        r.status_code = 200
        r.headers = dict()

        with pytest.raises(test_utils.NoErrorReturnedError):
            test_utils.validate_error(r, errors_api.InvalidMethodError)

    def test_validate_error_no_error_no_headers(self):
        r = Response()
        r.status_code = 200

        with pytest.raises(test_utils.NoErrorReturnedError):
            test_utils.validate_error(r, errors_api.InvalidMethodError)


class TestPrintedInfo:
    def test_basic(self, capsys):
        r = Response()
        r.status_code = 200

        test_utils.validate_response(r)

        captured = capsys.readouterr()

        assert captured.out.startswith("RESPONSE: <Response [200]>\n")

    def test_text(self, capsys):
        r = Response()
        r.status_code = 200
        r._content = "test text".encode()

        test_utils.validate_response(r, text_value="test text")

        captured = capsys.readouterr()

        assert "CONTENT:" in captured.out
        assert "test text" in captured.out

    def test_body(self, capsys):
        r = Response()
        r.status_code = 200
        r._content = json.dumps({"key": "value"}).encode()

        test_utils.validate_response(r)

        captured = capsys.readouterr()

        assert '"key": "value"' in captured.out
        assert "JSON:" in captured.out

    def test_body_not_json(self, capsys):
        r = Response()
        r.status_code = 200
        r._content = bytes(10)

        test_utils.validate_response(r)

        captured = capsys.readouterr()

        assert "CONTENT:" in captured.out
        assert str(bytes(10)) in captured.out
