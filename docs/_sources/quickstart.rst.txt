.. automodule:: spanserver

Quick Start
===========

Declaring a Service
-------------------

Declare a service with :class:`SpanAPI`, an extension of ``API`` from `responder`_.

.. code-block:: python

    from spanserver import SpanAPI

    grievous = SpanAPI()

``grievous`` now has access to a number of convenience features from spanserver.

Routing Requests
----------------

To use responder's feature set, routes *MUST BE* declared via a subclass of
:class:`SpanRoute`. Methods are added via `Responder's class-view routing convention`_


.. code-block:: python

    from spanserver import SpanRoute, Request, Response

    # set up the route
    @grievous.route("/greet")
    class Greet(SpanRoute):

        async def on_get(self, req: Request, resp: Response):
            data = await req.text
            resp.text = f"{data.upper()}!"


    # test the route
    r = grievous.requests.get("/greet", data="General Kenobi")

    print("STATUS CODE:", r.status_code)
    print("RESP TEXT:", r.text)

Output: ::

    STATUS CODE: 200
    RESP TEXT: GENERAL KENOBI!

.. important::

    All methods for :class:`SpanRoute` must be declared as ``async def on_method(...``.
    Non-async routes will not function properly.

.. note::

    It is recommended that users be familiar with the `responder`_ framework before
    continuing this guide.

Response Errors
---------------

Error information is reported in the response headers. Generic errors
are cast to :class:`errors_api.APIError`. Error information (including a traceback)
is also printed to stderr by the service.


.. code-block:: python

    # set up the route
    @grievous.route("/error")
    class Greet(SpanRoute):

        async def on_get(self, req: Request, resp: Response):
            raise ValueError("Some Unforseen Error")


    # test the route
    r = grievous.requests.get("/error")
    print()
    print("HEADERS:", json.dumps(dict(r.headers), indent=4), sep="\n")

Output: ::

    ERROR: (4b1c12e0-b062-4d66-92cf-66fb0c50788d) - APIError "An unknown error occurred"
    Traceback (most recent call last):
        ...
    ValueError: Some Unforseen Error

    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "APIError",
        "error-message": "An unknown error occurred",
        "error-id": "4b1c12e0-b062-4d66-92cf-66fb0c50788d",
        "error-code": "1000",
        "content-length": "4"
    }

Any error that inherits from :class:`errors_api.APIError` will pass its class name,
api_code, and any supplied error data back through the response headers.

.. code-block:: python

    from spanserver import errors_api


    class CustomError(errors_api.APIError):
        http_code = 401
        api_code = 2001


    # set up the route
    @grievous.route("/error")
    class Greet(SpanRoute):

        async def on_get(self, req: Request, resp: Response):
            raise CustomError("Handled gracefully", error_data={"key": "value"})


    # test the route
    r = grievous.requests.get("/error")
    print()
    print(r)
    print("HEADERS:", json.dumps(dict(r.headers), indent=4), sep="\n")

Output: ::

    ERROR: (0b91983e-779d-40cc-95b2-c7758a68b27f) - CustomError "Handled gracefully"
    Traceback (most recent call last):
        ...
    CustomError: Handled gracefully

    <Response [401]>
    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "CustomError",
        "error-message": "Handled gracefully",
        "error-id": "0b91983e-779d-40cc-95b2-c7758a68b27f",
        "error-code": "2001",
        "error-data": "{\"key\": \"value\"}",
        "content-length": "4"
    }

The status code of the response is altered to the error class' ``http_code`` value.

.. note::

    Any errors that manifest in the deeper code of `responder`_ or its ASGI engine,
    `starlette`_ will not get this neat error data, and instead return a default ``501``
    error with a brief message.

When an error occurs, the payload of the response is set to none (a blank byte string).
If you want to attempt to send back a payload, set ``send_media=`` to ``True`` when
initializing the error. SpanServer will attempt to serialize the payload as long as
no serialization errors occur, and the original error being handled was not a
serialization error.

.. code-block:: python

    # set up the route
    @grievous.route("/error")
    class Greet(SpanRoute):

        async def on_get(self, req: Request, resp: Response):
            resp.media = {"some": "data"}
            raise CustomError("Sending Data", send_media=True)

        # test the route
    r = grievous.requests.get("/error")

    print()
    print(r)
    print("DATA:", json.dumps(dict(r.headers), indent=4), sep="\n")

Output: ::

    ERROR: (0b91983e-779d-40cc-95b2-c7758a68b27f) - CustomError "Sending Data"
    Traceback (most recent call last):
        ...
    CustomError: Sending Data

    <Response [401]>
    DATA:
    {
        "some": "data"
    }


Content-Type Encoding
---------------------

:class:`SpanAPI` natively handles the following http body mimetypes:

    - JSON (application/json)
    - YAML (application/yaml)
    - BSON (application/bson)
    - TEXT (text/plain)

Each of the supported mimetypes is represented as a string Enum in :class:`MimeType`.

The mimetype of request body content is detailed on :func:`Request.mimetype`, which is
determined by the ``'Content-Type'`` header. If it is one of the content types detailed
above, a :class:`MimeType` enum value will be used, otherwise the raw text from the
header will be present.

.. code-block:: python

    from spanserver import MimeType,


    grievous = SpanAPI()

    @grievous.route("/limbs/status")
    class LimbsStatus(SpanRoute):
        async def on_post(self, req: Request, resp: Response) -> None:
            print("MIMETYPE RECEIVED:", req.mimetype)
            data = await req.media()
            resp.media = data

    r = grievous.requests.post(
        url="/limbs/status",
        json={"upper-left": "functional"},
        headers={"Accept": "application/json"}
    )

Output: ::

    MIMETYPE RECEIVED: MimeType.JSON


.. note::

    When selecting a mimetype, spanserver is somewhat forgiving in how the mimetype
    is detailed. All of the following ``'Content-Type'`` values will be treated as
    ``MimeType.JSON``:

        - application/json
        - application/JSON
        - application/jSON
        - application/x-json
        - application/X-JSON
        - json
        - JSON

.. important::
    Non-native mimetypes like ``'text/csv'`` must be an exact string match.

Response mime-types can be set by the request through the ``'Accept'`` request header.

Round-trip YAML example:

.. code-block::

    r = grievous.requests.post(
        url="/limbs/status",
        json={"upper-left": "functional"},
        headers={"Accept": "application/yaml", "Content-Type": "application/yaml"}
    )

    print("RESPONSE YAML:", r.content.decode(), sep="\n")
    print("RESPONSE HEADERS:", r.headers)

Output: ::

    MIMETYPE RECEIVED: MimeType.YAML
    RESPONSE YAML:
    upper-left: functional
    RESPONSE HEADERS: {'content-type': 'application/x-yaml', 'content-length': '23'}

Content-Type Sniffing
---------------------

When ``'Content-Type'`` is not specified in the request header, spanserver will
attempt to decode the content with every available decoder, until one does not throw
an error.

When registering custom encoders, make sure that they throw errors when they should.
For instance, json will decode raw strings to a str object, so the built-in json
decoder throws an error when the resulting object is not a dictionary or list.

Response mimetype is resolved in the following order:

    1. Mimetype set to :func:`Response.mimetype`
    2. Mimetype in `'Accept'`` request header.
    3. JSON for ``dict`` / ``list`` media values
    4. TEXT for ``str`` media.
    5. No action for ``bytes`` media values.

Content-Type Handlers
---------------------

Custom encoders and decoders can be registered with the api, and can replace the default
ones. Let's register a couple to handle text/csv content.

An encoder must take in a data object and turn it into bytes:

.. code-block:: python

    import csv
    import io
    from typing import List, Dict, Any


    def csv_encode(data: List[Dict[str, Any]]) -> bytes:
        encoded = io.StringIO()
        headers = list(data[0].keys())
        writer = csv.DictWriter(encoded, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
        return encoded.getvalue().encode()

Decoders must take in bytes and return python objects.

.. code-block:: python

    def csv_decode(data: bytes) -> List[Dict[str, Any]]:
        csv_file = io.StringIO(data.decode())
        reader = csv.DictReader(csv_file)
        return [row for row in reader]


Now we can register them with our api:

.. code-block:: python

    grievous.register_mimetype("text/csv", encoder=csv_encode, decoder=csv_decode)


Wala! Our api now understands how to encode and decode csv's

.. code-block:: python

    @grievous.route("/arms/status")
    class TestRoute(SpanRoute):
        async def on_post(self, req: Request, resp: Response):
            print("REQ MIMETYPE:", req.mimetype)

            media = await req.media()

            print("REQ DECODED:", media)

            resp.media = media
            resp.mimetype = req.mimetype


    data = [
        {"arm": "upper_left", "status": "intact"},
        {"arm": "upper_right", "status": "destroyed"}
    ]
    req_data = csv_encode(data)

    resp = grievous.requests.post(
        "/arms/status", headers={"Content-Type": "text/csv"}, data=req_data
    )
    resp_data = csv_decode(resp.content)

    print("RESP HEADERS:", resp.headers)
    print("RESP RAW:", resp.content)
    print("RESP DATA:", resp_data)

Output: ::

    REQ MIMETYPE: text/csv
    REQ DECODED: [OrderedDict([('arm', 'upper_left'), ...
    RESP HEADERS: {'content-type': 'text/csv', 'content-length': '54'}
    RESP RAW: b'arm,status\r\nupper_left,intact\r\nupper_right,destroyed\r\n'
    RESP DATA: [OrderedDict([('arm', 'upper_left'), ...

Request Data Validation
-----------------------

Lets design a data object and `marshmallow`_ schema to validate and load it

.. code-block:: python

    from dataclasses import dataclass, asdict
    from marshmallow import Schema, fields, post_load, pre_dump


    @dataclass
    class Enemy:
        title: str
        name: str


    class EnemySchema(Schema):
        title = fields.Str(required=True, description="Military Rank.")
        name = fields.Str(required=True, description="How the enemy is called.")

        @pre_dump
        def convert_dataclass(self, data: Enemy, *, many: bool):
            return asdict(data)

        @post_load
        def load_name(self, data: dict, *, many: bool, partial: bool):
            return Enemy(**data)

We can use the :func:`SpanAPI.use_schema` to have json body information automatically
validated and loaded. Loaded data can be accessed through :func:`Request.media_loaded`.

.. code-block:: python

    # set up the route
    from spanserver import RecordType

    @grievous.route("/quip")
    class QuipRoute(SpanRoute):

        @grievous.use_schema(req=EnemySchema())
        async def on_post(self, req: Request[RecordType, Enemy], resp: Response):
            data = await req.media_loaded()
            print("LOADED DATA:", data)
            resp.text = f"{data.title} {data.name}, you are a bold one!"


    # test the route
    r = grievous.requests.post("/quip", json={"title": "General", "name": "Kenobi"})
    print()
    print(r)
    print("RESPONSE:", r.status_code, r.text)

Output: ::

    LOADED DATA: Enemy(title='General', name='Kenobi')

    <Response [200]>
    RESPONSE: 200 General Kenobi, you are a bold one!

.. note::
    **Request Type Hints**

    In the above example, two type hints were used in the request object:
    ``req: Request[RecordType, Enemy]``

    :class:`Request` is a generic-type class and can be assigned the types that
    :func:`Request.media` and :func:`Request.media_loaded` will produce when invoked. In
    this case, :func:`Request.media` will produce a :class:`RecordType`
    (str, Any Mapping Alias) and :func:`Request.media_loaded` will produce an
    ``Enemy`` object.

    Setting Request media type hints is purely optional, and included to facilitate
    IDE code-completion.

Error information appears in the headers of the response data when request validation
fails. In the example below, the payload is missing the ``title`` field.

.. code-block:: python

    r = grievous.requests.post("/quip", json={"name": "Kenobi"})
    print(json.dumps(dict(r.headers), indent=4)

Output: ::

    ERROR: (3a7b504b-19f0-473f-a3b0-3dfa5dd128ce) - RequestValidationError "...
    Traceback (most recent call last):
       ...
    spanserver.errors_api._classes.RequestValidationError: Request data does not match schema.
    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "RequestValidationError",
        "error-message": "Request data does not match schema.",
        "error-id": "3a7b504b-19f0-473f-a3b0-3dfa5dd128ce",
        "error-code": "1003",
        "error-data": "{\"title\": [\"Missing data for required field.\"]}",
        "content-length": "4"
    }

Request Schema LoadOptions
--------------------------

How request body data is processed can be controlled through the ``req_load=`` param
To only validate the information:

.. code-block:: python

    from spanserver import LoadOptions

    # set up the route
    @grievous.route("/quip")
    class QuipRoute(SpanRoute):

        @grievous.use_schema(req=EnemySchema(), req_load=LoadOptions.VALIDATE_ONLY)
        async def on_post(self, req: Request, resp: Response):
            data = await req.media_loaded()
            print("LOADED DATA:", data)
            resp.text = f"{data['title']} {data['name']}, you are a bold one!"


    # test the route
    r = grievous.requests.post("/quip", json={"title": "general", "name": "Kenobi"})
    print()
    print(r)
    print("RESP TEXT:", r.text)

Output: ::

    LOADED DATA: {'title': 'general', 'name': 'Kenobi'}

    <Response [200]>
    RESP TEXT: general Kenobi, you are a bold one!

The possible options are:

    - **VALIDATE_AND_LOAD**: (default) - Validates and loads data through the supplied
      schema's ``load`` method.

    - **VALIDATE_ONLY**: Validates data through the supplied schema's ``validate``
      method. Decoded json/bson dict/list passed through to :func:`Request.media_loaded`

    - **IGNORE**: Data is not validated or loaded. Decoded json/bson dict/list passed
      through to :func:`Request.media_loaded` param without schema loading. Schema
      only used for API documentation.


Response Data Serialization
---------------------------

:func:`SpanAPI.use_schema` can also be used to automatically serialize outgoing data.

.. code-block:: python

    # set up the route
    @grievous.route("/current_target")
    class QuipRoute(SpanRoute):

        @grievous.use_schema(resp=EnemySchema())
        async def on_get(self, req: Request, resp: Response):
            resp.media = Enemy("General", "Kenobi")


    # test the route
    r = grievous.requests.get("/current_target")
    print()
    print(r)
    print("BODY:", json.dumps(r.json(), indent=4), sep="\n")

Output: ::

    <Response [200]>
    BODY:
    {
        "title": "General",
        "name": "Kenobi"
    }

Response Schema Options
-----------------------

Marshmallow does no validation when serializing objects, if we want to do a validation
of the response data, we can alter the ``resp_dump`` option:

.. code-block:: python

    # set up the route
    @grievous.route("/current_target")
    class QuipRoute(SpanRoute):

        @grievous.use_schema(resp=EnemySchema(), resp_dump=DumpOptions.VALIDATE_ONLY)
        async def on_get(self, req: Request, resp: Response, *, data: dict):
            resp.media = {"title": "General"}

    # test the request
    r = grievous.requests.get("/current_target")
    print()
    print(r)
    print("HEADERS:", json.dumps(dict(r.headers), indent=4), sep="\n")

Output: ::

    ERROR: (1fad52a8-7c18-4440-8f9c-1b2aad1639ac) - ResponseValidationError "Request ...
    Traceback (most recent call last):
        ...
    <Response [400]>

    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "ResponseValidationError",
        "error-message": "Request data does not match schema.",
        "error-id": "1fad52a8-7c18-4440-8f9c-1b2aad1639ac",
        "error-code": "1005",
        "error-data": "{\"name\": [\"Missing data for required field.\"]}",
        "content-length": "20"
    }

This option assumes the data is already in a serialized form.

The possible options are:

    - **DUMP_ONLY**: (default) resp.media is passed to the supplied schema's ``dump``
      method. Marshmallow only performs minimal validation on dump, but if a validation
      error is thrown, the api will return a
      :class:`errors_api.ResponseValidationError`.

    - **DUMP_AND_VALIDATE**: resp.media is passed to the supplied schema's ``dump``
      method. The result is passed to the schema's ``validate`` method. If validation
      errors occur during either step, :class:`errors_api.ResponseValidationError` is
      returned.

    - **VALIDATE_ONLY**: resp.media is passed to the supplied schema's ``validate``
      method. :class:`errors_api.ResponseValidationError` is returned on Validation
      errors.

    - **IGNORE**: No action is taken. Schema only used for API documentation.

.. warning::

    Validating response data can come with a big performance hit. The data is
    serialized first, then *fully deserialized* again to validate it. For large data
    structures, caution is advised.

Response Data Projection
------------------------

When using a response schema, the client can request a projection of the payload body
to trim down the returned data.

To suppress a field, add a url query param: ``'project.{field_name}=0'``. Multiple fields
can be defined this way.

.. code-block:: python

    r = grievous.requests.get("/current_target", params={"project.title": 0})
    print()
    print(r)
    print("BODY:", json.dumps(r.json(), indent=4), sep="\n")

Output: ::

    <Response [200]>
    BODY:
    {
        "name": "Kenobi"
    }

Or a set of fields to keep can be used with ``'project.{field_name}=1'``

.. code-block:: python

    r = grievous.requests.get("/current_target", params={"project.title": 1})
    print()
    print(r)
    print("BODY:", json.dumps(r.json(), indent=4), sep="\n")

Output: ::

    <Response [200]>
    BODY:
    {
        "title": "General"
    }

If you wish to handle projection logic within the route yourself:

.. code-block:: python

    # set up the route
    @grievous.route("/current_target")
    class QuipRoute(SpanRoute):

        @grievous.use_schema(resp=EnemySchema(partial=True))
        async def on_get(self, req: Request, resp: Response):
            print("PROJECTION:")
            print(req.projection)
            resp.apply_projection = False
            resp.media = Enemy("General", "Kenobi")

    r = grievous.requests.get("/current_target", params={"project.title": 1})
    print()
    print(r)
    print("BODY:", json.dumps(r.json(), indent=4), sep="\n")

Output: ::

    "PROJECTION:"
    {"title": 1}

    <Response [200]>
    BODY:
    {
        "title": "General",
        "name": "Kenobi"
    }

The projection is not automatically applied when ``req.apply_projection`` is set to
``False``.

Projection settings are accessed through ``req.projection``, with ``'projection.'``
stripped from the keys.

.. note::

    For nested schemas, sub-fields can be set with dot delimiters, ie:
    ``'project.field.subfield=1'``

.. note::

    While SpanAPI's projection out-performs transmitting unnecessary fields
    to the client, it will never be as fast as a database query implementation, since
    the entire object must still be fetched and deserialized into python objects. When
    response speed is critical, it is recommended that projection logic be applied
    directly in db queries by the route.

    This feature is intended for an out-of-the box solution for proof of concept, or
    endpoints with small payloads and non-critical performance.


URL Param Typing
----------------

Spanserver will automatically decode URL params to any type that can be cast from a
string. Just add it to the type annotation of the parameter.

.. code-block:: python

    ARM_STATUS = {
        1: "Functional",
        2: "Destroyed",
        3: "Destroyed",
        4: "Functional"
    }

    # set up the route
    @grievous.route("/arm/{arm_num}/status")
    class ArmStatusRoute(SpanRoute):

        async def on_get(self, req: Request, resp: Response, *, arm_num: int):
            resp.text = ARM_STATUS[arm_num]

    # test the request
    r = grievous.requests.get("/arm/1/status")
    print(r.text)

    r = grievous.requests.get("/arm/2/status")
    print(r.text)

Output: ::

    Functional
    Destroyed

If a value cannot be cast a :class:`RequestValidationError` will be returned.

.. code-block:: python

    r = grievous.requests.get("/arm/NotAnInt/status")
    print()
    print("HEADERS:")
    print(json.dumps(r.headers, indent=4))

Output: ::

    ERROR: (fc071988-7c11-460b-9aac-e67650bc673f) - RequestValidationError ...
    Traceback (most recent call last):
        ...
    spanserver.errors_api._classes.RequestValidationError: URL param {name} could ...

    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "RequestValidationError",
        "error-message": "URL param {name} could not be cast to {loader}",
        "error-id": "fc071988-7c11-460b-9aac-e67650bc673f",
        "error-code": "1003",
        "content-length": "4"
    }

Unions are also allowed. The method will attempt to cast the param in the order of the
types inside the Union, using the first type that is cast successfully.

.. code-block:: python

    from typing import Union

    ARM_STATUS = {
        1: "Functional",
        2: "Destroyed",
        "upper-left": "Functional",
        "upper-right": "Destroyed"
    }

    # set up the route
    @grievous.route("/arm/{arm_id}/status")
    class ArmStatusRoute(SpanRoute):

        async def on_get(
            self,
            req: Request,
            resp: Response,
            *,
            arm_id: Union[int, str]
        ):
            resp.text = ARM_STATUS[arm_id]

    # test the request
    r = grievous.requests.get("/arm/1/status")
    print(r.text)

    r = grievous.requests.get("/arm/upper-right/status")
    print(r.text)

Output: ::

    Functional
    Destroyed

In the above case it is important that ``int`` be listed first in the Union, since
``str`` will accept anything put in the URL.


Paging
------

Handling long lists of data through batch paging can be easily facilitated through the
:func:`SpanAPI.paged` decorator.

.. code-block:: python


    HANDS = ["TOP-LEFT", "TOP-RIGHT", "BOTTOM-LEFT", "BOTTOM-RIGHT"]


    @grievous.route("/hands")
    class QuipRoute(SpanRoute):

        @grievous.paged(limit=4)
        async def on_get(self, req: Request, resp: Response):
            limit = req.paging.limit
            offset = req.paging.offset

            resp.paging.total_items = len(HANDS)

            try:
                resp.media = HANDS[offset:(offset + limit)]
            except IndexError:
                resp.media = []

In the above example, the maximum request item count per page is set to ``4`` through
the decorator's ``limit=`` param.

The decorator will automatically add offset and limit information to
:func:`Request.paging`, pulled from ``paging-offset`` and ``paging-limit`` request url
parameters.

By setting ``resp.paging.total``, the decorator will automatically calculate a number of
other helpful metrics, like how many total pages there are.

Lets fetch the first page:

.. code-block:: python

    r = grievous.requests.get("/hands", params={"paging-limit": 2})
    print()
    print(r)
    print("DATA:", json.dumps(r.json(), indent=4), sep="\n")
    print("HEADERS:", json.dumps(dict(r.headers), indent=4), sep="\n")

Output: ::

    <Response [200]>
    DATA:
    [
        "TOP-LEFT",
        "TOP-RIGHT"
    ]
    HEADERS:
    {
        "content-type": "application/json",
        "paging-next": "http://;/hands?paging-offset=2&paging-limit=2",
        "paging-current-page": "1",
        "paging-offset": "0",
        "paging-limit": "2",
        "paging-total-pages": "2",
        "paging-total-items": "4",
        "content-length": "25"
    }

The offset is assumed to be 0 if none is passed.

Now we can use ``paging-next`` link to fetch the next two items:

.. code-block:: python

    r = grievous.requests.get(r.headers["paging-next"])
    print()
    print(r)
    print("DATA:", json.dumps(r.json(), indent=4), sep="\n")
    print("HEADERS:", json.dumps(dict(r.headers), indent=4), sep="\n")

Output: ::

    <Response [200]>
    DATA:
    [
        "BOTTOM-LEFT",
        "BOTTOM-RIGHT"
    ]
    HEADERS:
    {
        "content-type": "application/json",
        "paging-previous": "http://;/hands?paging-offset=0&paging-limit=2",
        "paging-current-page": "2",
        "paging-offset": "2",
        "paging-limit": "2",
        "paging-total-pages": "2",
        "paging-total-items": "4",
        "content-length": "31"
    }

.. web links:
.. _responder: https://python-responder.org/en/latest/
.. _Responder's class-view routing convention: https://python-responder.org/en/latest/tour.html#class-based-views
.. _starlette: https://www.starlette.io/
.. _marshmallow: https://marshmallow.readthedocs.io/en/3.0/
