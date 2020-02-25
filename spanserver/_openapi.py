import textwrap
import yaml
import marshmallow
import gemma
import datetime
import uuid
import inflect
import re
import apispec
import responder.ext.schema
import responder.api
from enum import Enum
from dataclasses import dataclass, field
from typing import (
    Type,
    Callable,
    Optional,
    Any,
    Dict,
    Union,
    List,
    TypeVar,
    Sequence,
    Tuple,
    cast,
    overload,
)

from spantools import MimeType
from spantools.errors_api import RequestValidationError


class OpenAPISchema(responder.ext.schema.Schema):
    """Extension of responder's schema class to handle tags."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tags: List[dict] = list()

    @property
    def _apispec(self) -> apispec.APISpec:
        spec = super()._apispec
        for tag in self.tags:
            spec.tag(tag)
        return spec


# Override responder's schema with our class.
responder.ext.schema = OpenAPISchema
responder.api.OpenAPISchema = OpenAPISchema


ParamDecoderType = TypeVar("ParamDecoderType")


INFLECT = inflect.engine()


# Param Info Classes #####
# These classes help flag what params should be expected


class ParamTypes(Enum):
    PATH = "PATH"
    QUERY = "QUERY"
    HEADER = "HEADER"


DEFAULT_RESP_CODE = 5000000000


# STRING FORMATTING FUNCTIONS.


@overload
def fix_descriptions(description: str) -> str:
    ...


@overload
def fix_descriptions(description: None) -> None:
    ...


def fix_descriptions(description: Optional[str]) -> Optional[str]:
    """
    Makes sure that a description starts with a capital letter and ends with a period
    for consistency.
    """
    if description is None:
        return None

    description = textwrap.dedent(description)
    description = description.strip("\n").rstrip("\n")

    if description[-1] not in [c for c in "!'\":?."]:
        description += "."

    first_letter = description[0]
    capitalized = first_letter.capitalize()

    description = capitalized + description[1:]

    return description


def camel_case_split(string: str) -> List[str]:
    matches = re.finditer(
        ".+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)", string
    )
    return [m.group(0) for m in matches]


def proper_plural_tag(tag: str) -> str:
    """
    Inflect sometimes gets plural conversion wrong when there are capital letters, so
    we need to lower the word then reinsert the capitals.
    """
    words = camel_case_split(tag)

    last_word = words.pop()
    plural = INFLECT.plural(last_word.lower())

    combined = ""
    for original, new in zip(last_word, plural):
        if original.upper() == original and original.lower() == new:
            combined += original
        else:
            combined += new

    combined += plural[len(combined) :]  # noqa: E203

    words.append(combined)
    new_tag = "".join(words)

    return new_tag


def _separate_description_summary(docstring: str) -> Tuple[str, Optional[str]]:
    docstring_parts = docstring.strip("\n").rstrip("\n").split("\n\n")

    summary = docstring_parts.pop(0)
    summary = fix_descriptions(summary)

    if docstring_parts:
        description: Optional[str] = "\n\n".join(docstring_parts)
        description = fix_descriptions(description)
    else:
        description = None

    return summary, description


# OPENAPI DATA OBJECTS #####


@dataclass
class ParamInfo:
    """Parameter detail."""

    param_type: ParamTypes
    """Type of parameter."""

    name: str
    """Name of parameter."""

    decode_types: Sequence[type]
    """Python types for decoding from string."""

    description: Optional[str] = None
    """Description of parameter."""

    required: bool = True
    """Whether the parameter is required."""

    default: Optional[Any] = None
    """Default value used if the parameter is not passed."""

    max: Optional[float] = None
    """Maximum allowed value of the parameter."""

    min: Optional[float] = None
    """Minimum allowed value of the parameter."""

    def __post_init__(self) -> None:
        self.description = fix_descriptions(self.description)

    def load_param(self, value: Any) -> Any:

        for decoder in self.decode_types:
            try:
                if decoder is bool:
                    value = value.lower()
                    return value == "true" or value == "1"
                else:
                    return decoder(value)
            except BaseException:
                pass

        raise RequestValidationError(
            f"URL param {self.name} could not be cast to {decoder}"
        )

    def openapi_spec(self) -> Dict[str, Any]:

        schema_format_block: List[Dict[str, Any]] = list()
        for decode_type in self.decode_types:
            this_type, this_format = PARAM_SCHEMA_TRANSLATOR.get(
                decode_type, ("string", decode_type.__name__.lower())
            )

            format_block: Dict[str, Any] = {"type": this_type}

            if this_format is not None:
                format_block["format"] = this_format

            if self.default is not None and issubclass(type(self.default), decode_type):
                format_block["default"] = self.default

            if issubclass(decode_type, (int, float)):
                if self.min:
                    format_block["minimum"] = self.min

                if self.max:
                    format_block["maximum"] = self.max

            schema_format_block.append(format_block)

        if len(schema_format_block) > 1:
            schema_block = {"anyOf": schema_format_block}
        else:
            schema_block = schema_format_block[0]

        param_block = {
            "in": self.param_type.value.lower(),
            "name": self.name,
            "schema": schema_block,
            "required": self.required,
        }
        if self.description:
            param_block["description"] = self.description

        return param_block


@dataclass
class DocRespInfo:
    """Documentation information about method responses."""

    description: Optional[str] = None
    """Description of the response code."""
    example: Optional[Any] = None
    """Example of response payload."""
    params: List[ParamInfo] = field(default_factory=list)
    """Response Headers Details."""

    def __post_init__(self) -> None:
        self.description = fix_descriptions(self.description)


@dataclass
class ApiTag:
    """Tag information."""

    name: str
    """Name of tag."""
    description: str
    """Tag Description."""

    def __post_init__(self) -> None:
        self.description = fix_descriptions(self.description)


@dataclass
class DocInfo:
    req_example: Optional[Any] = None
    """Example request body data."""
    req_params: List[ParamInfo] = field(default_factory=list)
    """Request parameter details."""
    responses: Dict[int, DocRespInfo] = field(default_factory=dict)
    """Response codes and details."""
    tags: List[str] = field(default_factory=list)
    """Tags for this method."""


# OPENAPI Construction Functions #####


def reformat_spanroute_docstring(api: "SpanAPI", route: Type["SpanRoute"]) -> None:
    """
    Responder allows the definition of a route's openapi documentation in it's
    docstring. This function takes the route and any schema information, data examples,
    and paging info, and turns it into the proper OpenAPI spec.
    """
    # combine docstrings
    if route.__doc__ is None:
        docstring = ""
    else:
        docstring = textwrap.dedent(str(route.__doc__))

    if any(s.startswith("-") for s in docstring.splitlines()):
        # We do not need to do anything if the main section has an api docstring
        # already
        return

    methods_openapi = dict()

    for method_name, handler in route.__dict__.items():
        if not method_name.startswith("on_"):
            continue

        method_name = method_name.replace("on_", "")
        try:
            schema_info: Optional[RouteSchemaInfo] = api.method_schema_info(handler)
        except KeyError:
            schema_info = None

        method_openapi = _build_method(
            http_method=method_name,
            handler=handler,
            schema_info=schema_info,
            route=route,
        )

        methods_openapi[method_name] = method_openapi

    methods_doc_string = yaml.dump(methods_openapi)
    docstring = docstring + "\n---\n" + methods_doc_string

    route.__doc__ = docstring


def _extract_handler_docstring_spec(handler: Callable) -> dict:
    if handler.__doc__ is None:
        method_yaml: Dict[str, Any] = dict()
    else:
        method_doc = textwrap.dedent(str(handler.__doc__))

        try:
            loaded: Union[Dict[str, Any], str] = yaml.safe_load(method_doc)
        except yaml.YAMLError:
            loaded = dict()

        if not isinstance(loaded, dict):
            if isinstance(loaded, str):
                summary, description = _separate_description_summary(
                    docstring=method_doc
                )
                method_yaml = {"summary": summary}
                if description:
                    method_yaml["description"] = description
            else:
                method_yaml = dict()
        else:
            method_yaml = loaded

    return method_yaml


def _is_error_code(http_code: int) -> bool:
    """
    Determines if an http status code denotes an error. The current implementation
    assumes any code between 400 and 599 is an error.
    """
    return http_code in range(400, 600) or http_code == DEFAULT_RESP_CODE


def _handler_set_error_headers(doc_info: DocInfo) -> None:

    for status, response_info in doc_info.responses.items():
        if not _is_error_code(status):
            continue

        response_info.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                decode_types=[str],
                name="error-name",
                description="Human-readable error name.",
                default="APIError",
            )
        )

        response_info.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                decode_types=[str],
                name="error-message",
                description="Message containing information about the error.",
                default="An unknown error has occurred.",
            )
        )

        response_info.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                decode_types=[int],
                name="error-code",
                description="An API error code that identifies the error-type.",
                default=1000,
            )
        )

        response_info.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                decode_types=[dict],
                name="error-data",
                description=(
                    "JSON-serialized data about the error. For instance: request body "
                    "validation errors will return a dict with details about all "
                    "offending fields."
                ),
                required=False,
            )
        )

        response_info.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                decode_types=[uuid.UUID],
                name="error-id",
                description=(
                    "A unique ID with details about this error. Please reference when "
                    "reporting errors."
                ),
                required=False,
            )
        )


def _handler_set_paging_params(method_handler: Callable, doc_info: DocInfo) -> None:
    paged_limit = getattr(method_handler, "paged_limit")
    paged_offset = getattr(method_handler, "paged_offset")

    # REQ PAGING PARAMS #######
    doc_info.req_params.append(
        ParamInfo(
            param_type=ParamTypes.QUERY,
            name="paging-offset",
            decode_types=[int],
            description=("Index of first item to be returned in response body"),
            required=False,
            default=paged_offset,
        )
    )
    doc_info.req_params.append(
        ParamInfo(
            param_type=ParamTypes.QUERY,
            name="paging-limit",
            decode_types=[int],
            description=("Maximum number of items allowed in response body."),
            required=False,
            max=paged_limit,
        )
    )

    # RESP PAGING PARAMS #######
    # If there are no documented responses, we are going to assume a default response
    # code of 200, and apply paging info to that.
    for http_code, response_config in doc_info.responses.items():

        if _is_error_code(http_code):
            continue

        response_config.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                name="paging-offset",
                decode_types=[int],
                description=(f"Index of first item returned in response body"),
                required=True,
                default=paged_offset,
            )
        )

        response_config.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                name="paging-limit",
                decode_types=[int],
                description=("Maximum number of items allowed in response body."),
                required=True,
                max=paged_limit,
            )
        )

        response_config.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                name="paging-total-items",
                decode_types=[int],
                description=("Total number of items that match request."),
                required=True,
            )
        )

        response_config.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                name="paging-current-page",
                decode_types=[int],
                description=(
                    "Page number of item set in response body given current "
                    "limit-per-page."
                ),
                required=True,
            )
        )

        response_config.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                name="paging-previous",
                decode_types=[str],
                description=("URL to previous page."),
                required=True,
            )
        )

        response_config.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                name="paging-next",
                decode_types=[str],
                description=("URL to next page."),
                required=True,
            )
        )

        response_config.params.append(
            ParamInfo(
                param_type=ParamTypes.HEADER,
                name="paging-total-pages",
                decode_types=[int],
                description=(
                    "Total number of pages that match request given current "
                    "limit-per-page."
                ),
                required=True,
            )
        )


def _apply_example_data(
    method_yaml: dict,
    example_data: Any,
    schema: Optional[Union[marshmallow.Schema, MimeType]],
    resp_code: Optional[int],
) -> None:
    if isinstance(schema, marshmallow.Schema) and example_data is not None:
        example_data = schema.dump(example_data)

    if isinstance(example_data, (dict, list)):
        content_type = MimeType.JSON.value
    else:
        content_type = MimeType.TEXT.value

    if resp_code is not None:
        course = (
            gemma.PORT
            / gemma.Item("responses", factory=dict)
            / gemma.Item(resp_code, factory=dict)
        )
    else:
        course = gemma.PORT / gemma.Item("requestBody", factory=dict)

    course = (
        course
        / gemma.Item("content", factory=dict)
        / gemma.Item(content_type, factory=dict)
        / gemma.Item("example")
    )
    course.place(method_yaml, example_data)


def _handler_apply_examples(
    method_yaml: dict, doc_info: DocInfo, schema_info: Optional["RouteSchemaInfo"]
) -> None:
    if doc_info.req_example is not None and schema_info is not None:

        _apply_example_data(
            method_yaml=method_yaml,
            example_data=doc_info.req_example,
            schema=schema_info.req_schema,
            resp_code=None,
        )

    for code, response_info in doc_info.responses.items():
        if response_info.example is not None and schema_info is not None:
            _apply_example_data(
                method_yaml=method_yaml,
                example_data=response_info.example,
                schema=schema_info.resp_schema,
                resp_code=code,
            )


def _apply_schema_to_code(
    schema: Union[marshmallow.Schema, MimeType],
    schema_name: str,
    code: int,
    http_block: str,
    method_yaml: dict,
    req_resp: str,
) -> None:
    # We don't apply schemas to error codes.
    if code != -1 and _is_error_code(code):
        return None

    types_course = gemma.PORT / gemma.Item(http_block, factory=dict)

    if req_resp == "resp":
        types_course = types_course / gemma.Item(code, factory=dict)

    types_course = types_course / gemma.Item("content", factory=dict)

    try:
        types_blocks = types_course.fetch(method_yaml)
    except gemma.NullNameError:
        # If there are not listed content types, that means no example data was
        # applied, so we need to generate the type blocks.
        types_blocks = dict()
        if isinstance(schema, marshmallow.Schema):
            types_blocks[MimeType.JSON.value] = dict()
        else:
            types_blocks[MimeType.TEXT.value] = dict()
        types_course.place(method_yaml, types_blocks)

    for type_block in types_blocks.values():
        if isinstance(schema, marshmallow.Schema):
            schema_link = f"#/components/schemas/{schema_name}"
            type_block["schema"] = {"$ref": schema_link}
        else:
            type_block["schema"] = {"type": "string"}


def _apply_schema(
    method_yaml: dict, schema_info: "RouteSchemaInfo", req_resp: str
) -> None:

    if req_resp == "req":
        schema = schema_info.req_schema
        schema_name = schema_info.req_name
    else:
        schema = schema_info.resp_schema
        schema_name = schema_info.resp_name

    # We know the API has already assigned a name at this point, so we don't need to
    # worry about it being None.
    schema_name = cast(str, schema_name)

    if schema is None:
        return

    if req_resp == "req":
        http_block = "requestBody"
        resp_codes = [-1]
    else:
        http_block = "responses"
        resp_codes = [code for code in method_yaml["responses"]]

    for code in resp_codes:
        _apply_schema_to_code(
            schema=schema,
            schema_name=schema_name,
            code=code,
            http_block=http_block,
            method_yaml=method_yaml,
            req_resp=req_resp,
        )


def tag_name_from_schema(
    schema: Union[marshmallow.Schema, Type[marshmallow.Schema]]
) -> str:
    if not isinstance(schema, type):
        schema_class = schema.__class__
    else:
        schema_class = schema

    tag_name = re.sub("schema", "", schema_class.__name__, flags=re.IGNORECASE)
    tag_name = proper_plural_tag(tag_name)
    return tag_name


def _apply_schema_tags(method_yaml: dict, schema_info: "RouteSchemaInfo") -> None:
    # We prefer the request schema if it exists.
    tag_schema = None
    if isinstance(schema_info.req_schema, marshmallow.Schema):
        tag_schema = schema_info.req_schema
    elif isinstance(schema_info.resp_schema, marshmallow.Schema):
        tag_schema = schema_info.resp_schema

    # Auto-generate a tag group based on the schema name, and pluralize it.
    # NameSchema -> Names
    # Job -> Jobs
    if tag_schema is not None:
        tags = method_yaml.get("tags", list())
        tag_name = tag_name_from_schema(tag_schema)

        tags.append(tag_name)
        method_yaml["tags"] = tags


def _handler_apply_schemas(method_yaml: dict, schema_info: "RouteSchemaInfo") -> None:
    _apply_schema(method_yaml=method_yaml, schema_info=schema_info, req_resp="req")
    _apply_schema(method_yaml=method_yaml, schema_info=schema_info, req_resp="resp")

    # auto-tag methods based on schemas
    _apply_schema_tags(method_yaml, schema_info)


PARAM_SCHEMA_TRANSLATOR: Dict[Type, Tuple[str, Optional[str]]] = {
    str: ("string", None),
    bool: ("boolean", None),
    int: ("integer", None),
    float: ("number", "float"),
    datetime.date: ("string", "date"),
    datetime.datetime: ("string", "date-time"),
    uuid.UUID: ("string", "uuid"),
}


def _handler_apply_params(method_yaml: dict, doc_info: DocInfo) -> None:
    # REQ PARAMS
    params: List[dict] = list()

    for param_info in doc_info.req_params:
        params.append(param_info.openapi_spec())

    if params:
        method_yaml["parameters"] = params

    # RESP PARAMS
    for http_code, response_info in doc_info.responses.items():
        headers: Dict[str, dict] = dict()

        for param_info in response_info.params:
            param_block = param_info.openapi_spec()
            param_block.pop("in")

            name = param_block.pop("name")
            headers[name] = param_block

        if headers:
            course = (
                gemma.PORT
                / gemma.Item("responses")
                / gemma.Item(http_code, factory=dict)
                / gemma.Item("headers")
            )
            course.place(method_yaml, headers)


def _create_doc_info_for_docstring_responses(
    existing_responses: Dict[Union[str, int], dict], doc_info: DocInfo
) -> None:

    for existing_code, existing_response in existing_responses.items():

        http_code = int(existing_code)
        existing_description = existing_response.get("description")

        response_info = doc_info.responses.get(
            http_code, DocRespInfo(description=existing_description)
        )
        if response_info.description is None:
            response_info.description = fix_descriptions(existing_description)

        doc_info.responses[http_code] = response_info


def _handler_create_responses(method_yaml: dict, doc_info: DocInfo) -> None:
    existing_responses = method_yaml.get("responses", dict())
    all_defined = [c for c in existing_responses] + [c for c in doc_info.responses]

    # If no responses are defined, we create a default ok response.
    if not any(code for code in all_defined if not _is_error_code(code)):
        existing_responses[200] = dict()

    # If no error responses are defined, we create a default error response. This
    # response code will be subbed out later for a "Default" error code.
    if not any(code for code in all_defined if _is_error_code(code)):
        existing_responses[DEFAULT_RESP_CODE] = dict()

    _create_doc_info_for_docstring_responses(existing_responses, doc_info)

    # Now we go through and create or merge documentation info that was hand-typed into
    # the docstring with the DocInfo object in the route's "Document" class.
    for http_code, response_info in doc_info.responses.items():
        try:
            response_block = method_yaml["responses"][http_code]
        except KeyError:
            course = (
                gemma.PORT
                / gemma.Item("responses", factory=dict)
                / gemma.Item(http_code, factory=dict)
            )
            response_block = dict()
            course.place(method_yaml, response_block)

        # Apply generic descriptions to those missing it.
        if response_info.description is None:
            if http_code == 201:
                response_info.description = "Created."
            elif not _is_error_code(http_code):
                response_info.description = "Ok."
            else:
                response_info.description = "Error."

        response_block["description"] = response_info.description


def _build_method(
    http_method: str,
    handler: Callable,
    schema_info: Optional["RouteSchemaInfo"],
    route: Type["SpanRoute"],
) -> Optional[dict]:
    method_yaml = _extract_handler_docstring_spec(handler)
    doc_info: DocInfo = getattr(route.Document, http_method)

    _handler_create_responses(method_yaml, doc_info)

    if getattr(handler, "paged", False):
        _handler_set_paging_params(handler, doc_info)

    _handler_set_error_headers(doc_info)

    if schema_info is not None:
        _handler_apply_examples(
            method_yaml=method_yaml, doc_info=doc_info, schema_info=schema_info
        )
        _handler_apply_schemas(method_yaml, schema_info)

    _handler_apply_params(method_yaml, doc_info)

    responses = method_yaml["responses"]
    if DEFAULT_RESP_CODE in responses:
        responses["default"] = responses.pop(DEFAULT_RESP_CODE)

    return method_yaml


typing_help = False
if typing_help:
    from ._api import SpanAPI, RouteSchemaInfo
    from ._route import SpanRoute  # noqa: F401
