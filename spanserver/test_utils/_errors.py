from spantools import (
    ContentDecodeError,
    ContentEncodeError,
    SpanError,
    NoErrorReturnedError,
    InvalidAPIErrorCodeError,
)


(ContentDecodeError, ContentEncodeError, NoErrorReturnedError, InvalidAPIErrorCodeError)


class ResponseValidationError(SpanError):
    """Base Error for Exceptions Thrown by mismatched Responses."""


class StatusMismatchError(ResponseValidationError):
    """Response status does not match expectations."""


class WrongExceptionError(ResponseValidationError):
    """Error in headers does not match expected exception."""


class DataValidationError(ResponseValidationError):
    """Response data does not match schema."""


class DataTypeValidationError(ResponseValidationError):
    """Response data does not match schema."""


class TextValidationError(DataValidationError):
    """Response text does not match supplied value."""


class HeadersMismatchError(ResponseValidationError):
    """Headers do not match expected values."""


class ParamsMismatchError(ResponseValidationError):
    """Headers do not match expected values."""


class PagingMismatchError(ResponseValidationError):
    """Paging does not match expected values."""


class URLMismatchError(ResponseValidationError):
    """Request URL does not match expected url."""
