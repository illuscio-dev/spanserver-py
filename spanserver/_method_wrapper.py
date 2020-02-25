import sys
import traceback
import functools
from typing import Callable, Any, Dict, List

from spantools import (
    Error,
    DecoderIndexType,
    EncoderIndexType,
    errors_api,
    ContentEncodeError,
)

from ._req_resp import Request, Response
from ._openapi import ParamInfo


URLInfoType = List[ParamInfo]
DumpErrors = (errors_api.ResponseValidationError, ContentEncodeError)


def _handle_route_error(exc: BaseException, req: Request, resp: Response) -> None:
    error_data, exc_api = Error.from_exception(exc)

    # Set the response status code
    resp.status_code = exc_api.http_code

    # Set the header error info
    error_data.to_headers(resp.headers)

    sys.stderr.write(f'ERROR: ({error_data.id}) - {error_data.name} "{exc_api}"\n')
    traceback.print_exc(file=sys.stderr)

    if exc_api.send_media and not isinstance(exc_api, DumpErrors):
        try:
            resp._dump_media()
        except DumpErrors:
            resp.content = b""
    else:
        resp.content = b""


def _load_params(param_loaders: URLInfoType, **kwargs: Any) -> Dict[str, Any]:

    for info in param_loaders:
        kwargs[info.name] = info.load_param(kwargs[info.name])

    return kwargs


def method_wrapper(
    endpoint_method: Callable,
    param_info: URLInfoType,
    decoders: DecoderIndexType,
    encoders: EncoderIndexType,
) -> Callable:
    @functools.wraps(endpoint_method)
    async def wrapper(
        self: "SpanRoute", req: Request, resp: Response, *args: Any, **kwargs: Any
    ) -> None:
        try:
            kwargs = _load_params(param_info, **kwargs)
            req._decoders = decoders
            resp._encoders = encoders
            resp._req_accept = req.headers.get("Accept")
            resp._projection = req.projection

            await endpoint_method(self, req, resp, *args, **kwargs)

            resp._dump_media()

        except BaseException as error:
            _handle_route_error(error, req, resp)

    return wrapper


type_helper = False
if type_helper:
    from ._route import SpanRoute
