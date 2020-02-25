import yaml
import uuid
import fractions
import apispec.yaml_utils
import gemma
import pytest
import datetime
import pathlib
import sys
import marshmallow
from dataclasses import dataclass, field
from grahamcracker import schema_for, DataSchema
from typing import Union, Optional
from marshmallow import fields

from spanserver import (
    SpanRoute,
    SpanAPI,
    DocInfo,
    DocRespInfo,
    MimeType,
    Request,
    Response,
    ParamInfo,
    ParamTypes,
)


def fraction_representer(dumper: yaml.Dumper, data: fractions.Fraction):
    return dumper.represent_str(str(data))


apispec.yaml_utils.YAMLDumper.add_representer(fractions.Fraction, fraction_representer)


class FractionField(fields.Field):
    def _serialize(self, value, attr, obj, **kwargs):
        return str(value)

    def _deserialize(self, value, attr, data, **kwargs):
        return fractions.Fraction(value)


@dataclass
class Name:
    """Name of a Wizard!"""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    first: str = "Harry"
    last: str = "Potter"
    platform: fractions.Fraction = fractions.Fraction("39/4")


@schema_for(Name, type_handlers={fractions.Fraction: FractionField})
class NameSchema(DataSchema[Name]):
    pass


def load_route(spec: Union[str, dict], route: str = "/route") -> dict:
    if isinstance(spec, str):
        spec = yaml.safe_load(spec)
    return spec["paths"][route]


def get_route_req_schema(route: dict, content_type: str = MimeType.JSON.value):
    course = (
        gemma.PORT
        / "get"
        / "requestBody"
        / "content"
        / gemma.Item(content_type)
        / "schema"
    )
    return course.fetch(route)


def get_route_resp_schema(
    route: dict, code: int, content_type: str = MimeType.JSON.value
):
    course = (
        gemma.PORT
        / "get"
        / "responses"
        / str(code)
        / "content"
        / gemma.Item(content_type)
        / "schema"
    )
    return course.fetch(route)


def get_route_req_example(route: dict, content_type: str = MimeType.JSON.value):
    course = (
        gemma.PORT
        / "get"
        / "requestBody"
        / "content"
        / gemma.Item(content_type)
        / "example"
    )
    return course.fetch(route)


def get_route_resp_example(
    route: dict, code: int, content_type: str = MimeType.JSON.value
):
    course = (
        gemma.PORT
        / "get"
        / "responses"
        / str(code)
        / "content"
        / gemma.Item(content_type)
        / "example"
    )
    return course.fetch(route)


def get_param(params: list, param_name: str) -> dict:
    return next(p for p in params if p["name"] == param_name)


def get_spec(api: SpanAPI) -> dict:
    spec = api.openapi.openapi
    print(spec)
    return spec


class TestDocDescriptions:
    def test_concat(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            """
            A route definition.
            """

            def on_get(self):
                """
                description: A thing.
                responses:
                    201:
                        description: Some Response.
                """
                pass

        spec = get_spec(api)
        api_route = load_route(spec)
        assert Route.__doc__.startswith("\nA route definition.")
        assert api_route["get"]["description"] == "A thing."
        assert api_route["get"]["responses"]["201"]["description"] == "Some Response."

    def test_no_concat(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            """
            A route definition.
            ---
            get:
                responses:
                    200:
                        description: OK.
            """

            def on_get(self):
                """
                description: A thing.
                """
                pass

        print(api.openapi.openapi)
        assert "A thing" not in Route.__doc__

    def test_implicit_summary(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                """
                a simple summary
                """
                pass

        spec = get_spec(api)
        api_route = load_route(spec)

        assert api_route["get"]["summary"] == "A simple summary."
        assert "description" not in api_route["get"]

    def test_implicit_summary_and_description(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                """
                a simple summary

                followed by some description
                """
                pass

        spec = get_spec(api)
        api_route = load_route(spec)

        assert api_route["get"]["summary"] == "A simple summary."
        assert api_route["get"]["description"] == "Followed by some description."

    def test_implicit_200_ok(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                pass

        spec = get_spec(api)
        api_route = load_route(spec)
        assert api_route["get"]["responses"]["200"]["description"] == "Ok."

    def test_implicit_201_created(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                pass

            class Document:
                get = DocInfo(responses={201: DocRespInfo()})

        spec = get_spec(api)
        api_route = load_route(spec)
        assert api_route["get"]["responses"]["201"]["description"] == "Created."
        assert "200" not in api_route["get"]["responses"]

    def test_auto_default_creation(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                pass

        spec = api.openapi.openapi
        print(spec)
        api_route = load_route(spec)
        assert api_route["get"]["responses"]["default"]["description"] == "Error."

    def test_implicit_401_error(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                pass

            class Document:
                get = DocInfo(responses={401: DocRespInfo()})

        spec = get_spec(api)
        api_route = load_route(spec)
        assert api_route["get"]["responses"]["401"]["description"] == "Error."
        assert "default" not in api_route["get"]["responses"]

    def test_description_through_doc(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                pass

            class Document:
                get = DocInfo(
                    responses={200: DocRespInfo(description="some Description")}
                )

        spec = get_spec(api)
        api_route = load_route(spec)
        assert api_route["get"]["responses"]["200"]["description"] == (
            "Some Description."
        )

    def test_docsting_bad_type(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                """
                - Word 1
                - Word 2
                """
                pass

        spec = get_spec(api)
        assert "Word" not in spec

    def test_docsting_yaml_error(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self):
                """:"""
                pass

        spec = get_spec(api)


class TestDocPathParams:
    @pytest.mark.parametrize(
        "param_type, schema_type, schema_format",
        [
            (str, "string", None),
            (bool, "boolean", None),
            (int, "integer", None),
            (float, "number", "float"),
            (datetime.date, "string", "date"),
            (datetime.datetime, "string", "date-time"),
            (uuid.UUID, "string", "uuid"),
            (fractions.Fraction, "string", "fraction"),
        ],
    )
    def test_str_param(
        self,
        api: SpanAPI,
        param_type: type,
        schema_type: str,
        schema_format: Optional[str],
    ):
        @api.route("/route/{param}")
        class Route(SpanRoute):
            def on_get(self, req: Request, resp: Response, *, param: param_type):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec, route="/route/{param}")

        param_block = api_route["get"]["parameters"][0]
        assert param_block["in"] == "path"
        assert param_block["name"] == "param"
        assert param_block["schema"]["type"] == schema_type

        if schema_format is None:
            assert "format" not in param_block["schema"]
        else:
            assert param_block["schema"]["format"] == schema_format


class TestDocCustomParams:
    def test_doc_custom_header(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self, req: Request, resp: Response):
                pass

            class Document:
                get = DocInfo(
                    req_params=[
                        ParamInfo(
                            param_type=ParamTypes.HEADER,
                            name="custom-header",
                            decode_types=[float],
                            description="Some Custom Header.",
                            default=5.0,
                            min=1.0,
                            max=10.0,
                            required=False,
                        )
                    ]
                )

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)
        param = api_route["get"]["parameters"][0]

        assert param["in"] == "header"
        assert param["name"] == "custom-header"
        assert param["description"] == "Some Custom Header."
        assert param["required"] is False
        assert param["schema"]["type"] == "number"
        assert param["schema"]["format"] == "float"
        assert param["schema"]["default"] == 5.0
        assert param["schema"]["minimum"] == 1.0
        assert param["schema"]["maximum"] == 10.0


class TestDocSchemas:
    def test_req_schema(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=NameSchema())
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)
        schema = get_route_req_schema(api_route)

        assert "NameGetReq1" in schema["$ref"]
        assert "NameGetReq1" in spec["components"]["schemas"]

        assert "Names" in api_route["get"]["tags"]

        tag_def = next(t for t in spec["tags"] if t["name"] == "Names")
        assert tag_def["description"] == Name.__doc__

    def test_req_schema_custom_name(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=NameSchema(), req_name="HumanName")
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)
        schema = get_route_req_schema(api_route)

        assert "HumanName" in schema["$ref"]
        assert "HumanName" in spec["components"]["schemas"]

        assert "Names" in api_route["get"]["tags"]

        tag_def = next(t for t in spec["tags"] if t["name"] == "Names")
        assert tag_def["description"] == Name.__doc__

    def test_req_schema_double_name(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=NameSchema())
            def on_get(self, req: Request, resp: Response):
                pass

        @api.route("/route/second")
        class Route(SpanRoute):
            @api.use_schema(req=NameSchema())
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)

        api_route_1 = load_route(spec)
        schema_1 = get_route_req_schema(api_route_1)

        api_route_2 = load_route(spec, route="/route/second")
        schema_2 = get_route_req_schema(api_route_2)

        assert "NameGetReq1" in schema_1["$ref"]
        assert "NameGetReq2" in schema_2["$ref"]

        assert "NameGetReq1" in spec["components"]["schemas"]
        assert "NameGetReq2" in spec["components"]["schemas"]

        assert "Names" in api_route_1["get"]["tags"]
        assert "Names" in api_route_2["get"]["tags"]

        tag_defs = [t for t in spec["tags"] if t["name"] == "Names"]
        assert len(tag_defs) == 1
        assert tag_defs[0]["description"] == Name.__doc__

    def test_resp_schema(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(resp=NameSchema())
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)
        schema = get_route_resp_schema(api_route, 200)

        assert "NameGetResp1" in schema["$ref"]
        assert "NameGetResp1" in spec["components"]["schemas"]

        assert "Names" in api_route["get"]["tags"]

        tag_def = next(t for t in spec["tags"] if t["name"] == "Names")
        assert tag_def["description"] == Name.__doc__

    def test_resp_schema_custom_name(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(resp=NameSchema(), resp_name="HumanName")
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)
        schema = get_route_resp_schema(api_route, 200)

        assert "HumanName" in schema["$ref"]
        assert "HumanName" in spec["components"]["schemas"]

        assert "Names" in api_route["get"]["tags"]

        tag_def = next(t for t in spec["tags"] if t["name"] == "Names")
        assert tag_def["description"] == Name.__doc__

    def test_req_resp_schema_custom_name(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=NameSchema(), resp=NameSchema())
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)

        req_schema = get_route_req_schema(api_route)
        resp_schema = get_route_resp_schema(api_route, 200)

        assert "NameGetReq1" in req_schema["$ref"]
        assert "NameGetResp1" in resp_schema["$ref"]

        assert "NameGetReq1" in spec["components"]["schemas"]
        assert "NameGetResp1" in spec["components"]["schemas"]

        assert "Names" in api_route["get"]["tags"]

        tag_defs = [t for t in spec["tags"] if t["name"] == "Names"]
        assert len(tag_defs) == 1
        assert tag_defs[0]["description"] == Name.__doc__

    def test_req_mimetype(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=MimeType.TEXT)
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)
        schema = get_route_req_schema(api_route, MimeType.TEXT.value)

        assert schema["type"] == "string"

    def test_resp_mimetype(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(resp=MimeType.TEXT)
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)
        schema = get_route_resp_schema(api_route, 200, MimeType.TEXT.value)

        assert schema["type"] == "string"

    def test_schema_description_multiline(self, api: SpanAPI):
        class SomeSchema(marshmallow.Schema):
            """
            This is quite a long description, we want to make sure that it is de-dented
            and the extra newlines are removed, as that causes formatting issues with
            some documentation tools.
            """

        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=SomeSchema())
            def on_get(self, req: Request, resp: Response):
                pass

        tag_name = "Somes"

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)

        assert tag_name in api_route["get"]["tags"]

        tag_def = next(t for t in spec["tags"] if t["name"] == tag_name)
        assert tag_def["description"] == (
            "This is quite a long description, we want to make sure that it is "
            "de-dented\nand the extra newlines are removed, as that causes formatting "
            "issues with\nsome documentation tools."
        )

    @pytest.mark.parametrize(
        "schema_name, tag_name",
        [
            ("nameSchema", "names"),
            ("SomeStorySchema", "SomeStories"),
            ("ScanSeriesSchema", "ScanSeries"),
            ("ScanSeriesschema", "ScanSeries"),
        ],
    )
    def test_schema_tag_complex_plural(
        self, api: SpanAPI, schema_name: str, tag_name: str
    ):
        """Tests that schema names are properly pluralized."""

        schema_type = type(
            schema_name, (marshmallow.Schema,), {"__doc__": "Some description."}
        )

        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=schema_type())
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)

        assert tag_name in api_route["get"]["tags"]

        tag_def = next(t for t in spec["tags"] if t["name"] == tag_name)
        assert tag_def["description"] == schema_type.__doc__


class TestDocExamples:
    def test_req_example(self, api: SpanAPI):
        example_data = Name()

        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=NameSchema())
            def on_get(self, req: Request, resp: Response):
                pass

            class Document:
                get = DocInfo(req_example=example_data)

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)

        example = get_route_req_example(api_route)
        assert example == NameSchema().dump(example_data)

    def test_req_example_text(self, api: SpanAPI):
        example_data = "Harry Potter"

        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=MimeType.TEXT)
            def on_get(self, req: Request, resp: Response):
                pass

            class Document:
                get = DocInfo(req_example=example_data)

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)

        example = get_route_req_example(api_route, MimeType.TEXT.value)
        assert example == example_data

    def test_resp_example(self, api: SpanAPI):
        example_data = Name()

        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(resp=NameSchema())
            def on_get(self, req: Request, resp: Response):
                pass

            class Document:
                get = DocInfo(responses={200: DocRespInfo(example=example_data)})

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)

        example = get_route_resp_example(api_route, 200)
        assert example == NameSchema().dump(example_data)

    def test_resp_example_text(self, api: SpanAPI):
        example_data = "Harry Potter"

        @api.route("/route")
        class Route(SpanRoute):
            @api.use_schema(req=MimeType.TEXT)
            def on_get(self, req: Request, resp: Response):
                pass

            class Document:
                get = DocInfo(responses={200: DocRespInfo(example=example_data)})

        spec = get_spec(api)
        spec = yaml.safe_load(spec)
        api_route = load_route(spec)

        example = get_route_resp_example(api_route, 200, MimeType.TEXT.value)
        assert example == example_data


class TestErrorHeaders:
    def test_doc_error_headers(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)

        api_route = load_route(spec)
        headers = api_route["get"]["responses"]["default"]["headers"]

        this_header = headers["error-name"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["default"] == "APIError"

        this_header = headers["error-message"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["default"] == "An unknown error has occurred."

        this_header = headers["error-code"]
        assert this_header["schema"]["type"] == "integer"

        this_header = headers["error-data"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["format"] == "dict"

        this_header = headers["error-id"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["format"] == "uuid"

    def test_doc_error_headers_401(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self, req: Request, resp: Response):
                pass

            class Document:
                get = DocInfo(responses={401: DocRespInfo()})

        spec = get_spec(api)
        spec = yaml.safe_load(spec)

        api_route = load_route(spec)
        headers = api_route["get"]["responses"]["401"]["headers"]

        this_header = headers["error-name"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["default"] == "APIError"

        this_header = headers["error-message"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["default"] == "An unknown error has occurred."

        this_header = headers["error-code"]
        assert this_header["schema"]["type"] == "integer"

        this_header = headers["error-data"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["format"] == "dict"

        this_header = headers["error-id"]
        assert this_header["schema"]["type"] == "string"
        assert this_header["schema"]["format"] == "uuid"


class TestDocPagedHeaders:
    def test_doc_paged_params(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.paged(limit=200, default_offset=10)
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)

        api_route = load_route(spec)
        params = api_route["get"]["parameters"]

        limit = get_param(params, "paging-limit")
        assert limit["schema"]["type"] == "integer"
        assert limit["schema"]["maximum"] == 200

        offset = get_param(params, "paging-offset")
        assert offset["schema"]["type"] == "integer"
        assert offset["schema"]["default"] == 10

        headers = api_route["get"]["responses"]["200"]["headers"]

        total_items = headers["paging-total-items"]
        assert total_items["schema"]["type"] == "integer"

        total_pages = headers["paging-total-pages"]
        assert total_pages["schema"]["type"] == "integer"

        next_page = headers["paging-next"]
        assert next_page["schema"]["type"] == "string"

        previous_page = headers["paging-previous"]
        assert previous_page["schema"]["type"] == "string"

        current_page = headers["paging-current-page"]
        assert current_page["schema"]["type"] == "integer"

    def test_paged_not_in_error_default(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.paged(limit=200, default_offset=10)
            def on_get(self, req: Request, resp: Response):
                pass

        spec = get_spec(api)
        spec = yaml.safe_load(spec)

        api_route = load_route(spec)
        response_error_headers = api_route["get"]["responses"]["default"]["headers"]

        assert "paging-limit" not in response_error_headers
        assert "paging-offset" not in response_error_headers
        assert "paging-total-items" not in response_error_headers

    def test_paged_not_in_error(self, api: SpanAPI):
        @api.route("/route")
        class Route(SpanRoute):
            @api.paged(limit=200, default_offset=10)
            def on_get(self, req: Request, resp: Response):
                pass

            class Document:
                get = DocInfo(responses={401: DocRespInfo()})

        spec = get_spec(api)
        spec = yaml.safe_load(spec)

        api_route = load_route(spec)
        response_error_headers = api_route["get"]["responses"]["401"]["headers"]

        assert "paging-limit" not in response_error_headers
        assert "paging-offset" not in response_error_headers
        assert "paging-total-items" not in response_error_headers


class TestSaveFiles:
    def test_openapi_spec_save(self, api: SpanAPI, openapi_save_path: pathlib.Path):
        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self, req: Request, resp: Response):
                pass

        assert not openapi_save_path.exists()
        api.openapi_save(openapi_save_path)
        assert openapi_save_path.exists()

    def test_redoc_save(
        self,
        api: SpanAPI,
        openapi_save_path: pathlib.Path,
        redoc_save_path: pathlib.Path,
    ):
        if "win" in sys.platform.lower():
            pytest.skip("redoc-cli functionality not tested on windows.")

        @api.route("/route")
        class Route(SpanRoute):
            def on_get(self, req: Request, resp: Response):
                pass

        assert not openapi_save_path.exists()
        assert not redoc_save_path.exists()

        api.redoc_save(path_openapi=openapi_save_path, path_redoc=redoc_save_path)

        assert openapi_save_path.exists()
        assert redoc_save_path.exists()
