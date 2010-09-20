..
	Copyright (c) 2008-2010 Erik Svensson <erik.public@gmail.com>
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

.. exception:: TransmissionError

	This exception is raised when there has occured an error related to
	communication with Transmission. It is a subclass of :exc:`Exception`.

	.. attribute:: original

		The original exception.

Torrent object
==============

Torrent is a class holding the information received from Transmission regarding
a bittorrent transfer. All fetched torrent fields are accessible through this
class using attributes. The attributes use underscore instead of hyphen in the
names though. This class has a few convenience attributes using the torrent
information.

Example:
::

	>>> import transmissionrpc
	>>> t = transmissionrpc.Torrent({'id': 1, 'comment': 'My torrent', 'addedDate': 1232281019})
	>>> t.comment
	'My torrent'
	>>> t.date_added
	datetime.datetime(2009, 1, 18, 13, 16, 59)
	>>>

.. class:: Torrent(fields)

	*fields* should be an dictionary build from the torrent information from an
	Transmission JSON-RPC result.

.. attribute:: Torrent.date_active

	Get the attribute *activityDate* as datetime.datetime.

.. attribute:: Torrent.date_added

	Get the attribute *addedDate* as datetime.datetime.

.. attribute:: Torrent.date_started

	Get the attribute *startDate* as datetime.datetime.

.. attribute:: Torrent.date_done

	Get the attribute *doneDate* as datetime.datetime.

.. attribute:: Torrent.eta

	The attribute *eta* as datetime.timedelta.

.. attribute:: Torrent.progress

	The download progress in percent.

.. attribute:: Torrent.ratio

	The upload/download ratio.

.. attribute:: Torrent.status

	Returns the torrent status. Is either one of 'check pending', 'checking',
	'downloading', 'seeding' or 'stopped'. The first two is related to
	verification.

.. method:: Torrent.files()
.. _transmissionrpc-torrent-files:

	Get list of files for this torrent.

	This function returns a dictionary with file information for each file.
	The file information is has following fields:
	::

		{
			<file id>: {
				'name': <file name>,
				'size': <file size in bytes>,
				'completed': <bytes completed>,
				'priority': <priority ('high'|'normal'|'low')>,
				'selected': <selected for download>
			}

			...
		}

	Example:
	::

		{
			0: {
				'priority': 'normal',
				'completed': 729186304,
				'selected': True,
				'name': 'ubuntu-8.10-beta-desktop-i386.iso',
				'size': 729186304
			}
		}

.. method:: Torrent.format_eta()

	Returns the attribute *eta* formatted as a string.

	* If eta is -1 the result is 'not available'
	* If eta is -2 the result is 'unknown'
	* Otherwise eta is formatted as <days> <hours>:<minutes>:<seconds>.

.. method:: Torrent.update(other)

	Updates the Torrent object with data from *other*.

	*other* should be a Torrent object or torrent information from an
	Transmission JSON-RPC result.

Session object
==============

Session is a class holding the session data for a Transmission session.

Access the session field can be done through attributes.
The attributes available are the same as the session arguments in the
Transmission RPC specification, but with underscore instead of hyphen.
``download-dir`` -> ``download_dir``.

.. class:: Session(fields = {})

	*fields* should be an dictionary build from session information from an
	Transmission JSON-RPC result.

.. method:: Session.update(other)

	Updates the Session object with data from *other*.

	*other* should be a Session object or session information from an
	Transmission JSON-RPC result.

Client object
=============

This is it. This class implements the JSON-RPC protocol to communicate with Transmission.

Torrent ids
-----------

Many functions in Client takes torrent id. A torrent id can either be id or
hashString. When suppling multiple id's it is possible to use a list mixed
with both id and hashString.

Timeouts
--------

In Python 2.6 it is possible to supply a timeout to a HTTP request. This is
accessible through transmissionrpc by either changing the timeout property of
a Client object or supply the named argument ``timeout`` in most methods of
Client. The default timeout is 30 seconds.

.. class:: Client(address='localhost', port=9091, user=None, password=None, timeout=None)

	* *address* and *port* should be the address and port to the Transmission
	  "server", this can be either a Transmission client with rpc access enabled
	  or transmission-daemon.
	* *user* and *password* is the username and password for RPC access
	  if athentication is used.
	* *timeout* is the HTTP request timeout in seconds.

	The argument *verbose* was removed in 0.3, use logging levels instead.

.. attribute:: Client.timeout

	The HTTP request timeout in seconds. Expects anything that can be converted to a float.

	.. NOTE::
	   Timeouts are only applicable in Python 2.6 or later.

.. _transmissionrpc-client-add:
.. method:: Client.add(data, timeout=None, kwargs**)

	Add torrent to transfers list. Takes a base64 encoded .torrent file in
	*data*. Additional arguments are:

	===================== ==== =========== =============================================================
	Argument              RPC  Replaced by Description
	===================== ==== =========== =============================================================
	``bandwidthPriority`` 8 -              Priority for this transfer.
	``download_dir``      1 -              The directory where the downloaded contents will be saved in.
	``filename``          1 -              A filepath or URL to a torrent file or a magnet link.
	``files_unwanted``    1 -              A list of file id's that shouldn't be downloaded.
	``files_wanted``      1 -              A list of file id's that should be downloaded.
	``metainfo``          1 -              The content of a torrent file, base64 encoded.
	``paused``            1 -              If True, does not start the transfer when added.
	``peer_limit``        1 -              Maximum number of peers allowed.
	``priority_high``     1 -              A list of file id's that should have high priority.
	``priority_low``      1 -              A list of file id's that should have low priority.
	``priority_normal``   1 -              A list of file id's that should have normal priority.
	===================== ==== =========== =============================================================

.. method:: Client.add_url(torrent_url, kwargs**)

	Add torrent to transfers list. Takes a file path or url to a .torrent file
	in *torrent_url*.

	For information on additional argument see
	:ref:`Client.add <transmissionrpc-client-add>`.

.. method:: Client.add_uri(uri, kwargs**)

	Add torrent to transfers list. Takes a URI to a .torrent file
	in *uri*. Support for file, http and ftp URI schemes are handled by python's
	urllib2. Otherwise the URI is sent to Transmission as is.

	For information on additional argument see
	:ref:`Client.add <transmissionrpc-client-add>`.

.. method:: Client.remove(ids, delete_data=False, timeout=None)

	Remove the torrent(s) with the supplied id(s). Local data is removed if
	*delete_data* is True, otherwise not.

.. method:: Client.start(ids, timeout=None)

	Start the torrent(s) with the supplied id(s).

.. method:: Client.stop(ids, timeout=None)

	Stop the torrent(s) with the supplied id(s).

.. method:: Client.verify(ids, timeout=None)

	Verify the torrent(s) with the supplied id(s).

.. method:: Client.reannounce(ids, timeout=None):

	Reannounce torrent(s) with provided id(s)

.. method:: Client.info(ids=[], timeout=None)

	Get information for the torrent(s) with the supplied id(s). If *ids* is
	empty, information for all torrents are fetched. See the RPC specification
	for a full list of information fields.

.. _transmissionrpc-client-get_files:
.. method:: Client.get_files(ids=[], timeout=None)

	Get list of files for provided torrent id(s). If *ids* is empty,
	information for all torrents are fetched. This function returns a dictonary
	for each requested torrent id holding the information about the files.

	::

		{
			<torrent id>: {
				<file id>: {
					'name': <file name>,
					'size': <file size in bytes>,
					'completed': <bytes completed>,
					'priority': <priority ('high'|'normal'|'low')>,
					'selected': <selected for download>
				}

				...
			}

			...
		}

	Example:
	::

		{
			1: {
				0: {
					'name': 'ubuntu-8.10-beta-desktop-i386.iso',
					'size': 729186304,
					'completed': 729186304,
					'priority': 'normal',
					'selected': True
				}
			}
		}

.. _transmissionrpc-client-set_files:
.. method:: Client.set_files(items, timeout=None)

	Set file properties. Takes a dictonary with similar contents as the result
	of :ref:`Client.get_files <transmissionrpc-client-get_files>`.

	::

		{
			<torrent id>: {
				<file id>: {
					'priority': <priority ('high'|'normal'|'low')>,
					'selected': <selected for download>
				}

				...
			}

			...
		}

	Example:
	::

		items = {
			1: {
				0: {
					'priority': 'normal',
					'selected': True,
				}
				1: {
					'priority': 'low',
					'selected': True,
				}
			}
			2: {
				0: {
					'priority': 'high',
					'selected': False,
				}
				1: {
					'priority': 'low',
					'selected': True,
				}
			}
		}
		client.set_files(items)

.. method:: Client.list(timeout=None)

	list all torrents, fetching ``id``, ``hashString``, ``name``
	, ``sizeWhenDone``, ``leftUntilDone``, ``eta``, ``status``, ``rateUpload``
	, ``rateDownload``, ``uploadedEver``, ``downloadedEver`` for each torrent.

.. method:: Client.change(ids, timeout=None, kwargs**)

	Change torrent parameters for the torrent(s) with the supplied id's. The
	parameters are:

	============================ ===== =============== =====================================================================================
	Argument                     RPC   Replaced by     Description
	============================ ===== =============== =====================================================================================
	``bandwidthPriority``        5 -                   Priority for this transfer.
	``downloadLimit``            5 -                   Set the speed limit for download in Kib/s.
	``downloadLimited``          5 -                   Enable download speed limiter.
	``files_unwanted``           1 -                   A list of file id's that shouldn't be downloaded.
	``files_wanted``             1 -                   A list of file id's that should be downloaded.
	``honorsSessionLimits``      5 -                   Enables or disables the transfer to honour the upload limit set in the session.
	``ids``                      1 -                   Local download location.
	``peer_limit``               1 -                   The peer limit for the torrents.
	``priority_high``            1 -                   A list of file id's that should have high priority.
	``priority_low``             1 -                   A list of file id's that should have normal priority.
	``priority_normal``          1 -                   A list of file id's that should have low priority.
	``seedRatioLimit``           5 -                   Seeding ratio.
	``seedRatioMode``            5 -                   Which ratio to use. 0 = Use session limit, 1 = Use transfer limit, 2 = Disable limit.
	``speed_limit_down``         1 - 5 downloadLimit   Set the speed limit for download in Kib/s.
	``speed_limit_down_enabled`` 1 - 5 downloadLimited Enable download speed limiter.
	``speed_limit_up``           1 - 5 uploadLimit     Set the speed limit for upload in Kib/s.
	``speed_limit_up_enabled``   1 - 5 uploadLimited   Enable upload speed limiter.
	``uploadLimit``              5 -                   Set the speed limit for upload in Kib/s.
	``uploadLimited``            5 -                   Enable upload speed limiter.
	============================ ===== =============== =====================================================================================

	.. NOTE::
	   transmissionrpc will try to automatically fix argument errors.

.. method:: Client.locate(ids, location, timeout=None)

	Locate the torrent data at ``location``.

.. method:: Client.move(ids, location, timeout=None)

	Move the torrent data to ``location``.

.. method:: Client.blocklist_update(timeout=None):

	Update block list. Returns the size of the block list.

.. method:: Client.port_test(timeout=None):

	Tests to see if your incoming peer port is accessible from the outside
	world.

.. method:: Client.get_session(timeout=None)

	Get the Session object for the client.

.. method:: Client.set_session(timeout=None, **kwargs)

	Set session parameters. The parameters are:

	================================ ===== ================= ==========================================================================================================================
	Argument                         RPC   Replaced by       Description
	================================ ===== ================= ==========================================================================================================================
	``alt_speed_down``               5 -                     Alternate session download speed limit (in Kib/s).
	``alt_speed_enabled``            5 -                     Enables alternate global download speed limiter.
	``alt_speed_time_begin``         5 -                     Time when alternate speeds should be enabled. Minutes after midnight.
	``alt_speed_time_day``           5 -                     Enables alternate speeds scheduling these days.
	``alt_speed_time_enabled``       5 -                     Enables alternate speeds scheduling.
	``alt_speed_time_end``           5 -                     Time when alternate speeds should be disabled. Minutes after midnight.
	``alt_speed_up``                 5 -                     Alternate session upload speed limit (in Kib/s).
	``blocklist_enabled``            5 -                     Enables the block list
	``dht_enabled``                  6 -                     Enables DHT.
	``download_dir``                 1 -                     Set the session download directory.
	``encryption``                   1 -                     Set the session encryption mode, one of ``required``, ``preferred`` or ``tolerated``.
	``incomplete_dir``               7 -                     The path to the directory of incomplete transfer data.
	``incomplete_dir_enabled``       7 -                     Enables the incomplete transfer data directory. Otherwise data for incomplete transfers are stored in the download target.
	``lpd_enabled``                  9 -                     Enables local peer discovery for public torrents.
	``peer_limit``                   1 - 5 peer-limit-global Maximum number of peers
	``peer_limit_global``            5 -                     Maximum number of peers
	``peer_limit_per_torrent``       5 -                     Maximum number of peers per transfer
	``peer_port``                    5 -                     Peer port.
	``peer_port_random_on_start``    5 -                     Enables randomized peer port on start of Transmission.
	``pex_allowed``                  1 - 5 pex-enabled       Allowing PEX in public torrents.
	``pex_enabled``                  5 -                     Allowing PEX in public torrents.
	``port``                         1 - 5 peer-port         Peer port.
	``port_forwarding_enabled``      1 -                     Enables port forwarding.
	``rename_partial_files``         8 -                     Appends ".part" to incomplete files
	``script_torrent_done_enabled``  9 -                     Whether or not to call the "done" script.
	``script_torrent_done_filename`` 9 -                     Filename of the script to run when the transfer is done.
	``seedRatioLimit``               5 -                     Seed ratio limit. 1.0 means 1:1 download and upload ratio.
	``seedRatioLimited``             5 -                     Enables seed ration limit.
	``speed_limit_down``             1 -                     Download speed limit (in Kib/s).
	``speed_limit_down_enabled``     1 -                     Enables download speed limiting.
	``speed_limit_up``               1 -                     Upload speed limit (in Kib/s).
	``speed_limit_up_enabled``       1 -                     Enables upload speed limiting.
	``start_added_torrents``         9 -                     Added torrents will be started right away.
	``trash_original_torrent_files`` 9 -                     The .torrent file of added torrents will be deleted.
	================================ ===== ================= ==========================================================================================================================

	.. NOTE::
	   transmissionrpc will try to automatically fix argument errors.

.. method:: Client.session_stats(timeout=None)

	Returns statistics about the current session in a dictionary.
