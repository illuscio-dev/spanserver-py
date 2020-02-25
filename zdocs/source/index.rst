.. islelib documentation master file, created by
   sphinx-quickstart on Mon Oct  1 00:18:03 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. automodule:: spanserver

SpanServer
==========

.. image:: http://getdrawings.com/vectors/quill-vector-1.png
   :width: 1600
   :height: 1600
   :scale: 13%

.. toctree::
   :maxdepth: 3
   :caption: Contents:

   ./quickstart.rst
   ./testing.rst
   ./docing.rst
   ./api_guide.rst

What Can it do for Me?
----------------------

``spanserver`` is an extension of `responder`_ for services that focus on sending and
receiving structured data.

Spanserver adds the following features:

   - Uniform method for raising and communicating errors through response headers.
   - In-line data validation, serialization, and deserialization via
     `marshmallow`_ schemas.
   - Handles `mongoDB`_ BSON data natively in http bodies.
   - Automatic generation of openapi v3 docs with even more minimal overhead than native
     `responder`_.
   - Uniform way of handling paged endpoints through request params and response
     headers.
   - Automatic decoding of url path parameters through type-hinting.
   - Adds type hinting to all methods and objects for better code-completion when
     using an IDE.
   - Part of a larger family of libraries that handle http clients, REST services,
     and consumer services.

The Spanreed Family
-------------------

Spanreed is a collection of libraries designed to work together and offer a cohesive
set of solutions for writing a microservice-based backend. Spanreed libraries all
understand a core set of conventions for common problems like paging, errors, and data
validation / loading.

To learn more, see `Spanreed's home-page`_

Background Reading
------------------

Before starting, it is recommended you familiarize yourself with the following
libraries:

   - `responder`_ - the library spanserver is based on.
   - `marshmallow`_ - data serialization / deserialization library.

**This library requires python 3.7++**

.. web links:
.. _responder: https://python-responder.org/en/latest/
.. _grahamcracker: https://illuscio-dev-grahamcracker-py.readthedocs-hosted.com/en/latest/
.. _marshmallow: https://marshmallow.readthedocs.io/en/3.0/
.. _mongoDB: https://www.mongodb.com/
.. _Spanreed's home-page:
