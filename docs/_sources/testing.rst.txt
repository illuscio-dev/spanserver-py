Testing Utilities
=================

Spanserver comes with some testing

Testing Basics
--------------

See `responder's documentation`_ for testing basics.

Validating Responses
--------------------

:func:`test_utils.validate_response` can validate all the basic features of a response:

.. code-block:: python

    from spanserver import test_utils

    @grievous.route("/enemies")
    class QuipRoute(SpanRoute):
        @grievous.use_schema(req=EnemySchema(), resp=EnemySchema())
        async def on_post(self, req: Request[RecordType, Enemy], resp: Response):
            data = await req.media_loaded()
            resp.status_code = 201
            resp.media = data

    r = grievous.requests.post("/enemies", json={"title": "General", "name": "Kenobi"})

    test_utils.validate_response(
        r,
        valid_status_codes=201,
        data_schema=EnemySchema(),
        expected_headers={"Content-Type": "application/json"}
    )

Output: ::

    HEADERS:
    {
        "content-type": "application/json",
        "content-length": "35"
    }
    JSON:
    {
        "title": "General",
        "name": "Kenobi"
    }

In this example the following was checked:

    - Response status was 201
    - Response content could be loaded by ``EnemySchema()``
    - Response has a ``'Content-Type'`` header with a value of ``'application/json'``

The response code, headers, and content are printed during the validation process.

If any of these criteria were to fail, an error is thrown:

.. code-block:: python

    r = grievous.requests.post("/enemies", json={"title": "General"})

    test_utils.validate_response(
        r,
        valid_status_codes=201,
        data_schema=EnemySchema(),
        expected_headers={"Content-Type": "application/json"}
    )

Output: ::

    RESPONSE: <Response [400]>
    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "RequestValidationError",
        "error-message": "Request data does not match schema.",
        "error-id": "d4ecfc47-210c-418f-b96f-9a0b6aea6f1c",
        "error-code": "1003",
        "error-data": "{\"name\": [\"Missing data for required field.\"]}",
        "content-length": "4"
    }
    JSON:
    null
    Traceback (most recent call last):
        ...
    spanserver...StatusMismatchError: Got status code: 400. Expected: (201,)

Validating Errors
-----------------

When an API error is expected in the response headers, :func:`test_utils.validate_error`
can be used to validate that the correct error has been returned.

.. code-block:: python

    from spanserver import errors_api

    error = test_utils.validate_error(r, error_type=errors_api.RequestValidationError)
    print("ERROR DATA:", error)

Output: ::

    RESPONSE: <Response [400]>
    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "RequestValidationError",
        "error-message": "Request data does not match schema.",
        "error-id": "d4ecfc47-210c-418f-b96f-9a0b6aea6f1c",
        "error-code": "1003",
        "error-data": "{\"name\": [\"Missing data for required field.\"]}",
        "content-length": "4"
    }
    JSON:
    null

    ERROR DATA: Error(name='RequestValidationError', message='Request data does not ...

When the correct error is not encountered, an error is raised:

.. code-block::

    test_utils.validate_error(r, error_type=errors_api.NothingToReturnError)

Output: ::

    RESPONSE: <Response [400]>
    HEADERS:
    {
        "content-type": "application/json",
        "error-name": "RequestValidationError",
        "error-message": "Request data does not match schema.",
        "error-id": "d4ecfc47-210c-418f-b96f-9a0b6aea6f1c",
        "error-code": "1003",
        "error-data": "{\"name\": [\"Missing data for required field.\"]}",
        "content-length": "4"
    }
    JSON:
    null
    Traceback (most recent call last):
        ...
    ....WrongExceptionError: Expected NothingToReturnError. Got RequestValidationError



.. _responder's documentation: https://python-responder.org/en/latest/tour.html#using-requests-test-client
