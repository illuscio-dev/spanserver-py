import inspect
from typing_inspect_isle import is_union_type, get_args
from responder import Response, Request
from typing import Any, TypeVar, Generic, List, Callable

from spantools import DecoderIndexType, EncoderIndexType
from spantools.errors_api import InvalidMethodError

from ._method_wrapper import _handle_route_error, method_wrapper
from ._openapi import ParamTypes, ParamInfo, DocInfo


ParamType = TypeVar("ParamType", bound=type)
Param = Generic[ParamType]


class SpanRoute:
    """
    Base class for class-view based routing with :class:`SpanAPI` See responder's
    documentation for more information on class-based routing.
    """

    async def on_request(self, req: Request, resp: Response, **kwargs: Any) -> None:
        if not hasattr(self, f"on_{req.method}"):
            error = InvalidMethodError(
                f"'{req.full_url}' does not support {req.method.upper()}"
            )
            _handle_route_error(error, req, resp)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if cls.Document is SpanRoute.Document:
            cls.Document = type("Document", (object,), {})  # type: ignore

        for method in cls.__dict__:
            if not method.startswith("on_"):
                continue

            http_method = method.replace("on_", "")

            doc_config = getattr(cls.Document, http_method, DocInfo())
            setattr(cls.Document, http_method, doc_config)

    @classmethod
    def wrap_methods(
        cls, decoders: DecoderIndexType, encoders: EncoderIndexType
    ) -> None:
        request_methods = tuple(
            item
            for item in cls.__dict__.items()  # type: ignore
            if item[0].startswith("on_")
        )

        # wrap request method in error-handler and pull out documentation config info
        for name, method in request_methods:
            if not callable(method):
                raise TypeError(f"method {name} not callable")

            http_method = name.replace("on_", "")
            doc_config: DocInfo = getattr(cls.Document, http_method)

            url_param_info = get_url_param_loaders(method)
            doc_config.req_params.extend(url_param_info)

            wrapped = method_wrapper(
                method, url_param_info, decoders=decoders, encoders=encoders
            )

            setattr(cls, f"on_{http_method}", wrapped)

    class Document:
        pass


def get_url_param_loaders(endpoint_method: Callable) -> List[ParamInfo]:

    params = inspect.signature(endpoint_method).parameters
    url_param_info: List[ParamInfo] = list()

    for param in params.values():
        if param.kind is not param.KEYWORD_ONLY:
            continue

        if is_union_type(param.annotation):
            decode_types = get_args(param.annotation)
        else:
            decode_types = [param.annotation]

        param_info = ParamInfo(
            param_type=ParamTypes.PATH, name=param.name, decode_types=decode_types
        )
        url_param_info.append(param_info)

    return url_param_info
