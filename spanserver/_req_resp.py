import responder.models
import responder.core
import responder.api as resp_api  # noqa: F401
import responder.routes as resp_routes  # noqa: F401
import functools
import marshmallow
import uuid
from marshmallow import Schema, ValidationError
from typing import (
    Optional,
    Callable,
    Union,
    Any,
    TypeVar,
    Generic,
    cast,
    Tuple,
    Dict,
    Type,
    FrozenSet,
)
from responder import Request as _ResponderRequest, Response as _ResponderResponse


from spantools import (
    MimeType,
    decode_content,
    PagingReq,
    PagingResp,
    MimeTypeTolerant,
    DecoderIndexType,
    EncoderIndexType,
    encode_content,
)
from spantools import ContentDecodeError, ContentEncodeError, ContentTypeUnknownError
from spantools.errors_api import (
    RequestValidationError,
    ResponseValidationError,
    NothingToReturnError,
)

from ._schema_info import LoadOptions, DumpOptions


FormatType = Optional[Union[Callable[["Request"], Any], str]]
MediaType = TypeVar("MediaType")
LoadedType = TypeVar("LoadedType")


class _NotLoadedFlag:
    pass


NOT_LOADED = _NotLoadedFlag()


REQ_VALIDATION_ERROR_MESSAGE = "Request data does not match schema."
RESP_VALIDATION_ERROR_MESSAGE = "Error in response data."


class Request(_ResponderRequest, Generic[MediaType, LoadedType]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._media: Optional[Union[MediaType, _NotLoadedFlag]] = NOT_LOADED
        self._media_loaded: Optional[Union[LoadedType, _NotLoadedFlag]] = NOT_LOADED
        self._paging: Optional[PagingReq] = None
        self._decoders: Optional[DecoderIndexType] = None
        self._schema: Optional[Schema] = None
        self._load_options: LoadOptions = LoadOptions.IGNORE
        self._projection: Optional[Dict[str, int]] = None

    @property
    def mimetype(self) -> Union[str, MimeType]:
        """Mimetype pulled from ``'Content-Type'`` request header."""
        mimetype = super().mimetype
        try:
            return MimeType.from_name(mimetype)
        except ValueError:
            return mimetype

    @property
    def paging(self) -> PagingReq:
        """Returns paging data pulled from url params."""
        if self._paging is None:
            raise TypeError("Route is not paged")
        else:
            return self._paging

    @property
    def projection(self) -> Dict[str, int]:
        """
        Return a str, int dict of which fields to project into the response. 1 means
        send field, 0 means remove field.

        Projection specification is passed via query params. A url with:
        ``'?project.id=1&project.data1=1'`` would return a payload with ONLY the
        ``id`` and ``data1`` fields.

        ``'?project.id=1&project.data1=0'`` would send back all fields except ``data1``.
        """
        if self._projection is None:

            self._projection = dict()

            header: str
            value: str

            for header, value in self.params.items():
                if header.lower().startswith("project."):
                    key = header[8:]
                    try:
                        self.projection[key] = int(value)
                    except (ValueError, TypeError):
                        raise RequestValidationError(
                            "project values must be '1' or '0'"
                        )

        return self._projection

    async def media(self) -> Optional[MediaType]:
        """
        Replacement for request's ``Request.media()``. Can handle bson with no special
        modification, and loads through schema when desired.
        """
        if self._media is not NOT_LOADED:
            self._media = cast(Optional[MediaType], self._media)
            return self._media

        if self._load_options is LoadOptions.IGNORE:
            schema = None
        else:
            schema = self._schema

        if isinstance(schema, MimeType):
            mimetype: MimeTypeTolerant = schema
            schema = None
        else:
            mimetype = self.mimetype

        content: Optional[bytes] = await self.content
        if content == b"":
            content = None

        if content is None and self._schema is None:
            return None

        try:
            loaded, mimetype_decoded = decode_content(  # type: ignore
                content=content,
                mimetype=mimetype,
                data_schema=schema,
                allow_sniff=True,
                decoders=self._decoders,
            )
        except ValidationError as error:
            raise RequestValidationError(
                message=REQ_VALIDATION_ERROR_MESSAGE, error_data=error.messages
            )
        except (ContentDecodeError, ContentTypeUnknownError):
            raise RequestValidationError("Media could not be decoded.")

        if self._load_options is LoadOptions.VALIDATE_ONLY:
            loaded = mimetype_decoded

        self._media = mimetype_decoded
        self._media_loaded = loaded

        self._media = cast(Optional[MediaType], self._media)
        return self._media

    async def media_loaded(self) -> Optional[LoadedType]:
        """Returns :func:`Request.media` data loaded through route schema."""
        if self._media_loaded is NOT_LOADED:
            await self.media()

        self._media_loaded = cast(Optional[LoadedType], self._media_loaded)
        return self._media_loaded


class ProjectionBuilder:
    """Handles building projection schemas for a route."""

    def __init__(self, route_method_schema: Schema):
        self.schema: Schema = route_method_schema
        self.schema_class: Type[marshmallow.Schema] = type(route_method_schema)
        self.hash = uuid.uuid4().int

    def build_projection_schema(
        self, project_keys: FrozenSet[Tuple[str, int]]
    ) -> marshmallow.Schema:
        # pass the route method hash so routes with similar schemas don't accidentally
        # use the wrong schema base.
        return self._build_projection_schema(project_keys, self.hash)

    @functools.lru_cache(maxsize=256)
    def _build_projection_schema(
        self, project_keys: FrozenSet[Tuple[str, int]], route_hash: int,
    ) -> marshmallow.Schema:
        """
        Generates a schema based on a client-requested projection. Implements an LRU
        cache of the last 256 schemas generated to reduce the overhead of schema
        initialization for popular projections.

        ``route_hash`` only exists to help the lru cache seperate routes. It is not
        used by the logic itself.
        """
        schema = self.schema

        # We need to start with the base schema settings. We don't want the client to
        # be able to expand the fields beyond what the route restricts them to.
        only_original = schema.only
        only = set()
        exclude = set(schema.exclude) if schema.exclude is not None else set()

        user_only = False
        for key, value in project_keys:
            if value == 0:
                exclude.add(key)
            elif value == 1:
                user_only = True
                if only_original is None or key in only_original:
                    only.add(key)
            else:
                raise RequestValidationError("Project values must be '0' or '1'")

        if user_only is False:
            # If the user did not request any fields to keep, use the original schema's
            # value.
            only_arg = only_original
        else:
            # Otherwise, if they did, then use the built list.
            only_arg = only

        # Init a new schema class.
        schema = self.schema_class(
            only=only_arg,
            exclude=exclude,
            many=schema.many,
            context=schema.context,
            load_only=schema.load_only,
            dump_only=schema.dump_only,
            partial=schema.partial,
            unknown=schema.unknown,
        )

        return schema


class Response(_ResponderResponse):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.mimetype: MimeTypeTolerant = None
        super().__init__(*args, **kwargs)
        self._req_accept: MimeTypeTolerant = None
        self._paging: Optional[PagingResp] = None
        self._encoders: Optional[EncoderIndexType] = None
        self._schema: Optional[Schema] = None
        self._dump_options: DumpOptions = DumpOptions.IGNORE
        self._projection: Dict[str, int] = dict()
        self._projection_builder: Optional[ProjectionBuilder] = None
        self.apply_projection: bool = True

    @property
    def paging(self) -> PagingResp:
        """
        Response paging information for response headers. Only ``total_items`` must be
        set for all other fields to be included in response.
        """
        if self._paging is None:
            raise TypeError("Route is not paged")
        else:
            return self._paging

    def _dump_media(self) -> None:
        content, schema, validate = self._resp_calculate_dump_settings()

        if schema is not None and self._dump_options is DumpOptions.VALIDATE_ONLY:
            errors = schema.validate(content)  # type: ignore
            if errors:
                raise ResponseValidationError(
                    RESP_VALIDATION_ERROR_MESSAGE, error_data=errors
                )
        try:
            content = encode_content(
                content=content,
                mimetype=self.mimetype,
                headers=self.headers,
                data_schema=schema,
                validate=validate,
                encoders=self._encoders,
            )
        except ValidationError as error:
            self.media = None
            raise ResponseValidationError(
                RESP_VALIDATION_ERROR_MESSAGE, error_data=error.messages
            )
        except (ContentEncodeError, ContentTypeUnknownError):
            self.media = None
            raise ResponseValidationError("Error Encoding Response")

        self.content = content

    def _resp_calculate_mimetype_and_schema(self) -> Optional[Schema]:
        accept = self._req_accept
        if accept == "*/*":
            accept = None

        if accept is not None:
            self.mimetype = accept

        if isinstance(self._schema, MimeType):
            schema = None
            self.mimetype = self._schema
        else:
            schema = self._schema

        return schema

    def _resp_calculate_undumped_content(self) -> Any:
        if self.media is not None:
            content = self.media
        elif self.text is not None:
            content = self.text
        else:
            content = self.content

        return content

    def _resp_calculate_dump_settings(
        self,
    ) -> Tuple[Optional[Any], Optional[Schema], bool]:
        schema = self._resp_calculate_mimetype_and_schema()

        content = self._resp_calculate_undumped_content()

        if self._schema is not None and content in [None, [], {}, "", b""]:
            raise NothingToReturnError("No Data to Return")

        validate = False
        if self._dump_options is DumpOptions.DUMP_AND_VALIDATE:
            validate = True
        elif self._dump_options is DumpOptions.IGNORE:
            validate = False
            schema = None
        elif self._projection and self.apply_projection:
            # Frozen set is a hashable type, so we can use it as a cache key, unlike
            # dict.
            assert self._projection_builder is not None
            projection_keys = frozenset(self._projection.items())
            schema = self._projection_builder.build_projection_schema(projection_keys)

        if self._projection_builder is None and self._projection:
            raise RequestValidationError("End point does not support projection.")

        return content, schema, validate


# We need to monkey-patch responder's Request class with our own subclass of it so we
# can add bson support.
responder.models.Request = Request
responder.core.Request = Request
responder.routes.Request = Request
responder.Request = Request
resp_api.models.Request = Request

responder.models.Response = Response
responder.core.Response = Response
responder.routes.Response = Response
responder.Response = Response
resp_api.models.Response = Response
