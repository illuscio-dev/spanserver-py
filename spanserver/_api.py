import functools
import urllib.parse
import math
import responder
import subprocess
import copy
from os import PathLike
from typing import (
    Optional,
    List,
    Type,
    Union,
    Any,
    Tuple,
    Callable,
    TypeVar,
    Dict,
    cast,
)
from marshmallow import Schema, fields
from grahamcracker import URLStr

from spantools import (
    MimeType,
    MimeTypeTolerant,
    PagingReq,
    PagingResp,
    DEFAULT_ENCODERS,
    DEFAULT_DECODERS,
    DecoderType,
    EncoderType,
    DecoderIndexType,
    EncoderIndexType,
)
from spantools.errors_api import APILimitError

from ._route import SpanRoute
from ._req_resp import Request, Response, ProjectionBuilder
from ._openapi import (
    reformat_spanroute_docstring,
    tag_name_from_schema,
    ParamInfo,
    ParamTypes,
    fix_descriptions,
    OpenAPISchema,
)
from ._schema_info import RouteSchemaInfo, LoadOptions, DumpOptions


HandlersDictType = Type[Union[Schema, fields.Field]]
ModelIndex = Tuple[Type, Optional[bool]]


SchemaType = Optional[Union[Schema, Type[Schema], MimeType]]
SchemaTypeInit = Optional[Union[Schema, MimeType]]


class _Default:
    pass


DEFAULT = _Default()
_Other = TypeVar("_Other")
DefaultType = Union[_Default, _Other]


PAGED_LIMIT_PARAM = ParamInfo(
    param_type=ParamTypes.QUERY,
    name="paging-limit",
    decode_types=[int],
    description="Number of items to return per page. Default ",
    required=False,
)


class SpanAPI(responder.API):
    """
    ``responder.API`` extension for data-driven micro-services
    """

    def __init__(
        self,
        debug: bool = False,
        title: Optional[str] = None,
        description: Optional[str] = None,
        version: Optional[str] = None,
        auto_escape: bool = True,
        openapi: Optional[str] = None,
        docs_route: Optional[str] = None,
        allowed_hosts: Optional[List[str]] = None,
        **kwargs: Any,
    ):

        self.openapi: OpenAPISchema

        super().__init__(
            debug=debug,
            title=title,
            description=description,
            version=version,
            allowed_hosts=allowed_hosts,
            openapi=openapi,
            docs_route=docs_route,
            auto_escape=auto_escape,
            **kwargs,
        )
        self.route_schema_info: Dict[str, RouteSchemaInfo] = dict()
        self._encoders: DecoderIndexType = copy.copy(DEFAULT_ENCODERS)
        self._decoders: EncoderIndexType = copy.copy(DEFAULT_DECODERS)

    def add_route(
        self,
        route: str,
        endpoint: Callable,
        *,
        default: bool = False,
        static: bool = False,
        check_existing: bool = True,
        websocket: bool = False,
        before_request: bool = False,
    ) -> None:
        if isinstance(endpoint, type) and issubclass(endpoint, SpanRoute):
            endpoint = cast(Type[SpanRoute], endpoint)
            endpoint.wrap_methods(  # type: ignore
                decoders=self._decoders, encoders=self._encoders
            )

            reformat_spanroute_docstring(self, endpoint)

        super().add_route(
            route=route,
            endpoint=endpoint,
            default=default,
            static=static,
            check_existing=check_existing,
            websocket=websocket,
            before_request=before_request,
        )

    def openapi_save(self, path: Union[str, PathLike]) -> None:
        """Save openapi.yaml file to ``path``"""
        with open(path, "w") as f:
            f.write(self.openapi.openapi)

    def redoc_save(
        self, path_openapi: Union[str, PathLike], path_redoc: Union[str, PathLike]
    ) -> None:
        """
        Save openapi.yaml file to ``path`` then generate ReDoc bundled api at
        ``path_redoc``.
        """

        self.openapi_save(path_openapi)

        commands = [
            "npx",
            "redoc-cli",
            "bundle",
            f"'{str(path_openapi)}'",
            "--output",
            f"'{str(path_redoc)}'",
        ]

        process = subprocess.Popen(commands)
        process.wait()

    def _add_schema_to_api(
        self,
        schema: SchemaTypeInit,
        passed_name: Optional[str],
        method: Callable,
        req_resp: str,
    ) -> Optional[str]:
        if not isinstance(schema, Schema):
            return passed_name

        if passed_name:
            self.openapi.add_schema(passed_name, schema)
            name = passed_name
        else:
            method_name = method.__name__.replace("on_", "").title()
            schema_name = schema.__class__.__name__.replace("Schema", "")

            i = 1
            while True:
                name = f"{schema_name}{method_name}{req_resp}{i}"
                try:
                    self.openapi.add_schema(name, schema)
                except AssertionError:
                    i += 1
                else:
                    break

        schema_type = schema.__class__
        tag_name = tag_name_from_schema(schema_type)
        tag_description = fix_descriptions(schema_type.__doc__)

        if tag_description:
            tag_info = {"name": tag_name, "description": tag_description}
            if not any(t["name"] == tag_name for t in self.openapi.tags):
                self.openapi.tags.append(tag_info)

        return name

    def _save_schema_info(
        self, endpoint_method: Callable, schema_info: RouteSchemaInfo
    ) -> None:
        key = repr(endpoint_method).split(" ")[1]
        self.route_schema_info[key] = schema_info

    def method_schema_info(self, endpoint_method: Callable) -> RouteSchemaInfo:
        key = repr(endpoint_method).split(" ")[1]
        return self.route_schema_info[key]

    def use_schema(
        self,
        *,
        req: SchemaType = None,
        req_name: Optional[str] = None,
        req_load: LoadOptions = LoadOptions.VALIDATE_AND_LOAD,
        resp: SchemaType = None,
        resp_name: Optional[str] = None,
        resp_dump: DumpOptions = DumpOptions.DUMP_ONLY,
    ) -> Callable:
        """
        Decorator for :class:`SpanRoute` methods to automatically validate incoming
        request data based on a given model.

        :param req: schema for request json data.
        :param req_name: name for request schema.
        :param req_load: loading options for req schema.

            - **VALIDATE_AND_LOAD**: Default. Loads and validates incoming data using
              the schema's ``loads`` method.

            - **VALIDATE_ONLY**: Validates incoming data, but passes raw dict to
              ``data`` param in route method.

            - **PASS_THROUGH**: Passes json data into ``data`` param of route, but does
              not validate or load it.

            - **IGNORE**: Uses ``req`` schema for documentation, but does nothing with
              incoming data at runtime -- default responder behavior.

        :param resp: schema for response json data.
        :param resp_name: name for response schema.
        :param resp_dump: loading options for req schema

            - **DUMP_ONLY**: Default. Dumps data using the schema's ``dump`` method.
              Only minimal validation is done during this process. See Marshmallow's
              documentation for details.

            - **VALIDATE_ONLY**: Validates outgoing data but does not dump it.

            - **VALIDATE_AND_DUMP**: Validates outdoing data, then dumps it.

            - **IGNORE**: Uses ``resp`` schema for documentation, but does nothing with
              outgoing data at runtime -- default responder behavior.

        A ``data`` param can be added to the decorated method which data from
        ``req.media()`` will be passed into based on the ``req_load`` option above.

        Using ``spanreed.flag.TEXT`` as the response or request schema indicates that
        data will be loaded or sent back from req.text rather than req.media, and
        openapi documentation will be tweaked accordingly.
        """
        schema_req = _init_schema(req)
        schema_resp = _init_schema(resp)

        # Add a projection builder for dynamically generating schemas based on client
        # requests
        if isinstance(schema_resp, Schema):
            projection_builder: Optional[ProjectionBuilder] = ProjectionBuilder(
                schema_resp
            )
        else:
            projection_builder = None

        def decorator(route_method: Callable) -> Callable:

            req_name_api = self._add_schema_to_api(
                schema_req, req_name, route_method, "Req"
            )
            resp_name_api = self._add_schema_to_api(
                schema_resp, resp_name, route_method, "Resp"
            )

            schema_options = RouteSchemaInfo(
                _req=schema_req,
                req_name=req_name_api,
                req_load=req_load,
                _resp=schema_resp,
                resp_name=resp_name_api,
                resp_dump=resp_dump,
            )

            @functools.wraps(route_method)
            async def wrapper(
                # Since we are wrapping class functions, "self" needs to be the first
                # parameter
                route: SpanRoute,
                http_req: Request,
                http_resp: Response,
                **kwargs: Any,
            ) -> None:

                # validate the incoming data if a model was provided.
                http_req._schema = schema_options.req_schema
                http_req._load_options = schema_options.req_load

                http_resp._schema = schema_options.resp_schema
                http_resp._dump_options = schema_options.resp_dump
                http_resp._projection_builder = projection_builder
                # await schema_options.load_req(http_req)

                # pass loaded data into the actual route method if applicable. Await the
                # response.
                await route_method(route, http_req, http_resp, **kwargs)
                # validate / dump response data.
                # schema_options.dump_response(http_resp=http_resp, http_req=http_req)

            self._save_schema_info(route_method, schema_options)

            return wrapper

        return decorator

    @staticmethod
    def paged(*, limit: int, default_offset: int = 0) -> Callable:
        """
        Decorator to handle paging for :class:`SpanRoute` method.

        :param limit: max items a user can request

        Assumes the possibility of ``paging-offset`` and ``paging-limit`` url params.
        Passes :class:`Paging` object into request and response ``paging`` attributes``.

        Paging information, including urls for the next / previous page are added to the
        response headers for all decorated routes.

        If ``paging.total_items`` must be set inside the route, all other paging
        attributes will be automatically generated based on the total item count.

        :raises APILimitError: If requested ``paging-limit`` url param is above
            ``limit``.
        """

        def decorator(route_method: Callable) -> Callable:
            @functools.wraps(route_method)
            async def wrapper(
                inst: Callable, req: Request, resp: Response, **kwargs: Any
            ) -> None:

                paging_req = PagingReq.from_params(
                    req.params, default_offset=default_offset, default_limit=limit
                )
                paging_resp: PagingResp = _set_up_paging_resp(req, app_limit=limit)
                req._paging = paging_req
                resp._paging = paging_resp
                await route_method(inst, req, resp, **kwargs)
                _adjust_paging_totals(paging_resp)

                paging_resp.to_headers(resp.headers)

            wrapper.paged = True  # type: ignore
            wrapper.paged_limit = limit  # type: ignore
            wrapper.paged_offset = default_offset  # type: ignore

            return wrapper

        return decorator

    def register_mimetype(
        self, mimetype: MimeTypeTolerant, encoder: EncoderType, decoder: DecoderType
    ) -> None:
        """
        Registers encoder and decoder function for a given mimetype.

        :param mimetype: to register for ex: ``'text/csv'``.
        :param encoder: Encodes mimetype data to binary.
        :param decoder: Decodes mimetype data to binary.
        :return:
        """
        try:
            mimetype = MimeType.from_name(mimetype)
        except ValueError:
            pass

        self._encoders[mimetype] = encoder
        self._decoders[mimetype] = decoder


def _init_schema(schema: SchemaType) -> Optional[Union[Schema, MimeType]]:
    if isinstance(schema, type) and issubclass(schema, Schema):
        schema = schema()
    return schema


def _replace_paging_info(url: URLStr, offset: int, limit: int) -> URLStr:
    params = {"paging-offset": str(offset), "paging-limit": str(limit)}

    url_parts = list(urllib.parse.urlparse(url))
    query = dict(urllib.parse.parse_qsl(url_parts[4]))
    query.update(params)

    url_parts[4] = urllib.parse.urlencode(query)

    return urllib.parse.urlunparse(url_parts)


def _set_up_paging_resp(req: Request, app_limit: int) -> PagingResp:
    """Sets up paging info based on request."""
    offset = int(req.params.get("paging-offset", 0))
    user_limit = int(req.params.get("paging-limit", app_limit))

    if user_limit > app_limit:
        raise APILimitError(
            f"item limit for {req.method} {req.full_url} is {app_limit}."
            f" {user_limit} requested."
        )

    next_url = _replace_paging_info(
        req.full_url, offset=offset + user_limit, limit=user_limit
    )
    if offset - user_limit >= 0:
        previous_url = _replace_paging_info(
            req.full_url, offset=offset - user_limit, limit=user_limit
        )
    else:
        previous_url = None

    current = math.floor(offset / user_limit) + 1

    paging = PagingResp(
        previous=previous_url,
        next=next_url,
        current_page=current,
        offset=offset,
        limit=user_limit,
        total_items=None,
        total_pages=None,
    )
    return paging


def _adjust_paging_totals(paging: PagingResp) -> None:
    """
    Adjusts total pages based on total items supplied by route. Removes url to next page
    if necessary.
    """
    if paging.total_items is not None:
        if paging.offset + paging.limit >= paging.total_items:
            paging.next = None
        paging.total_pages = math.ceil(paging.total_items / paging.limit)
