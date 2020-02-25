import marshmallow
import pytest
import uuid
import copy
import fractions
import datetime
import io
import csv
import pathlib
from bson import BSON
from bson.raw_bson import RawBSONDocument
from dataclasses import dataclass, field
from grahamcracker import schema_for, DataSchema, MISSING
from typing import Union, Optional, Type, Dict, List, Any

from spanserver import (
    Request,
    Response,
    SpanRoute,
    LoadOptions,
    DumpOptions,
    SpanAPI,
    MimeType,
    PagingResp,
    errors_api,
)
from spantools import DEFAULT_ENCODERS
from spanserver.test_utils import validate_error, validate_response


encode_bson = DEFAULT_ENCODERS[MimeType.BSON]


@dataclass
class Name:
    id: uuid.UUID
    first: str
    last: str


@schema_for(Name)
class NameSchema(DataSchema[Name]):
    @marshmallow.validates("last")
    def malfoy_sucks(self, value: str):
        if value.lower() == "malfoy":
            raise marshmallow.ValidationError("Malfoys are not allowed", "last")


@dataclass
class HasUUID:
    id: uuid.UUID = field(default_factory=uuid.uuid4())


@schema_for(HasUUID)
class HasUUIDSchema(DataSchema[HasUUID]):
    pass


# TEST VALUES
UUID_VALUE = uuid.uuid4()
UUID_STR = str(UUID_VALUE)

HARRY = Name(UUID_VALUE, "Harry", "Potter")
HARRY_DUMPED = NameSchema().dump(HARRY)

HARRY_BAD_ID = copy.copy(HARRY_DUMPED)
HARRY_BAD_ID["id"] = "badid"

DRACO = Name(UUID_VALUE, "Draco", "Malfoy")
DRACO_DUMPED = {"id": UUID_STR, "first": "Draco", "last": "Malfoy"}


class TestInit:
    def test_route_type_error(self, api: SpanAPI):
        with pytest.raises(TypeError):

            @api.route("/thing")
            class TestRoute(SpanRoute):
                on_get = None


class TestBasicDecoding:
    def test_mimetype_known(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            async def on_post(self, req: Request, resp: Response):
                assert req.mimetype is MimeType.JSON

        with api.requests as client:
            headers = dict()
            MimeType.add_to_headers(headers, MimeType.JSON)

            r = client.post("/test", headers=headers)
            validate_response(r)

    def test_mimetype_unknown(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            async def on_post(self, req: Request, resp: Response):
                assert req.mimetype == "application/unknown"

        with api.requests as client:
            headers = dict()
            MimeType.add_to_headers(headers, "application/unknown")

            r = client.post("/test", headers=headers)
            validate_response(r)

    def test_no_media(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            async def on_post(self, req: Request, resp: Response):
                media = await req.media()
                assert media is None

        with api.requests as client:
            r = client.post("/test")
            validate_response(r)

    def test_decode_error(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            async def on_post(self, req: Request, resp: Response):
                media = await req.media()
                assert media is None

        with api.requests as client:
            headers = dict()
            MimeType.add_to_headers(headers, MimeType.JSON)

            r = client.post("/test", headers=headers, data="Not A JSON")

            validate_error(r, error_type=errors_api.RequestValidationError)

    def test_decode_media_loaded(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            async def on_post(self, req: Request, resp: Response):
                loaded = await req.media_loaded()
                media = await req.media()

                assert media is loaded

        with api.requests as client:
            headers = dict()
            MimeType.add_to_headers(headers, MimeType.JSON)

            r = client.post("/test", headers=headers, json={"key": "value"})
            validate_response(r)

    def test_register_mimetype_encoders(self, api: SpanAPI):
        data = [{"key": "value1"}, {"key": "value2"}]

        def csv_encode(data: List[dict]) -> bytes:
            encoded = io.StringIO()
            headers = list(data[0].keys())
            writer = csv.DictWriter(encoded, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)
            return encoded.getvalue().encode()

        def csv_decode(data: bytes) -> List[Dict[str, Any]]:
            csv_file = io.StringIO(data.decode())
            reader = csv.DictReader(csv_file)
            return [row for row in reader]

        api.register_mimetype("text/csv", encoder=csv_encode, decoder=csv_decode)

        @api.route("/test")
        class TestRoute(SpanRoute):
            async def on_post(self, req: Request, resp: Response):
                loaded = await req.media_loaded()
                media = await req.media()

                assert media is loaded
                assert media == loaded == data

                resp.media = media
                resp.mimetype = "text/csv"

        req_data = csv_encode(data)
        r = api.requests.post(
            "/test", headers={"Content-Type": "text/csv"}, data=req_data
        )

        validate_response(r, expected_headers={"Content-Type": "text/csv"})

        resp_data = csv_decode(r.content)
        assert resp_data == data


class TestErrorHandling:
    def test_basic_error(self, api: SpanAPI):
        class TestCustomError(errors_api.APIError):
            http_code = 403
            api_code = 9999

        @api.route("/error")
        class ErrorRoute(SpanRoute):
            async def on_get(self, req: Request, resp: Response):
                raise TestCustomError("Custom Message")

        with api.requests as client:
            r = client.get("/error")
            validate_error(r, TestCustomError)

    def test_unknown_error(self, api: SpanAPI):
        @api.route("/error")
        class ErrorRoute(SpanRoute):
            async def on_get(self, req: Request, resp: Response):
                raise ValueError("Some Error")

        with api.requests as client:
            r = client.get("/error")
            validate_error(r, errors_api.APIError)

    def test_invalid_method_error(self, api: SpanAPI):
        @api.route("/error")
        class ErrorRoute(SpanRoute):
            async def on_get(self, req: Request, resp: Response):
                pass

        with api.requests as client:
            r = client.post("/error")
            validate_error(r, errors_api.InvalidMethodError)

    def test_route_type_data_error(self, api: SpanAPI):
        @api.route("/error")
        class ErrorRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                raise TypeError("Some Error")

        with api.requests as client:
            r = client.get("/error")
            validate_error(r, errors_api.APIError)

    def test_nothing_to_return_error(self, api: SpanAPI):
        @api.route("/error")
        class ErrorRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                pass

        with api.requests as client:
            r = client.get("/error")
            validate_error(r, errors_api.NothingToReturnError)

    @pytest.mark.parametrize("sent_value", [None, [], {}])
    def test_nothing_to_return_error_passed(self, api: SpanAPI, sent_value):
        @api.route("/error")
        class ErrorRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                resp.media = sent_value

        with api.requests as client:
            r = client.get("/error")
            validate_error(r, errors_api.NothingToReturnError)

    def test_send_data_with_error(self, api: SpanAPI):
        class CustomError(errors_api.APIError):
            http_code = 400
            api_code = 1100

        @api.route("/error")
        class ErrorRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                resp.media = {"first": "Billy", "last": "Peake"}
                raise CustomError("Some Custom Error", send_media=True)

        with api.requests as client:
            r = client.get("/error")
            validate_error(r, CustomError)

        assert r.json() == {"first": "Billy", "last": "Peake"}

    def test_send_data_with_error_fails_dump(self, api: SpanAPI):
        class CustomError(errors_api.APIError):
            http_code = 400
            api_code = 1100

        @api.route("/error")
        class ErrorRoute(SpanRoute):
            async def on_get(self, req: Request, resp: Response):
                resp.media = {"first": "Billy", "last": pathlib.Path("/some/path")}
                raise CustomError("Some Custom Error", send_media=True)

        with api.requests as client:
            r = client.get("/error")
            validate_error(r, CustomError)

        assert not r.content


class TestUseSchemaReq:
    @pytest.mark.parametrize(
        "req_load,data_post,data_passed,error",
        [
            # Tests normal loading to dataclass object
            (LoadOptions.VALIDATE_AND_LOAD, HARRY_DUMPED, HARRY, None),
            # Tests validation error on loading bad data
            (
                LoadOptions.VALIDATE_AND_LOAD,
                HARRY_BAD_ID,
                None,
                errors_api.RequestValidationError,
            ),
            # Tests validation error on loading bad data
            (
                LoadOptions.VALIDATE_AND_LOAD,
                DRACO_DUMPED,
                None,
                errors_api.RequestValidationError,
            ),
            # Tests validation error on load for not a json
            (
                LoadOptions.VALIDATE_AND_LOAD,
                "notajson",
                None,
                errors_api.RequestValidationError,
            ),
            # Tests successful validation of incoming data without a load
            (LoadOptions.VALIDATE_ONLY, HARRY_DUMPED, HARRY_DUMPED, None),
            # Tests validation error on validate-only bad data.
            (
                LoadOptions.VALIDATE_ONLY,
                HARRY_BAD_ID,
                None,
                errors_api.RequestValidationError,
            ),
            # Tests validation error on validate-only bad data.
            (
                LoadOptions.VALIDATE_ONLY,
                DRACO_DUMPED,
                None,
                errors_api.RequestValidationError,
            ),
            # Tests validation error on validate for not a json
            (
                LoadOptions.VALIDATE_ONLY,
                "notajson",
                None,
                errors_api.RequestValidationError,
            ),
            # Tests successful ignore of good data
            (LoadOptions.IGNORE, HARRY_DUMPED, HARRY_DUMPED, None),
            # Tests successful ignore of bad data
            (LoadOptions.IGNORE, HARRY_BAD_ID, HARRY_BAD_ID, None),
            # Tests successful ignore of bad data
            (LoadOptions.IGNORE, DRACO_DUMPED, DRACO_DUMPED, None),
        ],
    )
    @pytest.mark.parametrize("bson", [True, False])
    def test_req_load_schema(
        self,
        api: SpanAPI,
        req_load: LoadOptions,
        data_post: dict,
        data_passed: Union[Name, dict],
        error: Optional[Type[errors_api.APIError]],
        bson: bool,
    ):
        if bson and isinstance(data_passed, dict):
            data_passed = RawBSONDocument(BSON.encode(data_passed))

        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(req=NameSchema(), req_load=req_load)
            async def on_post(
                self, req: Request[dict, Union[Name, dict]], resp: Response
            ):
                data = await req.media_loaded()
                if req_load is LoadOptions.IGNORE:
                    assert data == data_passed
                    assert await req.media() == data_passed
                else:
                    assert isinstance(data, type(data_passed))
                    assert data == data_passed

        with api.requests as client:
            if bson:
                if isinstance(data_post, dict):
                    data_post = BSON.encode(data_post)

                r = client.post(
                    "/test",
                    data=data_post,
                    headers={"Content-Type": "application/bson"},
                )
            else:
                r = client.post("/test", json=data_post)

            if error is not None:
                validate_error(r, error)
            else:
                validate_response(r)

    def test_req_load_schema_class(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(req=NameSchema)
            async def on_post(self, req: Request, resp: Response):
                assert await req.media_loaded() == HARRY

        with api.requests as client:
            r = client.post("/test", json=HARRY_DUMPED)
            validate_response(r)

    @pytest.mark.parametrize(
        "data",
        [
            [HARRY_DUMPED, HARRY_DUMPED],
            [
                RawBSONDocument(BSON.encode(HARRY_DUMPED)),
                RawBSONDocument(BSON.encode(HARRY_DUMPED)),
            ],
        ],
    )
    def test_req_load_bson_list(self, api: SpanAPI, data):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(req=NameSchema(many=True))
            async def on_post(self, req: Request, resp: Response):
                assert await req.media_loaded() == [HARRY, HARRY]

        with api.requests as client:
            headers = {"Content-Type": "application/bson"}
            r = client.post("/test", data=encode_bson(data), headers=headers)
            validate_response(r)

    def test_req_schema_class_marshmallow(self, api: SpanAPI):
        class NameSchemaM(marshmallow.Schema):
            id = marshmallow.fields.UUID()
            first = marshmallow.fields.Str()
            last = marshmallow.fields.Str()

        harry_loaded = NameSchemaM().load(HARRY_DUMPED)

        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(req=NameSchemaM())
            async def on_post(self, req: Request, resp: Response):
                assert await req.media_loaded() == harry_loaded

        with api.requests as client:
            r = client.post("/test", json=HARRY_DUMPED)
            validate_response(r)

    def test_req_load_text(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(req=MimeType.TEXT)
            async def on_post(self, req: Request, resp: Response):
                assert await req.media_loaded() == "test_text"

        with api.requests as client:
            r = client.post("/test", data="test_text")
            validate_response(r)

    def test_error_not_a_json(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(req=NameSchema())
            async def on_post(self, req: Request, resp: Response):
                await req.media()

        with api.requests as client:
            r = client.post("/test", data=bytes(14))
            validate_error(r, errors_api.RequestValidationError)


class TestUseSchemaResp:
    @pytest.mark.parametrize(
        "resp_dump,data_send,data_returned,error",
        [
            # Tests normal dumping from dataclass object
            (DumpOptions.DUMP_ONLY, HARRY, HARRY_DUMPED, None),
            # Tests normal dumping from dataclass object missing validation
            (DumpOptions.DUMP_ONLY, DRACO, DRACO_DUMPED, None),
            # Tests normal dumping error from bad uuid
            (DumpOptions.DUMP_ONLY, HARRY_BAD_ID, HARRY_BAD_ID, None),
            # Tests dumping + validation from dataclass object
            (DumpOptions.DUMP_AND_VALIDATE, HARRY, HARRY_DUMPED, None),
            # Tests dumping + validation error
            (
                DumpOptions.DUMP_AND_VALIDATE,
                HARRY_BAD_ID,
                None,
                errors_api.ResponseValidationError,
            ),
            # Tests dumping + validation error
            (
                DumpOptions.DUMP_AND_VALIDATE,
                DRACO,
                None,
                errors_api.ResponseValidationError,
            ),
            # Tests validation success
            (DumpOptions.VALIDATE_ONLY, HARRY_DUMPED, HARRY_DUMPED, None),
            # Tests validation failure
            (
                DumpOptions.VALIDATE_ONLY,
                DRACO_DUMPED,
                None,
                errors_api.ResponseValidationError,
            ),
            # Tests ignore normal
            (DumpOptions.IGNORE, HARRY_DUMPED, HARRY_DUMPED, None),
            # Tests ignore bad data
            (DumpOptions.IGNORE, HARRY_BAD_ID, HARRY_BAD_ID, None),
            # Tests ignore bad data
            (DumpOptions.IGNORE, DRACO_DUMPED, DRACO_DUMPED, None),
        ],
    )
    @pytest.mark.parametrize("bson", [False, True])
    def test_use_schema_resp(
        self,
        api: SpanAPI,
        resp_dump: DumpOptions,
        data_send: Union[Name, dict],
        data_returned: dict,
        error: Optional[Type[errors_api.APIError]],
        bson: bool,
    ):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema(), resp_dump=resp_dump)
            async def on_get(self, req: Request, resp: Response):
                resp.media = data_send

        with api.requests as client:
            if bson:
                headers = {"accept": "application/bson"}
            else:
                headers = {}

            r = client.get("/test", headers=headers)

            if error is not None:
                validate_error(r, error)
            else:
                validate_response(r)

            if error is None:
                if bson:
                    assert dict(RawBSONDocument(r.content)) == dict(
                        RawBSONDocument(BSON.encode(data_returned))
                    )
                else:
                    assert r.json() == data_returned

    def test_resp_schema_class(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema)
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test")
            name: Name = validate_response(r, data_schema=NameSchema())
            assert name == HARRY

    @pytest.mark.parametrize("accept", ["application/bson", "application/json"])
    def test_resp_bson_raw(self, api: SpanAPI, accept):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema(), resp_dump=DumpOptions.IGNORE)
            async def on_get(self, req: Request, resp: Response):
                resp.media = RawBSONDocument(BSON.encode(HARRY_DUMPED))

        with api.requests as client:

            headers = {"Accept": accept}
            r = client.get("/test", headers=headers)
            assert r.headers["content-type"] == accept

            name: Name = validate_response(r, data_schema=NameSchema())
            assert name == HARRY

    def test_resp_bson_encode_error(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema(), resp_dump=DumpOptions.IGNORE)
            async def on_get(self, req: Request, resp: Response):
                resp.media = {"key": fractions.Fraction("1/4")}

        with api.requests as client:

            headers = {"Accept": "application/bson"}
            r = client.get("/test", headers=headers)
            validate_error(r, errors_api.ResponseValidationError)

    def test_resp_schema_class_marshmallow(self, api: SpanAPI):
        class NameSchemaM(marshmallow.Schema):
            id = marshmallow.fields.UUID()
            first = marshmallow.fields.Str()
            last = marshmallow.fields.Str()

        harry_loaded = NameSchemaM().load(HARRY_DUMPED)

        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchemaM())
            async def on_get(self, req: Request, resp: Response):
                resp.media = harry_loaded

        with api.requests as client:
            r = client.get("/test")
            name: Name = validate_response(r, data_schema=NameSchema())
            assert name == HARRY

    def test_use_schema_resp_text(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=MimeType.TEXT)
            async def on_get(self, req: Request, resp: Response):
                resp.text = "response_text"

        with api.requests as client:
            r = client.get("/test")
            validate_response(r)
            assert r.text == "response_text"

    def test_return_bson_types(self, api: SpanAPI):
        uuid_value = uuid.uuid4()
        # bytes_value = b"Some data"
        dt_value = datetime.datetime.utcnow()
        dt_value = dt_value.replace(microsecond=0)
        info_value = {"key": "value"}
        array_value = ["one", "two", "three"]

        @dataclass
        class ResponseData:
            id: uuid.UUID
            dt: datetime.datetime
            # binary: str
            info: Dict[str, str]
            array: List[str]
            empty: Dict[str, str]

        @schema_for(ResponseData)
        class ResponseSchema(DataSchema[ResponseData]):
            pass

        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=ResponseSchema(), resp_dump=DumpOptions.IGNORE)
            async def on_get(self, req: Request, resp: Response):
                resp.media = RawBSONDocument(
                    BSON.encode(
                        {
                            "id": uuid_value,
                            "dt": dt_value,
                            # "binary": bytes_value,
                            "info": info_value,
                            "array": array_value,
                            "empty": {},
                        }
                    )
                )

        with api.requests as client:
            r = client.get("/test")
            loaded: ResponseData = validate_response(
                r,
                data_schema=ResponseSchema(),
                expected_headers={"Content-Type": "application/json"},
            )

            assert loaded.id == uuid_value
            assert loaded.dt == dt_value
            # assert bytes.fromhex(loaded.binary) == bytes_value
            assert loaded.info == info_value
            assert loaded.array == array_value
            assert loaded.empty == {}


class TestProjection:
    def test_only(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.id": 1})
            name: Name = validate_response(r, data_schema=NameSchema(only=["id"]))

            assert isinstance(name.id, uuid.UUID)
            assert name.first is MISSING
            assert name.last is MISSING

    def test_exclude(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.id": 0})
            name: Name = validate_response(r, data_schema=NameSchema(exclude=["id"]))

            assert name.id is MISSING
            assert isinstance(name.first, str)
            assert isinstance(name.last, str)

    def test_lru_cache_hits(self, api: SpanAPI):
        run = 0

        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                hits = max(0, run - 2)

                assert (
                    resp._projection_builder._build_projection_schema.cache_info().hits
                ) == hits
                resp.media = HARRY

        @api.route("/test2")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                # We need to check that the first request for this endpoint does not
                # trigger a hit.
                if run < 2:
                    hits = 9
                else:
                    hits = 9 + run - 2

                assert (
                    resp._projection_builder._build_projection_schema.cache_info().hits
                ) == hits
                resp.media = HARRY

        with api.requests as client:
            for _ in range(10):
                run += 1
                r = client.get("/test", params={"project.id": 1})
                _ = validate_response(r, data_schema=NameSchema(only=["id"]))

            run = 0

            # Check that the cache is endpoint-specific
            for _ in range(10):
                run += 1
                r = client.get("/test2", params={"project.id": 1})
                _ = validate_response(r, data_schema=NameSchema(only=["id"]))

    def test_handle_projection_false(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            """Tests that projection application can be cancelled."""

            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                resp.apply_projection = False
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.id": 0})
            name: Name = validate_response(r, data_schema=NameSchema())

            assert isinstance(name.id, uuid.UUID)
            assert isinstance(name.first, str)
            assert isinstance(name.last, str)

    def test_original_only_kept(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema(only=["first", "last"]))
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.last": 0})
            name: Name = validate_response(r, data_schema=NameSchema(partial=True))

            assert name.id is MISSING
            assert isinstance(name.first, str)
            assert name.last is MISSING

    def test_original_exclude_kept(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema(exclude=["id"]))
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.last": 0})
            name: Name = validate_response(r, data_schema=NameSchema(partial=True))

            assert name.id is MISSING
            assert isinstance(name.first, str)
            assert name.last is MISSING

    def test_client_cannot_override_exclude(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema(exclude=["id"]))
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.id": 1})
            name: Name = validate_response(r, data_schema=NameSchema(partial=True))

            assert name.id is MISSING
            assert name.first is MISSING
            assert name.last is MISSING

    def test_client_cannot_override_only(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema(only=["first", "last"]))
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.id": 1})
            name: Name = validate_response(r, data_schema=NameSchema(partial=True))

            assert name.id is MISSING
            assert name.first is MISSING
            assert name.last is MISSING

    def test_not_int_validation_error(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.id": "blah"})
            validate_error(r, error_type=errors_api.RequestValidationError)

    def test_wrong_int_validation_error(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            @api.use_schema(resp=NameSchema())
            async def on_get(self, req: Request, resp: Response):
                resp.media = HARRY

        with api.requests as client:
            r = client.get("/test", params={"project.id": 3})
            validate_error(r, error_type=errors_api.RequestValidationError)

    def test_not_supported_validation_error(self, api: SpanAPI):
        @api.route("/test")
        class TestRoute(SpanRoute):
            async def on_get(self, req: Request, resp: Response):
                resp.media = {"id": "value"}

        with api.requests as client:
            r = client.get("/test", params={"project.id": 0})
            validate_error(r, error_type=errors_api.RequestValidationError)


class TestPaged:
    def test_paging_attrs(self, api: SpanAPI):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                assert req.paging is not resp.paging
                assert req.paging.offset == resp.paging.offset == 0
                assert req.paging.limit == resp.paging.limit == 2

        with api.requests as client:
            r = client.get("/test")
            validate_response(r)

    @pytest.mark.parametrize("test_obj_name", ["req", "resp"])
    def test_paging_req_error(self, api: SpanAPI, test_obj_name):
        @api.route("/test")
        class PagedTest(SpanRoute):
            async def on_get(self, req: Request, resp: Response):
                error = None
                test_obj = req if test_obj_name == "req" else resp

                try:
                    _ = test_obj.paging
                except TypeError as exc:
                    error = exc

                assert isinstance(error, TypeError)

        with api.requests as client:
            r = client.get("/test")
            validate_response(r)

    @pytest.mark.parametrize(
        "url_params", [{}, {"paging-offset": 0, "paging-limit": 2}]
    )
    def test_get_paged_basic(self, api: SpanAPI, url_params: dict):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                resp.paging.total_items = 10
                resp.media = [
                    {"offset": req.paging.offset},
                    {"offset": req.paging.offset + 1},
                ]

        with api.requests as client:
            i = 0
            page = 1
            r = client.get("/test", params=url_params)
            page_previous = None

            while True:
                validate_response(r)

                data = r.json()
                assert isinstance(data, list)
                assert len(data) == 2
                for obj in data:
                    assert obj["offset"] == i
                    i += 1

                assert r.headers.get("paging-total-items") == "10"
                assert r.headers.get("paging-total-pages") == "5"
                assert r.headers.get("paging-limit") == "2"
                assert r.headers.get("paging-current-page") == str(page)

                if page == 5:
                    assert "paging-next" not in r.headers
                else:
                    assert r.headers.get("paging-next") == (
                        f"http://;/test?paging-offset={i}&paging-limit=2"
                    )

                if page == 1:
                    assert "paging-previous" not in r.headers
                elif page == 2 and not url_params:
                    assert r.headers.get("paging-previous") == (
                        "http://;/test?paging-offset=0&paging-limit=2"
                    )
                else:
                    assert r.headers.get("paging-previous") == page_previous

                next_page_url = r.headers.get("paging-next", None)
                if next_page_url is None:
                    break

                page += 1
                page_previous = r.url
                r = client.get(next_page_url)

        assert i == 10

    def test_get_paged_custom_limit(self, api: SpanAPI):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                resp.paging.total_items = 10
                resp.media = [{"offset": req.paging.offset}]

        with api.requests as client:
            i = 0
            page = 1
            r = client.get("/test", params={"paging-limit": 1})
            page_previous = None

            while True:
                validate_response(r)

                data = r.json()
                assert isinstance(data, list)
                assert len(data) == 1
                for obj in data:
                    assert obj["offset"] == i
                    i += 1

                assert r.headers.get("paging-total-items") == "10"
                assert r.headers.get("paging-total-pages") == "10"
                assert r.headers.get("paging-limit") == "1"
                assert r.headers.get("paging-current-page") == str(page)

                if page == 10:
                    assert "paging-next" not in r.headers
                else:
                    assert r.headers.get("paging-next") == (
                        f"http://;/test?paging-limit=1&paging-offset={i}"
                    )

                if page == 1:
                    assert "paging-previous" not in r.headers
                elif page == 2:
                    assert r.headers.get("paging-previous") == (
                        "http://;/test?paging-limit=1&paging-offset=0"
                    )
                else:
                    assert r.headers.get("paging-previous") == page_previous

                next_page_url = r.headers.get("paging-next", None)
                if next_page_url is None:
                    break

                page += 1
                page_previous = r.url
                r = client.get(next_page_url)

        assert i == 10

    def test_get_paged_custom_offset(self, api: SpanAPI):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                resp.paging.total_items = 10
                resp.media = [
                    {"offset": req.paging.offset},
                    {"offset": req.paging.offset + 1},
                ]

        with api.requests as client:
            i = 5
            page = 3
            r = client.get("/test", params={"paging-offset": 5})
            page_previous = None

            while True:
                validate_response(r)

                data = r.json()
                assert isinstance(data, list)
                assert len(data) == 2
                for obj in data:
                    assert obj["offset"] == i
                    i += 1

                assert r.headers.get("paging-total-items") == "10"
                assert r.headers.get("paging-total-pages") == "5"
                assert r.headers.get("paging-limit") == "2"
                assert r.headers.get("paging-current-page") == str(page)

                if page == 5:
                    assert "paging-next" not in r.headers
                else:
                    assert r.headers.get("paging-next") == (
                        f"http://;/test?paging-offset={i}&paging-limit=2"
                    )

                if page == 3:
                    assert r.headers.get("paging-previous") == (
                        f"http://;/test?paging-offset=3&paging-limit=2"
                    )
                elif page == 4:
                    assert r.headers.get("paging-previous") == (
                        f"http://;/test?paging-offset=5&paging-limit=2"
                    )
                else:
                    assert r.headers.get("paging-previous") == page_previous

                next_page_url = r.headers.get("paging-next", None)
                if next_page_url is None:
                    break

                page += 1
                page_previous = r.url
                r = client.get(next_page_url)

        assert i == 11

    def test_get_paged_limit_error(self, api: SpanAPI):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                paging = req.paging
                paging.total_items = 10
                resp.media = [{"offset": paging.offset}, {"offset": paging.offset + 1}]

        with api.requests as client:
            r = client.get("/test", params={"paging-limit": 3})
            validate_error(r, errors_api.APILimitError)

    def test_paged_from_headers(self, api: SpanAPI):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                paging = resp.paging
                print(paging)
                paging.total_items = 10
                resp.media = [{"offset": paging.offset}, {"offset": paging.offset + 1}]

        with api.requests as client:
            r = client.get("/test", params={"paging-offset": 5})
            paging_info = PagingResp.from_headers(r.headers)

            assert paging_info.limit == 2
            assert paging_info.offset == 5
            assert paging_info.total_items == 10
            assert paging_info.previous is not None
            assert paging_info.next is not None
            assert paging_info.current_page == 3
            assert paging_info.total_pages == 5

    def test_paged_from_headers_first(self, api: SpanAPI):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                paging = resp.paging
                print(paging)
                paging.total_items = 10
                resp.media = [{"offset": paging.offset}, {"offset": paging.offset + 1}]

        with api.requests as client:
            r = client.get("/test")
            paging_info = PagingResp.from_headers(r.headers)

            assert paging_info.limit == 2
            assert paging_info.offset == 0
            assert paging_info.total_items == 10
            assert paging_info.previous is None
            assert paging_info.next is not None
            assert paging_info.current_page == 1
            assert paging_info.total_pages == 5

    def test_paged_from_headers_last(self, api: SpanAPI):
        @api.route("/test")
        class PagedTest(SpanRoute):
            @api.paged(limit=2)
            async def on_get(self, req: Request, resp: Response):
                paging = resp.paging
                print(paging)
                paging.total_items = 10
                resp.media = [{"offset": paging.offset}, {"offset": paging.offset + 1}]

        with api.requests as client:
            r = client.get("/test", params={"paging-offset": 9})
            paging_info = PagingResp.from_headers(r.headers)

            assert paging_info.limit == 2
            assert paging_info.offset == 9
            assert paging_info.total_items == 10
            assert paging_info.previous is not None
            assert paging_info.next is None
            assert paging_info.current_page == 5
            assert paging_info.total_pages == 5


class TestLoadURLParams:
    def test_load_int(self, api: SpanAPI):
        @api.route("/test/{item_id}")
        class PagedTest(SpanRoute):
            async def on_get(self, req: Request, resp: Response, *, item_id: int):
                assert isinstance(item_id, int)

        with api.requests as client:
            r = client.get("/test/10")
            assert r.status_code == 200

    def test_load_uuid(self, api: SpanAPI):
        req_id = uuid.uuid4()

        @api.route("/test/{item_id}")
        class PagedTest(SpanRoute):
            async def on_get(self, req: Request, resp: Response, *, item_id: uuid.UUID):
                assert isinstance(item_id, uuid.UUID)
                assert item_id == req_id

        with api.requests as client:
            r = client.get(f"/test/{req_id}")
            assert r.status_code == 200

    def test_load_uuid_validation_error(self, api: SpanAPI):
        @api.route("/test/{item_id}")
        class PagedTest(SpanRoute):
            async def on_get(self, req: Request, resp: Response, *, item_id: uuid.UUID):
                pass

        with api.requests as client:
            r = client.get(f"/test/NotAnUUID")
            validate_error(r, errors_api.RequestValidationError)

    @pytest.mark.parametrize("id_value", [uuid.uuid4(), 10, "SomeIDName"])
    def test_load_union(self, api: SpanAPI, id_value):
        @api.route("/test/{item_id}")
        class PagedTest(SpanRoute):
            async def on_get(
                self,
                req: Request,
                resp: Response,
                *,
                item_id: Union[uuid.UUID, int, str],
            ):
                print(item_id)
                assert item_id == id_value
                assert item_id.__class__ is id_value.__class__

        with api.requests as client:
            r = client.get(f"/test/{id_value}")
            assert r.status_code == 200

    def test_load_union_validation_error(self, api: SpanAPI):
        @api.route("/test/{item_id}")
        class PagedTest(SpanRoute):
            async def on_get(
                self, req: Request, resp: Response, *, item_id: Union[uuid.UUID, int]
            ):
                pass

        with api.requests as client:
            r = client.get(f"/test/NotAnUUID")
            validate_error(r, errors_api.RequestValidationError)

    @pytest.mark.parametrize(
        "value_in, value_parsed",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
        ],
    )
    def test_load_bool(self, api: SpanAPI, value_in: str, value_parsed: bool):
        @api.route("/test/{value}")
        class PagedTest(SpanRoute):
            async def on_get(self, req: Request, resp: Response, *, value: bool):
                assert value == value_parsed

        with api.requests as client:
            r = client.get(f"/test/{value_in}")
            validate_response(r)
