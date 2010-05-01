# -*- coding: utf-8 -*-
# 2009-05, Erik Svensson <erik.public@gmail.com>

import unittest, logging, copy
try:
    import json
except ImportError:
    import simplejson as json

# this test suite requires transmission-daemon with following settings
#  * Default address and port i.e. 0.0.0.0:9095
#  * User authentication with username admin and password admin

torrent_url = 'http://releases.ubuntu.com/9.04/ubuntu-9.04-alternate-i386.iso.torrent'
torrent_hash = '031ebeb6faa215c387d8bc35198efc07df9433c5'
mf_torrent_url = 'http://imgjam.com/torrents/album/26/36026/36026-ogg3.torrent/Sean%20Fournier%20-%20Oh%20My%20--%20Jamendo%20-%20OGG%20Vorbis%20q7%20-%202008.12.05%20%5Bwww.jamendo.com%5D.torrent'
mf_torrent_hash = '711adbb146d153c81a0fd13d1df6b294ddb87dc6'
ubuntu910_magnet = 'magnet:?xt=urn:btih:b65333c904f35428c09811a01032666f98abff67&dn=ubuntu-9.10-desktop-i386.iso&tr=http%3A%2F%2Ftracker.openbittorrent.com%2Fannounce'

from transmissionrpc import TransmissionError, Client
from transmissionrpc.utils import get_arguments, make_rpc_name, argument_value_convert
import transmissionrpc.constants as const

class liveTestCase(unittest.TestCase):
    def setUp(self):
        self.client = Client(user='admin', password='admin', port=9095)
        torrents = self.client.list()
        add_torrent = True
        self.torrent_id = None
        for tid, torrent in torrents.iteritems():
            if torrent.hashString == mf_torrent_hash:
                self.torrent_id = tid
                add_torrent = False
                break
        if add_torrent:
            if self.client.rpc_version > 6:
                self.torrent_id = self.client.add_uri(mf_torrent_url).values()[0].id
            else:
                self.torrent_id = self.client.add_url(mf_torrent_url).values()[0].id

    def tearDown(self):
        self.client.remove(self.torrent_id, delete_data=True)
        del self.client

    def testAddMagnet(self):
        if self.client.rpc_version > 6:
            torrent = self.client.add_uri(ubuntu910_magnet).values()[0]
            hstr = self.client.info(torrent.id).values()[0].hashString
            self.assertEqual(torrent.hashString, hstr)
            self.client.remove(torrent.id, delete_data=True)
    
    def testAdd(self):
        if self.client.rpc_version > 7:
            torrent = self.client.add_uri(torrent_url, paused=True, peer_limit=10, bandwidthPriority=const.TR_PRI_HIGH).values()[0]
            torrent_info = self.client.info(torrent.id).values()[0]
            self.assertEqual(torrent_info.priority, 'high')
            self.assertEqual(torrent_info.status, 'stopped')
            self.assertEqual(torrent_info.peer_limit, 10)
            self.client.remove(torrent.id, delete_data=True)
            torrent = self.client.add_uri(torrent_url, paused=False, peer_limit=20, bandwidthPriority=const.TR_PRI_LOW).values()[0]
            torrent_info = self.client.info(torrent.id).values()[0]
            self.assertEqual(torrent_info.priority, 'low')
            self.assertEqual(torrent_info.status, 'downloading')
            self.assertEqual(torrent_info.peer_limit, 20)
            self.client.remove(torrent.id, delete_data=True)
        elif self.client.rpc_version > 4:
            torrent = self.client.add_uri(torrent_url, paused=True, peer_limit=10).values()[0]
            torrent_info = self.client.info(torrent.id).values()[0]
            self.assertEqual(torrent_info.status, 'stopped')
            self.assertEqual(torrent_info.peer_limit, 10)
            self.client.remove(torrent.id, delete_data=True)
            torrent = self.client.add_uri(torrent_url, paused=False, peer_limit=20).values()[0]
            torrent_info = self.client.info(torrent.id).values()[0]
            self.assertNotEqual(torrent_info.status, 'stopped')
            self.assertEqual(torrent_info.peer_limit, 20)
            self.client.remove(torrent.id, delete_data=True)
            self.failUnlessRaises(ValueError, self.client.add_uri, torrent_url, bandwidthPriority=const.TR_PRI_LOW)
        else:
            torrent = self.client.add_uri(torrent_url, paused=True, peer_limit=10).values()[0]
            torrent_info = self.client.info(torrent.id).values()[0]
            self.assertEqual(torrent_info.status, 'stopped')
            self.client.remove(torrent.id, delete_data=True)
            torrent = self.client.add_uri(torrent_url, paused=False, peer_limit=20).values()[0]
            torrent_info = self.client.info(torrent.id).values()[0]
            self.assertEqual(torrent_info.status, 'downloading')
            self.client.remove(torrent.id, delete_data=True)
            self.failUnlessRaises(ValueError, self.client.add_uri, torrent_url, bandwidthPriority=const.TR_PRI_LOW)

    def doSetSession(self, argument, value, rvalfunc=None, rarg=None):
        if not rvalfunc:
            rvalfunc = lambda v: v
        if not rarg:
            rarg = argument
        original = copy.deepcopy(
            rvalfunc(
                self.client.get_session().fields[rarg]
            )
        )
        args = {argument: value}
        self.client.set_session(**args)
        rval = rvalfunc(self.client.get_session().fields[rarg])
        self.assertEqual(value, rval
                         , msg='Argument "%s": in: "%r" does not equal out:"%r"'
                         % (argument, value, rval))
        args = {argument: original}
        self.client.set_session(**args)
        rval = rvalfunc(self.client.get_session().fields[rarg])
        self.assertEqual(rval, original
                         , msg='Argument "%s": original in: "%r" does not equal out:"%r"'
                         % (argument, original, rval))

    def doFailSetSession(self, argument, value):
        args = {argument: value}
        self.failUnlessRaises(ValueError, self.client.set_session, **args)

    def testSetSession(self):
        # a torrent-get is needed to really find out if the rpc_version is 1 or 2
        if self.client.rpc_version <= 2:
            self.client.info(self.torrent_id)
        self.doSetSession('encryption', 'tolerated')
        self.doSetSession('encryption', 'preferred')
        self.doSetSession('encryption', 'required')
        self.doSetSession('download_dir', '/tmp')
        self.doSetSession('port_forwarding_enabled', False)
        self.doSetSession('port_forwarding_enabled', True)
        self.doSetSession('speed_limit_down_enabled', False)
        self.doSetSession('speed_limit_down_enabled', True)
        self.doSetSession('speed_limit_up_enabled', False)
        self.doSetSession('speed_limit_up_enabled', True)
        if self.client.rpc_version < 2:
            # these versions of the protocol seems to return the value in
            # b/s instead of Kib/s
            def speedLimitValueFunction(value):
                res = int(value)
                res = res / 1024
                return res
            self.doSetSession('speed_limit_up', 10, rvalfunc=speedLimitValueFunction)
            self.doSetSession('speed_limit_down', 10, rvalfunc=speedLimitValueFunction)
        else:
            self.doSetSession('speed_limit_up', 10)
            self.doSetSession('speed_limit_down', 10)

        if self.client.rpc_version <= 4:
            self.doSetSession('pex_allowed', False)
            self.doSetSession('pex_allowed', True)
            self.doSetSession('port', 33033)
            self.doSetSession('peer_limit', 1000)
            # test automatic argument replacer
            self.doSetSession('peer_limit_global', 1000, rarg='peer_limit')
            self.doSetSession('pex_enabled', True, rarg='pex_allowed')
            self.doSetSession('peer_port', 33033, rarg='port')
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
            # test automatic argument replacer
            self.doSetSession('peer_limit', 1000, rarg='peer_limit_global')
            self.doSetSession('pex_allowed', True, rarg='pex_enabled')
            self.doSetSession('port', 33033, rarg='peer_port')
        if self.client.rpc_version > 5:
            self.doSetSession('dht_enabled', True)
            self.doSetSession('dht_enabled', False)
        if self.client.rpc_version > 6:
            self.doSetSession('incomplete_dir', '/tmp')
            self.doSetSession('incomplete_dir_enabled', True)
            self.doSetSession('incomplete_dir_enabled', False)
        if self.client.rpc_version > 7:
            self.doSetSession('rename_partial_files', False)
            self.doSetSession('rename_partial_files', True)

    def testGetSession(self):
        o = self.client.get_session()
        library_args = get_arguments('session-get', self.client.rpc_version)
        for argument, value in o.fields.iteritems():
            argument = make_rpc_name(argument)
            self.assertTrue(argument in library_args
                            , msg='Response argument %s not found.' % (argument))
            library_args.remove(argument)
        for argument in library_args:
            self.fail('%s not found in response' % argument)
        self.assertEqual(len(library_args), 0)

    def getTorrent(self):
        return self.client.info(self.torrent_id).values()[0]

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

    def doSetTorrent(self, argument, value, rarg=None, check=True):
        if not rarg:
            rarg = argument
        original = copy.deepcopy(self.getTorrent())
        args = {argument: value}
        self.client.change(self.torrent_id, **args)
        torrent = self.getTorrent()
        if not check:
            return
        self.assertEqual(torrent.fields[rarg], value)
        args = {argument: original.fields[rarg]}
        self.client.change(self.torrent_id, **args)
        torrent = self.getTorrent()
        self.assertEqual(torrent.fields[rarg], original.fields[rarg])

    def testSetTorrent(self):
        if self.client.rpc_version <= 4:
            self.doSetTorrent('peer_limit', 10, check=False)
            self.doSetTorrent('speed_limit_down', 10, rarg='downloadLimit')
            self.doSetTorrent('speed_limit_down_enabled', False, check=False)
            self.doSetTorrent('speed_limit_down_enabled', True, check=False)
            self.doSetTorrent('speed_limit_up', 10, rarg='uploadLimit')
            self.doSetTorrent('speed_limit_up_enabled', False, check=False)
            self.doSetTorrent('speed_limit_up_enabled', True, check=False)
            pass
        if self.client.rpc_version > 4:
            self.doSetTorrent('peer_limit', 10)
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

    def testSetTorrentFiles(self):
        tid = self.torrent_id
        files = self.client.get_files(tid)[tid]
        original = copy.deepcopy(files)
        files[0]['priority'] = 'high'
        files[1]['priority'] = 'normal'
        files[2]['priority'] = 'low'
        files[3]['selected'] = False
        files[4]['selected'] = True
        self.client.set_files({tid: files})
        files = self.client.get_files(tid)[tid]
        self.assertEqual(files[0]['priority'], 'high')
        self.assertEqual(files[1]['priority'], 'normal')
        self.assertEqual(files[2]['priority'], 'low')
        self.assertEqual(files[3]['selected'], False)
        self.assertEqual(files[4]['selected'], True)
        files[0]['selected'] = True
        files[1]['selected'] = False
        files[2]['priority'] = 'high'
        files[3]['priority'] = 'low'
        files[3]['selected'] = True
        files[4]['priority'] = 'high'
        self.client.set_files({tid: files})
        files = self.client.get_files(tid)[tid]
        self.assertEqual(files[0]['priority'], 'high')
        self.assertEqual(files[1]['priority'], 'normal')
        self.assertEqual(files[2]['priority'], 'high')
        self.assertEqual(files[3]['priority'], 'low')
        self.assertEqual(files[4]['priority'], 'high')
        self.assertEqual(files[0]['selected'], True)
        self.assertEqual(files[1]['selected'], False)
        self.assertEqual(files[2]['selected'], True)
        self.assertEqual(files[3]['selected'], True)
        self.assertEqual(files[4]['selected'], True)
        pass

    def testReannounce(self):
        if self.client.rpc_version < 5:
            self.assertRaises(TransmissionError, self.client.reannounce
                              , self.torrent_id)
        else:
            self.client.reannounce(self.torrent_id)

    def testPortTest(self):
        if self.client.rpc_version < 5:
            self.assertRaises(TransmissionError, self.client.port_test)
        else:
            self.client.port_test()
    
    def testMove(self):
        if self.client.rpc_version < 6:
            self.assertRaises(TransmissionError, self.client.move
                              , self.torrent_id, '/tmp')
        else:
            self.client.move(self.torrent_id, '/tmp')
    
    def testLocate(self):
        if self.client.rpc_version < 6:
            self.assertRaises(TransmissionError, self.client.locate
                              , self.torrent_id, '/tmp')
        else:
            self.client.locate(self.torrent_id, '/tmp')
    
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    #logging.getLogger('transmissionrpc').setLevel(logging.INFO)
    unittest.main()
