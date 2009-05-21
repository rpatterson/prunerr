
Transmission RPC
################

Introduction
============

This is the transmissionrpc. This module helps using Python to connect
to a Transmission_ JSON-RPC service. transmissionrpc is compatible with
Transmission 1.3 and later.

transmissionrpc is licensed under the MIT license.

.. _Transmission: http://www.transmissionbt.com/

Getting started
===============

Transmission is available at
`Python Package Index <http://pypi.python.org/pypi/transmissionrpc/>`_. To
install the transmissionrpc python module use easy_install.

::

    $ easy_install transmissionrpc

Dependecies
-----------

 * simplejson >= 1.7.1 or Python >= 2.6.
 
Report a problem
----------------

Problems with transmissionrpc should be reported through the issue tracker at
bitbucket_. Please look through the `existing issues`_ before opening a
`new issue`_.

.. _existing issues: http://bitbucket.org/blueluna/transmissionrpc/issues/
.. _new issue: http://bitbucket.org/blueluna/transmissionrpc/issues/new/

Getting dirty
=============

The source code
---------------

Transmission is hosted at bitbucket_ using mercurial_. To pull a working copy,
run
::

   $ hg pull http://www.bitbucket.org/blueluna/transmissionrpc/

Then install the module using
::

    $ python setup.py install

Or if you wish to poke around in transmissionrpc itself use
::

	$ python setup.py develop

This will link this directory to the library as transmissionrpc.

.. _bitbucket: http://www.bitbucket.org/blueluna/transmissionrpc/
.. _mercurial: http://www.selenic.com/mercurial

Poking around
-------------

Now that transmissionrpc has been installed, run python and start to poke
around. Following will create a RPC client and list all torrents.

::

    >>> import transmissionrpc
    >>> tc = transmissionrpc.Client('localhost', port=9091, user=None, password=None)
    >>> tc.list()

List will return a dictionary of Torrent object indexed by their id. You might
not have any torrents yet. This can be remedied by adding an torrent.
::

    >>> tc.add_url('http://releases.ubuntu.com/8.10/ubuntu-8.10-desktop-i386.iso.torrent')
    {1: <Torrent 1 "ubuntu-8.10-desktop-i386.iso">}
    >>> tc.info(1)
    {1: <Torrent 1 "ubuntu-8.10-desktop-i386.iso">}

As you saw, the add_url and info calls also returns a dictionary with
``{<id>: <Torrent>, ...}``. More information about a torrent transfer can be
found in the Torrent object.
::

    >>> torrent = tc.info(1)[1]
    >>> torrent.name
    'ubuntu-8.10-desktop-i386.iso'
    >>> torrent.hashString
    '33820db6dd5e5928d23bc811bbac2f4ae94cb882'
    >>> torrent.status
    'downloading'
    >>> torrent.eta
    datetime.timedelta(0, 750)
    >>> for key, value in torrent.fields.iteritems():
    ...     print(key, value)
    ...
    ('comment', 'Ubuntu CD releases.ubuntu.com')

The last call will list all known data provided by the Transmission.

Well, we weren't that interested in Ubuntu so lets stop the transfer and the
remove it.

::

    >>> tc.stop(1)
    >>> tc.remove('33820db6dd5e5928d23bc811bbac2f4ae94cb882')

See what we did there? most methods in transmissionrpc can take both torrent id
and torrent hash when referring to a torrent. lists and sequences are also
supported.

    >>> tc.info([2, 'caff87b88f50f46bc22da3a2712a6a4e9a98d91e'])
    {2: <Torrent 2 "ubuntu-8.10-server-amd64.iso">, 3: <Torrent 3 "ubuntu-8.10-alternate-amd64.iso">}
    >>> tc.info('1:3')
    {2: <Torrent 2 "ubuntu-8.10-server-amd64.iso">, 3: <Torrent 3 "ubuntu-8.10-alternate-amd64.iso">}

Continue to explore and have fun! For more in depth information read the module reference.

Module reference
================

.. toctree::
   :maxdepth: 2

   reference/transmissionrpc

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`