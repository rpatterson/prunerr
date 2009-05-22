# -*- coding: utf-8 -*-
# 2009-05, Erik Svensson <erik.public@gmail.com>

import unittest, logging, copy

# this test suite requires transmission-daemon

torrent_url = 'http://releases.ubuntu.com/9.04/ubuntu-9.04-alternate-i386.iso.torrent'
torrent_name = 'ubuntu-9.04-alternate-i386.iso'

from transmissionrpc import TransmissionError, Client

class liveTestCase(unittest.TestCase):
    def setUp(self):
        self.client = Client(user='admin', password='admin')
        torrents = self.client.list()
        add_torrent = True
        for tid, torrent in torrents.iteritems():
            if torrent.name == torrent_name:
                add_torrent = False
                break
        if add_torrent:
            self.client.add_url(torrent_url)
    
    def tearDown(self):
        del self.client
    
    def doChangeAndTestSetSession(self, argument, value):
        original_session = copy.deepcopy(self.client.get_session())
        logging.info('changing %s from %r to %r and testing' % (argument, original_session.fields[argument], value))
        args = {argument: value}
        self.client.set_session(**args)
        session = self.client.get_session()
        self.assertEqual(session.fields[argument], value)
        args = {argument: original_session.fields[argument]}
        self.client.set_session(**args)
        session = self.client.get_session()
        self.assertEqual(session.fields[argument], original_session.fields[argument])
    
    def testSetSession(self):
        o = self.client.get_session()
        self.doChangeAndTestSetSession('encryption', 'tolerated')
        self.doChangeAndTestSetSession('encryption', 'preferred')
        self.doChangeAndTestSetSession('encryption', 'required')
        self.doChangeAndTestSetSession('download_dir', '/tmp')
        self.doChangeAndTestSetSession('port_forwarding_enabled', False)
        self.doChangeAndTestSetSession('port_forwarding_enabled', True)
        self.doChangeAndTestSetSession('speed_limit_down', 10)
        self.doChangeAndTestSetSession('speed_limit_down_enabled', False)
        self.doChangeAndTestSetSession('speed_limit_down_enabled', True)
        self.doChangeAndTestSetSession('speed_limit_up', 10)
        self.doChangeAndTestSetSession('speed_limit_up_enabled', False)
        self.doChangeAndTestSetSession('speed_limit_up_enabled', True)

        if self.client.rpc_version() <= 4:
            self.doChangeAndTestSetSession('peer_limit', 1000)
            self.doChangeAndTestSetSession('peer_allowed', False)
            self.doChangeAndTestSetSession('peer_allowed', True)
            self.doChangeAndTestSetSession('port', 33033)
        if self.client.rpc_version() > 4:
            self.doChangeAndTestSetSession('alt_speed_down', 10)
            self.doChangeAndTestSetSession('alt_speed_enabled', False)
            self.doChangeAndTestSetSession('alt_speed_enabled', True)
            self.doChangeAndTestSetSession('alt_speed_time_begin', 10)
            self.doChangeAndTestSetSession('alt_speed_time_enabled', False)
            self.doChangeAndTestSetSession('alt_speed_time_enabled', True)
            self.doChangeAndTestSetSession('alt_speed_time_end', 10)
            self.doChangeAndTestSetSession('alt_speed_time_day', 2)
            self.doChangeAndTestSetSession('alt_speed_up', 10)
            self.doChangeAndTestSetSession('blocklist_enabled', False)
            self.doChangeAndTestSetSession('blocklist_enabled', True)
            self.doChangeAndTestSetSession('peer_limit_global', 10000)
            self.doChangeAndTestSetSession('peer_limit_per_torrent', 1000)
            self.doChangeAndTestSetSession('pex_enabled', False)
            self.doChangeAndTestSetSession('pex_enabled', True)
            self.doChangeAndTestSetSession('peer_port', 33033)
            self.doChangeAndTestSetSession('peer_port_random_on_start', False)
            self.doChangeAndTestSetSession('peer_port_random_on_start', True)
            self.doChangeAndTestSetSession('seedRatioLimit', 100)
            self.doChangeAndTestSetSession('seedRatioLimited', False)
            self.doChangeAndTestSetSession('seedRatioLimited', True)

    def testGetSession(self):
        from transmissionrpc.utils import get_arguments, make_rpc_name
        
        o = self.client.get_session()
        library_args = get_arguments('session-get', o.rpc_version)
        for argument, value in o.fields.iteritems():
            argument = make_rpc_name(argument)
            self.assertTrue(argument in library_args)
            library_args.remove(argument)
        self.assertEqual(len(library_args), 0)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    unittest.main()
