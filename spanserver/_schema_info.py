import enum
from dataclasses import dataclass, field, InitVar
from typing import Optional, Union, Type
from marshmallow import Schema

from spantools import SpanError
from spantools import MimeType


class ReqResp(enum.Enum):
    REQ = enum.auto()
    RESP = enum.auto()


class LoadOptions(enum.Enum):
    VALIDATE_AND_LOAD = enum.auto()
    VALIDATE_ONLY = enum.auto()
    IGNORE = enum.auto()


class DumpOptions(enum.Enum):
    DUMP_ONLY = enum.auto()
    VALIDATE_ONLY = enum.auto()
    DUMP_AND_VALIDATE = enum.auto()
    IGNORE = enum.auto()


class NoSchemaError(SpanError):
    """Raised when no schema for route."""


REQ_VALIDATION_ERROR_MESSAGE = "Request data does not match schema."
RESP_VALIDATION_ERROR_MESSAGE = "Error in response data."


RouteSchemaType = Optional[Union[Type[Schema], Schema, MimeType]]


@dataclass
class RouteSchemaInfo:
    _req: InitVar[RouteSchemaType]
    """Schema class -- is flags.TEXT if schema-less text"""
    req_schema: Optional[Union[Schema, MimeType]] = field(init=False)
    """Schema class -- is flags.TEXT if schema-less text"""
    req_name: Optional[str]
    """Schema name -- is flags.TEXT if schema-less text"""
    req_load: LoadOptions
    """Options for loading req schemas."""

    _resp: InitVar[RouteSchemaType]
    """Schema class -- is flags.TEXT if schema-less text"""
    resp_schema: Optional[Union[Schema, MimeType]] = field(init=False)
    """Schema class -- is flags.TEXT if schema-less text"""
    resp_name: Optional[str]
    """Schema name -- is flags.TEXT if schema-less text"""
    resp_dump: DumpOptions
    """Options for dumping resp schemas."""

    def __post_init__(self, _req: RouteSchemaType, _resp: RouteSchemaType) -> None:
        # Cache isinstance info for schemas
        self.req_schema = _req
        self.resp_schema = _resp
