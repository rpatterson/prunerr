:mod:`transmissionrpc` --- Transmission bittorent API
=====================================================

.. module:: transmissionrpc
.. moduleauthor:: Erik Svensson <erik.public@gmail.com>

Please have the Transmission specification ready. It should be available
`here <http://trac.transmissionbt.com/browser/trunk/doc/rpc-spec.txt>`_.

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
class using attributes. This class has a few convenience properties using the
torrent information.

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

.. class:: Client(address='localhost', port=9091, user=None, password=None, verbose=False)

    * *address* and *port* should be the address and port to the Transmission
      "server", this can be either a Transmission client with rpc access enabled
      or transmission-daemon.
    * *user* and *password* is the username and password for RPC access
      if password protection is used.
    * If *verbose* is `True` request data is logged using logging at info level.

.. _transmissionrpc-client-add:
.. method:: Client.add(data, kwargs**)

    Add torrent to transfers list. Takes a base64 encoded .torrent file in
    *data*. Additional arguments are:

    * `paused`, Whether to pause or start the transfer on add.
    * `download_dir`, The directory where the downloaded contents will be
      saved in.
    * `peer_limit`, Limits the number of peers for this transfer.

.. method:: Client.add_url(torrent_url, kwargs**)

    Add torrent to transfers list. Takes a file path or url to a .torrent file
    in *torrent_url*.
    
    For information on addition argument see :ref:`Client.add <transmissionrpc-client-add>`.

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
    empty, information for all torrents are fetched.

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

    list all torrents, fetching ``id``, ``hashString``, ``name``, ``sizeWhenDone``,
    ``leftUntilDone``, ``eta``, ``status``, ``rateUpload``, ``rateDownload``,
    ``uploadedEver``, ``downloadedEver`` for each torrent.

.. method:: Client.change(ids, kwargs**)

    Change torrent parameters for the torrent(s) with the supplied id's. The
    parameters are:
    
    * ``files_wanted``, A list of file id's that should be downloaded.
    * ``files_unwanted``, A list of file id's that shouldn't be downloaded.
    * ``peer_limit``, The peer limit for the torrents.
    * ``priority_high``, A list of file id's that should have high priority.
    * ``priority_normal``, A list of file id's that should have normal priority.
    * ``priority_low``, A list of file id's that should have low priority.
    * ``speed_limit_up``, Set the speed limit for upload in Kib/s.
    * ``speed_limit_up_enable``, Enable upload speed limiter.
    * ``speed_limit_down``, Set the speed limit for download in Kib/s.
    * ``speed_limit_down_enable``, Enable download speed limiter.

.. method:: Client.get_session()

    Get the Session object for the client.

.. method:: Client.set_session()

    Set session parameters. The parameters are:
    
    * ``encryption``, Level of encryption. Should be one of ``required``, ``preferred`` or ``tolerated``.
    * ``download_dir``, Default download dir.
    * ``peer_limit``, Default download dir.
    * ``pex_allowed``, Allow pex in public torrents.
    * ``port``, Set the port number.
    * ``port_forwarding_enabled``, 
    * ``speed_limit_down``, Set the global download speed limit in Kib/s.
    * ``speed_limit_down_enabled``, Enables the global download speed limiter.
    * ``speed_limit_up``, Set the global upload speed limit in Kib/s.
    * ``speed_limit_up_enabled``, Enables the global upload speed limiter.

.. method:: Client.session_stats()

    Returns statistics about the current session in a dictionary.

