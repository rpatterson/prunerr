..
	Copyright (c) 2008-2011 Erik Svensson <erik.public@gmail.com>
	Licensed under the MIT license.


:mod:`transmissionrpc` --- Module reference
###########################################

.. module:: transmissionrpc
.. moduleauthor:: Erik Svensson <erik.public@gmail.com>

This documentation will not describe all RPC fields in detail. Please refer to
the `RPC specification`_ for more information on RPC data.

.. _RPC specification: http://trac.transmissionbt.com/wiki/rpc

.. contents::
	:depth: 3

Exceptions
==========

.. autoclass:: TransmissionError

	.. attribute:: original

		The original exception.

.. autoclass:: HTTPHandlerError

	.. attribute:: url

		The requested url.

	.. attribute:: code

		HTTP error code.

	.. attribute:: message

		HTTP error message.

	.. attribute:: headers

		HTTP headers.

	.. attribute:: data

		HTTP data.

Torrent object
==============

Torrent is a class holding the information received from Transmission regarding a bittorrent transfer.

Attributes
----------

All fetched torrent fields are accessible through this class using attributes. The attributes use underscore instead of
hyphen in the names though. This class has a few convenience attributes using the torrent information.

Example:
::

	>>> import transmissionrpc
	>>> t = transmissionrpc.Torrent(None, {'id': 1, 'comment': 'My torrent', 'addedDate': 1232281019})
	>>> t.comment
	'My torrent'
	>>> t.date_added
	datetime.datetime(2009, 1, 18, 13, 16, 59)
	>>>

Mutators
--------

Some attributes can be changed, these are called mutators. These changes will be sent to the server when changed.
To reload information from Transmission use ``update()``.

Example:
::

	>>> import transmissionrpc
	>>> c = transmissionrpc.Client()
	>>> t = c.get_torrent(0)
	>>> t.peer_limit
	10
	>>> t.peer_limit = 20
	>>> t.update()
	>>> t.peer_limit
	20

Reference
---------

.. autoclass:: Torrent
	:members:

Session object
==============

Session is a class holding the session data for a Transmission session.

Attributes
----------

Access the session field can be done through attributes.
The attributes available are the same as the session arguments in the
Transmission RPC specification, but with underscore instead of hyphen.
``download-dir`` -> ``download_dir``.

Reference
---------

.. autoclass:: Session
	:members:

Client object
=============

This class implements the JSON-RPC protocol to communicate with Transmission.

Torrent ids
-----------

Many functions in Client takes torrent id. A torrent id can either be id or
hashString. When supplying multiple id's it is possible to use a list mixed
with both id and hashString.

Timeouts
--------

In Python 2.6 it is possible to supply a timeout to a HTTP request. This is
accessible through transmissionrpc by either changing the timeout property of
a Client object or supply the named argument ``timeout`` in most methods of
Client. The default timeout is 30 seconds.

Reference
---------

.. autoclass:: Client
	:members:
