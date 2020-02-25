import requests
import uuid
import json
import dataclasses
from grahamcracker import schema_for, DataSchema
from typing import Type, Tuple, Optional, Dict, Union, Any
from marshmallow import Schema, ValidationError
from bson import InvalidBSON, InvalidDocument

from spantools import Error, PagingResp, MimeType, MimeTypeTolerant, decode_content
from spantools.errors_api import APIError

from ._errors import (
    StatusMismatchError,
    PagingMismatchError,
    WrongExceptionError,
    DataValidationError,
    ContentDecodeError,
    TextValidationError,
    HeadersMismatchError,
)


@schema_for(Error)
class _ErrorSchema(DataSchema[Error]):
    pass


_ERROR_SCHEMA = _ErrorSchema()


def _validate_status(
    response: requests.Response, valid_status_codes: Union[int, Tuple[int, ...]]
) -> None:

    if isinstance(valid_status_codes, int):
        valid_status_codes = (valid_status_codes,)

    if response.status_code not in valid_status_codes:
        raise StatusMismatchError(
            f"Got status code: {response.status_code}. Expected: {valid_status_codes}"
        )


def _print_response_data(response: requests.Response) -> None:

    print("RESPONSE:", response)
    print()
    print("HEADERS:", json.dumps(dict(response.headers), indent=4), sep="\n")
    print()

    try:
        print("JSON:", json.dumps(response.json(), indent=4), sep="\n")
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        print("CONTENT:", response.content, sep="\n")


def validate_error(response: requests.Response, error_type: Type[APIError]) -> Error:
    """
    Validates response contains correct error info, prints response and headers for
    test logs.

    :param response: from test client.
    :param error_type: APIError class that returned error should correspond to.

    :raises NoErrorReturnedError: No error information in response headers.
    :raises StatusMismatchError: Response http code does not match ``error_type``.
    :raises WrongExceptionError: Error data does not match ``error_type``.

    :return: error data model.

    Response status code and data are printed to stdout for log capture.

    All exceptions are inherited from :class:`ResponseValidationError`
    """
    _print_response_data(response)

    error = Error.from_headers(response.headers)

    try:
        assert error.name == error_type.__name__
        assert error.code == error_type.api_code
        assert error.message
        assert isinstance(error.id, uuid.UUID)
    except AssertionError:
        raise WrongExceptionError(f"Expected {error_type.__name__}. Got {error.name}")

    _validate_status(response, error_type.http_code)

    return error


def _validate_response_content(
    response: requests.Response, data_schema: Optional[Schema] = None
) -> Optional[Any]:
    if data_schema is None:
        return None

    try:
        try:
            mimetype: Optional[MimeTypeTolerant] = MimeType.from_name(
                response.headers.get("Content-Type")
            )
        except ValueError:
            mimetype = None

        loaded, _ = decode_content(
            response.content,
            mimetype=mimetype,
            data_schema=data_schema,
            allow_sniff=True,
        )
        return loaded

    except (json.JSONDecodeError, InvalidBSON, InvalidDocument, UnicodeDecodeError):
        raise ContentDecodeError("Could not load response data.")

    except ValidationError:
        raise DataValidationError("Error validating returned data")


def _validate_data(
    response: requests.Response,
    data_schema: Optional[Schema] = None,
    text_value: Optional[str] = None,
) -> Optional[Any]:

    if text_value is not None:
        data: Optional[Any] = response.text
        if data != text_value:
            raise TextValidationError(f"Got '{response.text}', expected '{data}'")
    else:
        data = _validate_response_content(response, data_schema)

    return data


def _validate_headers(
    response: requests.Response, expected_headers: Optional[Dict[str, str]] = None
) -> None:
    if expected_headers:
        for k, v in expected_headers.items():
            try:
                assert response.headers[k] == v
            except KeyError:
                raise HeadersMismatchError(f"{k} not in headers")
            except AssertionError:
                raise HeadersMismatchError(
                    f"Header {k} has value {response.headers[k]}, not {v}"
                )


def _validate_paging(
    response: requests.Response,
    expected_paging: Optional[PagingResp] = None,
    paging_urls: bool = True,
) -> None:
    if expected_paging is not None:
        received_paging = PagingResp.from_headers(response.headers)

        expected_values = dataclasses.asdict(expected_paging)
        received_values = dataclasses.asdict(received_paging)

        if not paging_urls:
            expected_values.pop("next")
            expected_values.pop("previous")

            received_values.pop("next")
            received_values.pop("previous")

        if expected_values != received_values:
            raise PagingMismatchError(
                f"Received values do not match expected values.\n"
                f"Received:\n"
                f"{received_values}\n"
                f"Expected:\n"
                f"{expected_values}"
            )


def validate_response(
    response: requests.Response,
    valid_status_codes: Union[int, Tuple[int, ...]] = 200,
    data_schema: Optional[Schema] = None,
    text_value: Optional[str] = None,
    expected_headers: Optional[Dict[str, str]] = None,
    expected_paging: Optional[PagingResp] = None,
    paging_urls: bool = True,
) -> Optional[Any]:
    """
    Validate response object from test client. For use when writing tests.

    :param response: from test client.
    :param valid_status_codes: Status code(s) expected.
    :param data_schema: used for loading data.
    :param text_value: if text return expected, the expected text value.
    :param expected_headers: dict of expected headers.
    :param expected_paging: Paging object with expected values.
    :param paging_urls: Whether to check the URLs of the paging object. Default is
        ``True``.

    :return: Loaded Data.

    :raises StatusMismatchError: Response http code does not match
        ``valid_status_codes``.
    :raises TextValidationError: Response.text does not match ``text_value``.
    :raises DataLoadError: Content could not be loaded as dict / bson.
    :raises DataValidationError: Loaded data does not match schema.
    :raises HeadersMismatchError: Response header values missing / different from
        ``expected_headers``. Additional values are allowed. Only passed values are
        checked.

    This function tests that:

        - Status code comes back as expected.

        - Data can be loaded by passed schema.

        - Header values match expected.

        - Text data matches expected value.

    Response status code and data are printed to stdout for log capture.

    All exceptions are inherited from :class:`ResponseValidationError`
    """
    _print_response_data(response)

    _validate_status(response, valid_status_codes)
    data = _validate_data(response, data_schema, text_value)
    _validate_headers(response, expected_headers)
    _validate_paging(response, expected_paging, paging_urls)

    return data
