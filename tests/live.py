# -*- coding: utf-8 -*-
# 2009-05, Erik Svensson <erik.public@gmail.com>

import unittest, logging, copy
try:
    import json
except ImportError:
    import simplejson as json

# this test suite requires transmission-daemon with following settings
#  * Default address and port i.e. 0.0.0.0:9091
#  * User authentication with username admin and password admin

torrent_url = 'http://releases.ubuntu.com/9.04/ubuntu-9.04-alternate-i386.iso.torrent'
torrent_name = 'ubuntu-9.04-alternate-i386.iso'

from transmissionrpc import TransmissionError, Client
from transmissionrpc.utils import get_arguments, make_rpc_name
import transmissionrpc.constants as const

class liveTestCase(unittest.TestCase):
    def setUp(self):
        self.client = Client(user='admin', password='admin')
        torrents = self.client.list()
        add_torrent = True
        self.torrent_id = None
        for tid, torrent in torrents.iteritems():
            if torrent.name == torrent_name:
                self.torrent_id = tid
                add_torrent = False
                break
        if add_torrent:
            self.torrent_id = self.client.add_url(torrent_url).values()[0].id

    def tearDown(self):
        self.client.remove(self.torrent_id, delete_data=True)
        del self.client

    def doSetSession(self, argument, value):
        original = copy.deepcopy(self.client.get_session())
        args = {argument: value}
        self.client.set_session(**args)
        session = self.client.get_session()
        self.assertEqual(session.fields[argument], value)
        args = {argument: original.fields[argument]}
        self.client.set_session(**args)
        session = self.client.get_session()
        self.assertEqual(session.fields[argument], original.fields[argument])

    def doFailSetSession(self, argument, value):
        args = {argument: value}
        self.failUnlessRaises(ValueError, self.client.set_session, **args)

    def testSetSession(self):
        self.doSetSession('encryption', 'tolerated')
        self.doSetSession('encryption', 'preferred')
        self.doSetSession('encryption', 'required')
        self.doSetSession('download_dir', '/tmp')
        self.doSetSession('port_forwarding_enabled', False)
        self.doSetSession('port_forwarding_enabled', True)
        self.doSetSession('speed_limit_down', 10)
        self.doSetSession('speed_limit_down_enabled', False)
        self.doSetSession('speed_limit_down_enabled', True)
        self.doSetSession('speed_limit_up', 10)
        self.doSetSession('speed_limit_up_enabled', False)
        self.doSetSession('speed_limit_up_enabled', True)

        if self.client.rpc_version <= 4:
            self.doSetSession('peer_limit', 1000)
            self.doSetSession('peer_allowed', False)
            self.doSetSession('peer_allowed', True)
            self.doSetSession('port', 33033)
            # TODO: should test a lot of failures
        if self.client.rpc_version > 4:
            self.doSetSession('alt_speed_down', 10)
            self.doSetSession('alt_speed_enabled', False)
            self.doSetSession('alt_speed_enabled', True)
            self.doSetSession('alt_speed_time_begin', 10)
            self.doSetSession('alt_speed_time_enabled', False)
            self.doSetSession('alt_speed_time_enabled', True)
            self.doSetSession('alt_speed_time_end', 10)
            self.doSetSession('alt_speed_time_day', 2)
            self.doSetSession('alt_speed_up', 10)
            self.doSetSession('blocklist_enabled', False)
            self.doSetSession('blocklist_enabled', True)
            self.doSetSession('peer_limit_global', 10000)
            self.doSetSession('peer_limit_per_torrent', 1000)
            self.doSetSession('pex_enabled', False)
            self.doSetSession('pex_enabled', True)
            self.doSetSession('peer_port', 33033)
            self.doSetSession('peer_port_random_on_start', False)
            self.doSetSession('peer_port_random_on_start', True)
            self.doSetSession('seedRatioLimit', 100)
            self.doSetSession('seedRatioLimited', False)
            self.doSetSession('seedRatioLimited', True)
            # fail!
            self.doFailSetSession('peer_limit', 1000)
            self.doFailSetSession('peer_allowed', False)
            self.doFailSetSession('port', 1000)

    def testGetSession(self):
        o = self.client.get_session()
        library_args = get_arguments('session-get', o.rpc_version)
        for argument, value in o.fields.iteritems():
            argument = make_rpc_name(argument)
            self.assertTrue(argument in library_args
                , msg='Response argument %s not found.' % (argument))
            library_args.remove(argument)
        for argument in library_args:
            self.fail('%s not found in response' % argument)
        self.assertEqual(len(library_args), 0)

    def testGetTorrent(self):
        torrent = self.getTorrent()
        library_args = get_arguments('torrent-get', self.client.rpc_version)
        for argument, value in torrent.fields.iteritems():
            argument = make_rpc_name(argument)
            self.assertTrue(argument in library_args
                , msg='Response argument %s not found.' % (argument))
            library_args.remove(argument)
        for argument in library_args:
            self.fail('%s not found in response' % argument)
        self.assertEqual(len(library_args), 0)

    def getTorrent(self):
        return self.client.info(self.torrent_id).values()[0]

    def doSetTorrent(self, argument, value):
        original = copy.deepcopy(self.getTorrent())
        args = {argument: value}
        self.client.change(self.torrent_id, **args)
        torrent = self.getTorrent()
        self.assertEqual(torrent.fields[argument], value)
        args = {argument: original.fields[argument]}
        self.client.change(self.torrent_id, **args)
        torrent = self.getTorrent()
        self.assertEqual(torrent.fields[argument], original.fields[argument])

    def testSetTorrent(self):
        self.doSetTorrent('peer_limit', 10)
        if self.client.rpc_version <= 4:
            self.doSetTorrent('speed_limit_down', 10)
            self.doSetTorrent('speed_limit_down_enabled', False)
            self.doSetTorrent('speed_limit_down_enabled', True)
            self.doSetTorrent('speed_limit_up', 10)
            self.doSetTorrent('speed_limit_up_enabled', False)
            self.doSetTorrent('speed_limit_up_enabled', True)
            pass
        if self.client.rpc_version > 4:
            self.doSetTorrent('bandwidthPriority', const.TR_PRI_HIGH)
            self.doSetTorrent('bandwidthPriority', const.TR_PRI_LOW)
            self.doSetTorrent('bandwidthPriority', const.TR_PRI_NORMAL)
            self.doSetTorrent('downloadLimit', 10)
            self.doSetTorrent('downloadLimited', False)
            self.doSetTorrent('downloadLimited', True)
            self.doSetTorrent('honorsSessionLimits', False)
            self.doSetTorrent('honorsSessionLimits', True)
            self.doSetTorrent('seedRatioLimit', 1.1)
            self.doSetTorrent('seedRatioMode', const.TR_RATIOLIMIT_GLOBAL)
            self.doSetTorrent('seedRatioMode', const.TR_RATIOLIMIT_SINGLE)
            self.doSetTorrent('seedRatioMode', const.TR_RATIOLIMIT_UNLIMITED)
            self.doSetTorrent('uploadLimit', 10)
            self.doSetTorrent('uploadLimited', False)
            self.doSetTorrent('uploadLimited', True)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    #logging.getLogger('transmissionrpc').setLevel(logging.INFO)
    unittest.main()
