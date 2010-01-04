:mod:`transmissionrpc` --- Module reference
===========================================

.. module:: transmissionrpc
.. moduleauthor:: Erik Svensson <erik.public@gmail.com>

This documentation will not describe all RPC fields in detail. Please refer to
the `RPC specification`_ for more information on RPC data.

.. _RPC specification: http://trac.transmissionbt.com/wiki/rpc

.. contents::
   :depth: 3

Exceptions
----------

.. exception:: TransmissionError

    This exception is raised when there has occured an error related to
    communication with Transmission. It is a subclass of :exc:`Exception`.

    .. attribute:: original

        The original exception.

Torrent object
--------------

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
--------------

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
-------------

This is it. This class implements the JSON-RPC protocol to communicate with Transmission.

.. _transmissionrpc-client-id-note:
.. note::
    Many functions in Client takes torrent id. A torrent id can either be id or
    hashString. When suppling multiple id's it is possible to use a list mixed
    with both id and hashString.

.. class:: Client(address='localhost', port=9091, user=None, password=None)

    * *address* and *port* should be the address and port to the Transmission
      "server", this can be either a Transmission client with rpc access enabled
      or transmission-daemon.
    * *user* and *password* is the username and password for RPC access
      if athentication is used.
    
    The argument *verbose* was removed in 0.3, use logging levels instead.

.. _transmissionrpc-client-add:
.. method:: Client.add(data, kwargs**)

    Add torrent to transfers list. Takes a base64 encoded .torrent file in
    *data*. Additional arguments are:

    * `download_dir`, The directory where the downloaded contents will be
      saved in.
    * `files_unwanted`, A list of file index not to download.
    * `files_wanted`, A list of file index to download.
    * `paused`, Whether to pause or start the transfer on add.
    * `peer_limit`, Limits the number of peers for this transfer.
    * `priority_high`, A list of file index with high priority.
    * `priority_low`, A list of file index with low priority.
    * `priority_normal`, A list of file index with normal priority.
    
    `files_unwanted`, `files_wanted`, `priority_high`, `priority_low`
    , `priority_normal` are new in RPC protocol version 5.

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

.. method:: Client.remove(ids, delete_data=False)

    Remove the torrent(s) with the supplied id(s). Local data is removed if
    *delete_data* is True, otherwise not.

.. method:: Client.start(ids)

    Start the torrent(s) with the supplied id(s).

.. method:: Client.stop(ids)

    Stop the torrent(s) with the supplied id(s).

.. method:: Client.verify(ids)

    Verify the torrent(s) with the supplied id(s).

.. method:: Client.info(ids=[])

    Get information for the torrent(s) with the supplied id(s). If *ids* is
    empty, information for all torrents are fetched. See the RPC specification
    for a full list of information fields.

.. _transmissionrpc-client-get_files:
.. method:: Client.get_files(ids=[])

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
.. method:: Client.set_files(items)

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

.. method:: Client.list()

    list all torrents, fetching ``id``, ``hashString``, ``name``
    , ``sizeWhenDone``, ``leftUntilDone``, ``eta``, ``status``, ``rateUpload``
    , ``rateDownload``, ``uploadedEver``, ``downloadedEver`` for each torrent.

.. method:: Client.change(ids, kwargs**)

    Change torrent parameters for the torrent(s) with the supplied id's. The
    parameters are:

    * ``bandwidthPriority``, Priority for this transfer.
    * ``downloadLimit``, Set the speed limit for download in Kib/s.
    * ``downloadLimited``, Enable download speed limiter.
    * ``files_wanted``, A list of file id's that should be downloaded.
    * ``files_unwanted``, A list of file id's that shouldn't be downloaded.
    * ``honorsSessionLimits``, Enables or disables the transfer to honour the
      upload limit set in the session.
    * ``location``, Local download location.
    * ``peer_limit``, The peer limit for the torrents.
    * ``priority_high``, A list of file id's that should have high priority.
    * ``priority_normal``, A list of file id's that should have normal priority.
    * ``priority_low``, A list of file id's that should have low priority.
    * ``seedRatioLimit``, Seeding ratio.
    * ``seedRatioMode``, Which ratio to use. 0 = Use session limit, 1 = Use
      transfer limit, 2 = Disable limit.
    * ``uploadLimit``, Set the speed limit for upload in Kib/s.
    * ``uploadLimited``, Enable upload speed limiter.
    
    Following arguments where renamed in RPC protocol version 5.
    
    * ``speed_limit_up`` is now called ``uploadLimit`` 
    * ``speed_limit_up_enable`` is now called ``uploadLimited``
    * ``speed_limit_down`` is now called ``downloadLimit``
    * ``speed_limit_down_enable`` is now called ``downloadLimited``
    
    .. NOTE::
       transmissionrpc will try to automatically fix argument errors.

.. method:: Client.locate(ids, location)
    
    Locate the torrent data at ``location``.

.. method:: Client.move(ids, location)
    
    Move the torrent data to ``location``.

.. method:: Client.get_session()

    Get the Session object for the client.

.. method:: Client.set_session()

    Set session parameters. The parameters are:

    * ``alt_speed_down``, max global download speed (in K/s).
    * ``alt_speed_enabled``, True means use the alt speeds.
    * ``alt_speed_time_begin``, when to turn on alt speeds (units: minutes after midnight).
    * ``alt_speed_time_day``, what day(s) to turn on alt speeds (look at tr_sched_day).
    * ``alt_speed_time_enabled``, True means the scheduled on/off times are used.
    * ``alt_speed_time_end``, when to turn off alt speeds (units: same).
    * ``alt_speed_up``, max global upload speed (in K/s).
    * ``blocklist_enabled``, Enabled block list.
    * ``download_dir``, Default download dir.
    * ``dht_enabled``, Enable DHT.
    * ``encryption``, Level of encryption. Should be one of ``required``, ``preferred`` or ``tolerated``.
    * ``peer_limit_global``, Maximum number of peers.
    * ``peer_limit_per_torrent``, Maximum number of peers per torrent.
    * ``pex_enabled``, Allow pex in public torrents.
    * ``peer_port``, Set the port number.
    * ``peer-port-random-on-start``, Ranomize port peer port om launch.
    * ``port_forwarding_enabled``, Enabled port forwarding.
    * ``seedRatioLimit``, Limits how much to seed, where 1.0 is as much as you downloaded.
    * ``seedRatioLimited``, Enables seed limiting.
    * ``speed_limit_down``, Set the global download speed limit in Kib/s.
    * ``speed_limit_down_enabled``, Enables the global download speed limiter.
    * ``speed_limit_up``, Set the global upload speed limit in Kib/s.
    * ``speed_limit_up_enabled``, Enables the global upload speed limiter.
    
    Following arguments where renamed in RPC protocol version 5.
    
    * ``peer_limit`` is now called ``peer_limit_global``
    * ``pex_allowed`` is now called ``pex_enabled`` 
    * ``port`` is now called ``peer_port``
    
    .. NOTE::
       transmissionrpc will try to automatically fix argument errors.

.. method:: Client.session_stats()

    Returns statistics about the current session in a dictionary.

