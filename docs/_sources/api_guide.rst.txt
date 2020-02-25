.. automodule:: spanserver

API Guide
=========

SpanAPI
-------

.. autoclass:: SpanAPI
   :members:

   The ``is_test`` param is added to :func:`SpanAPI.__init__`, and can be accessed
   through ``SpanAPI.IS_TEST`` for flagging that an API is being run as a test.

SpanRoute
---------

.. autoclass:: SpanRoute
   :members:


Request and Response
--------------------

.. autoclass:: Request
    :members:

.. autoclass:: Response
    :members:


Options Enums
-------------

.. autoclass:: LoadOptions
    :members:

.. autoclass:: DumpOptions
    :members:

MimeType
--------

MimeType
--------

.. autoclass:: MimeType
   :members:

   Enum class for the default supported Content-Types / Mimetypes for decoding and
   encoding.

   =========== ======================
   Enum Attr   Text Value
   =========== ======================
   JSON        application/json
   YAML        application/yaml
   BSON        application/bson
   TEXT        text/plain
   =========== ======================

   .. automethod:: is_mimetype

   .. automethod:: from_name

   .. automethod:: to_string

   .. automethod:: add_to_headers

   .. automethod:: from_headers


.. data:: MimeTypeTolerant

   Typing alias for ``Union[MimeType, str, None]``.


Models
------

.. autoclass:: PagingReq
   :members:

   serialized url param example: ::

      {
        "paging-limit": 50,
        "paging-offset": 0
      }

.. autoclass:: PagingResp
   :members:

   serialized header example: ::

      {
         "paging-limit": 50,
         "paging-offset": 150,
         "paging-previous": "https://www.api.com/items?limit=50&offset=200",
         "paging-next": "https://www.api.com/items?limit=50&offset=100",
         "paging-total-items": 234,
         "paging-current-page": 4
         "paging-total-pages": 5
      }

.. autoclass:: Error
   :members:

   serialized example: ::

        {
            "content-type": "application/json",
            "error-name": "RequestValidationError",
            "error-message": "Request data does not match schema.",
            "error-id": "3a7b504b-19f0-473f-a3b0-3dfa5dd128ce",
            "error-code": "1003",
            "error-data": "{\"title\": [\"Missing data for required field.\"]}",
            "content-length": "4"
        }


Documentation Tools
-------------------

.. autoclass:: DocInfo
    :members:


.. autoclass:: DocRespInfo
    :members:


.. autoclass:: ParamInfo
    :members:


.. autoclass:: ParamTypes
    :members:


Typing Aliases
--------------

.. autodata:: RecordType

    Type alias to be used for Mapping-based objects in Req bodies.


.. automodule:: spanserver.errors_api

API Errors
----------

These errors will be automatically returned in response headers if raised within a
route method.

.. autoexception:: APIError

   **http code:** 501

   **api code:** 1000

   Returned when any exception not inherited from APIError is raised from a SpanRoute
   method.

   Init Values / Attributes
       * **message**: ``str``: error message passed back in response

       * **error_data**: ``Optional[dict]``: error data to be passed back in response

       * **send_data**: ``bool``: send regular response data as well as error. If
         ``False``: ``'data'`` object of response is set to ``None``

.. autoexception:: InvalidMethodError
   :members:

   **http code:** 405

   **api code:** 1001

   Returned when :class:`SpanRoute` does not support request method
   (POST/DELETE/GET/etc.).


.. autoexception:: NothingToReturnError

   **http code:** 400

   **api code:** 1002

   Returned when response schema is specified but resp.media is None, an empty list, or
   an empty dict.


.. autoexception:: RequestValidationError

   **http code:** 400

   **api code:** 1003

   Returned when request.media() does not match schema for model supplied by
   :func:`SpanAPI.use_model`


.. autoexception:: APILimitError

   **http code:** 400

   **api code:** 1004

   Request param exceeds limit


.. autoexception:: ResponseValidationError

   **http code:** 400

   **api code:** 1005

   Returned when route method with :func:`SpanAPI.use_schema` has data that fails
   validation.


.. automodule:: spanserver.test_utils

Testing Utilities
-----------------

.. autofunction:: validate_error

.. autofunction:: validate_response

Testing Errors
--------------

.. autoexception:: ContentDecodeError

.. autoexception:: ContentEncodeError

.. autoexception:: NoErrorReturnedError

.. autoexception:: ResponseValidationError

.. autoexception:: StatusMismatchError

.. autoexception:: WrongExceptionError

.. autoexception:: DataValidationError

.. autoexception:: DataTypeValidationError

.. autoexception:: TextValidationError

.. autoexception:: HeadersMismatchError

.. autoexception:: ParamsMismatchError

.. autoexception:: PagingMismatchError

.. autoexception:: URLMismatchError
