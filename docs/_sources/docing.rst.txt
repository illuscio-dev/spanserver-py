.. automodule:: spanserver

Generating Documentation
========================

SpansServer offers automatic documentation of your API by generating `openapi v3`_
documentation which can be displayed by tools like `swagger`_ and `redoc`_.

Spanserver still supports Responder's method of `writing openapi yaml in docstrings`_,
but also introduces it's own set of convenience functions.

Basic API Information
---------------------

The API title, description and version can all be passed to the init method of
:class:`SpanAPI`.

.. code-block:: python

    from spanserver import SpanRoute, Request, Response, SpanAPI


    grievous = SpanAPI(
        title="Grievous", description="A four-armed sickly general.", version="1.0.0", openapi="3.0.0"
    )

    print(grievous.openapi)

Output: ::

    info:
      description: A four-armed sickly general.
      title: Grievous
      version: 1.0.0
    openapi: 3.0.0


Route Method
------------

Summaries and descriptions for routes will be pulled directly from the docstrings.

.. code-block:: python

    # set up the route
    @grievous.route("/greet")
    class Greet(SpanRoute):
        async def on_get(self, req: Request, resp: Response):
            """
            Provoke a greeting.

            Grievous likes to shout things. He is a bold one.
            """
            # route logic goes here.

    print(grievous.openapi)

Output: ::

    info:
      ...
    paths:
      /greet:
        get:
          description: Grievous likes to shout things. He is a bold one.
          responses:
            '200':
              description: Ok.
            default:
              description: Error.
              headers:
                error-code:
                  description: An API error code that identifies the error-type.
                  required: true
                  schema:
                    default: 1000
                    type: integer
                error-data:
                  description: 'JSON-serialized data about the error. For instance: request
                    body validation errors will return a dict with details about all offending
                    fields.'
                  required: false
                  schema:
                    format: dict
                    type: string
                error-id:
                  description: A unique ID with details about this error. Please reference
                    when reporting errors.
                  required: false
                  schema:
                    format: uuid
                    type: string
                error-message:
                  description: Message containing information about the error.
                  required: true
                  schema:
                    default: An unknown error has occurred.
                    type: string
                error-name:
                  description: Human-readable error name.
                  required: true
                  schema:
                    default: APIError
                    type: string
          summary: Provoke a greeting.


Wow! That's a lot of info. Let's make a quick breakdown of what got added automatically:

    - The route's ``summary`` is pulled from the first paragraph of the docstring.

    - The route's description is pulled from all subsequent paragraphs.

    - Default elements detailed below.


Default Documentation
---------------------

Some elements are added by default when no explicit configuration is given:

    - A default response of ``'200'`` is generated when no other non-error response is
      specified.

    - A ``'default'`` error response is generated when no other error response is
      specified.

    - A default description ``'Ok.'`` is given to any non-error response codes without
      a description

    - A default description ``'Error.'`` is given to any error response codes without
      a description

    - Response headers for spanserver-style errors are automatically added to any error
      response codes.


What is an error response?
--------------------------

Spanserver will consider any response code between 400 and 599 to be an error, and
automatically add response header documentation / default response descriptions
accordingly.

Non-default Responses
---------------------

We can add information about a route's http method by inserting a ``Document`` class
into the :class:`SpanRoute` we wish to document, and setting a :class:`DocInfo` object
to the method's name.

:class:`DocRespInfo` is used to add information about each response code.


.. code-block:: python

    from spanserver import DocInfo, DocRespInfo

    # set up the route
    @grievous.route("/greet")
    class Greet(SpanRoute):
        async def on_get(self, req: Request, resp: Response):
            """
            Provoke a greeting.

            Grievous likes to shout things. He is a bold one.
            """
            # route logic goes here.

        class Document:
            get = DocInfo(
                responses={
                    201: DocRespInfo(
                        description="Created."
                    )
                }
            )

    print(grievous.openapi)

Output: ::

    info:
      ...
    paths:
      /greet:
        get:
          description: Grievous likes to shout things. He is a bold one.
          responses:
            '201':
              description: Created.
            default:
              ...
          summary: Provoke a greeting



Schemas
-------

Schemas are automatically added to the documentation when invoked through
:func:`SpanAPI.use_schema`

.. code-block:: python

    from spanserver import MimeType
    from dataclasses import dataclass, asdict
    from marshmallow import Schema, fields, post_load, pre_dump


    @dataclass
    class Enemy:
        title: str
        name: str


    class EnemySchema(Schema):
        """Pesky Jedi scum who can add a lightsaber to Grievous' collection"""
        title = fields.Str(required=True, description="Military Rank.")
        name = fields.Str(required=True, description="How the enemy is called.")

        @pre_dump
        def convert_dataclass(self, data: Enemy, *, many: bool):
            return asdict(data)

        @post_load
        def load_name(self, data: dict, *, many: bool):
            return Enemy(**data)

        # set up the route
    @grievous.route("/quip")
    class QuipRoute(SpanRoute):

        @grievous.use_schema(req=EnemySchema(), resp=MimeType.TEXT)
        async def on_post(self, req: Request, resp: Response):
            """Make a snide remark at an enemy."""
            # route logic goes here.

    print(grievous.openapi)

Output: ::

    components:
      schemas:
        EnemyPostReq1:
          properties:
            name:
              description: How the enemy is called.
              type: string
            title:
              description: Military Rank.
              type: string
          required:
          - name
          - title
          type: object
    info:
        ...
    paths:
      /greet:
        ...
      /quip:
        post:
          requestBody:
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/EnemyPostReq1'
          responses:
            '200':
              content:
                text/plain:
                  schema:
                    type: string
              description: Ok.
            default:
              description: Error.
              headers:
                ...
          summary: Make a snide remark at an enemy.
          tags:
          - Enemies
    tags:
    - description: Pesky Jedi scum who can add a lightsaber to Grievous' collection.
      name: Enemies

The following elements have been added:

    - ``'EnemyPostReq1'`` has been registered under ``components.schemas``.

    - Schema field descriptions are pulled into the spec.

    - A reference to the schema has been placed under
      ``post.requestBody.content.application/json.schema``

    - The ``'200'`` response has been marked as being ``'text/plain'`` content return
      with the corresponding schema. This comes from using ``MimeType.TEXT`` as the
      response schema for the route.

    - An ``'Enemies'`` tag has been registered with a description from the Schema's
      docstring, and added to the appropriate route's


Schema names can be customized via the ``req_name=`` and ``resp_name_`` params of
:func:`SpanAPI.use_schema.`

Automatic names are generated with the following pattern: ::

    {Schema Name Minus "Schema"}{HTTP Method}{Increasing Number}

.. note::

    Schema spec rendering is handled via `api_spec`_. Please see more details there.

.. note::

    `Grahamcracker`_ is a dataclass / marshmallow library built for use with SpanServer
    that has a number of convenience features for documenting schema descriptions and
    fields directly in a dataclass.

Example Data
------------

Example data can also be passed by declaring a ``Document`` class in the
:class:`SpanRoute`.

.. code-block:: python

    @grievous.route("/quip")
    class QuipRoute(SpanRoute):

        @grievous.use_schema(req=EnemySchema(), resp=MimeType.TEXT)
        async def on_post(self, req: Request, resp: Response):
            """Make a snide remark at an enemy."""
            # route logic goes here.

        class Document:
            post = DocInfo(
                req_example=Enemy("General", "Kenobi"),
                responses={
                    201: DocRespInfo(
                        description="Created.",
                        example="General Kenobi, you are a bold one!"
                    )
                }
            )

    print(grievous.openapi)


Output: ::

    components:
      ...
    info:
      ...
    openapi: 3.0.0
    paths:
      /quip:
        post:
          requestBody:
            content:
              application/json:
                example:
                  name: Kenobi
                  title: General
                schema:
                  $ref: '#/components/schemas/EnemyPostReq2'
          responses:
            '201':
              content:
                text/plain:
                  example: General Kenobi, you are a bold one!
                  schema:
                    type: string
              description: Created.
            default:
              ...
          tags:
          - Enemies
    tags:
    - description: Pesky Jedi scum who can add a lightsaber to Grievous' collection.
      name: Enemies


URL Parameters
--------------

Parameters declared in the route method's signature with type annotations will be added
to the openapi spec automatically.

.. code-block:: python

    from typing import Union

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
            # route logic goes here.

    print(grievous.openapi)

Output: ::

    components:
      ...
    info:
      ...
    openapi: 3.0.0
    paths:
      ...
      /arm/{arm_id}/status:
        get:
          parameters:
          - in: path
            name: arm_id
            required: true
            schema:
              anyOf:
              - type: integer
              - type: string
          responses:
            ...
    ...

Paging Parameters
-----------------

When using :func:`SpanAPI.paged`, paging url and response header params are
automatically added to the spec.

.. code-block:: python

    @grievous.route("/hands")
    class QuipRoute(SpanRoute):

        @grievous.paged(limit=4)
        async def on_get(self, req: Request, resp: Response):
            # route logic goes here.

    print(grievous.openapi)

Output: ::

    info:
      ...
    openapi: 3.0.0
    paths:
      /hands:
        get:
          parameters:
          - description: Index of first item to be returned in response body.
            in: query
            name: paging-offset
            required: false
            schema:
              default: 0
              type: integer
          - description: Maximum number of items allowed in response body.
            in: query
            name: paging-limit
            required: false
            schema:
              maximum: 4
              type: integer
          responses:
            '200':
              description: Ok.
              headers:
                paging-current-page:
                  description: Page number of item set in response body given current
                    limit-per-page.
                  required: true
                  schema:
                    type: integer
                paging-limit:
                  description: Maximum number of items allowed in response body.
                  required: true
                  schema:
                    maximum: 4
                    type: integer
                paging-next:
                  description: URL to next page.
                  required: true
                  schema:
                    type: string
                paging-offset:
                  description: Index of first item returned in response body.
                  required: true
                  schema:
                    default: 0
                    type: integer
                paging-previous:
                  description: URL to previous page.
                  required: true
                  schema:
                    type: string
                paging-total-items:
                  description: Total number of items that match request.
                  required: true
                  schema:
                    type: integer
                paging-total-pages:
                  description: Total number of pages that match request given current
                    limit-per-page.
                  required: true
                  schema:
                    type: integer
            default:
              description: Error.
              headers:
                error-code:
                ...

Paging params are not added to responses with error status codes.

Custom Parameters
-----------------

Custom parameters can be added through the ``Document`` class declaration.

.. code-block:: python

    from spanserver import ParamInfo, ParamTypes


    @grievous.route("/minions")
    class MinionCount(SpanRoute):
        async def on_get(self, req: Request, resp: Response):
            # route logic goes here.

        class Document:
            get = DocInfo(
                req_params=[
                    ParamInfo(
                        param_type=ParamTypes.QUERY,
                        name="droid-model",
                        decode_types=[str],
                        description="Model of droid to get current count of.",
                    )
                ]
            )

    print(grievous.openapi)

Output: ::

    info:
      ...
    openapi: 3.0.0
    paths:
      /minions:
        get:
          parameters:
          - description: Model of droid to get current count of.
            in: query
            name: droid-model
            required: true
            schema:
              type: string
          responses:
            ...

:class:`DocRespInfo` can also store response headers in its ``params`` field.


.. _redoc: https://github.com/Redocly/redoc
.. _swagger: https://swagger.io/tools/swaggerhub/hosted-api-documentation/
.. _openapi v3: https://swagger.io/specification/
.. _writing openapi yaml in docstrings: https://python-responder.org/en/latest/tour.html#openapi-schema-support
.. _api_spec: https://apispec.readthedocs.io/en/stable/
.. _Grahamcracker: https://illuscio-dev-grahamcracker-py.readthedocs-hosted.com/en/latest/
