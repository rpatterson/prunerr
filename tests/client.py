# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>

import unittest
import transmission.constants
from transmission import Client

class client(unittest.TestCase):
    def assertTransmissionRequest(self, expected, client, call, *args, **kwargs):
        
        def request(method, arguments={}, ids=[], require_ids=False):
            if method != expected['method']:
                raise ValueError()
            if arguments != expected['arguments']:
                raise ValueError()
            if ids != expected['ids']:
                raise ValueError()
            if require_ids != expected['require_ids']:
                raise ValueError()
        original_request = client._request
        client._request = request
        try:
            call(*args, **kwargs)
        except Exception, e:
            self.fail(e)
        client._request = original_request
    
    def testConstruction(self):
        tc = Client()
        self.assertEqual(tc.url, 'http://localhost:%d/transmission/rpc' % (transmission.constants.DEFAULT_PORT))
        self.assertEqual(tc.verbose, False)
        tc = Client('www.google.com', 6000)
        self.assertEqual(tc.url, 'http://www.google.com:6000/transmission/rpc')
        self.assertEqual(tc.verbose, False)
        tc = Client('127.0.0.1', 7000, user='user', password='secret')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        self.assertEqual(tc.verbose, False)
        tc = Client('127.0.0.1', 7000, user='user', password='secret', verbose=True)
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        self.assertEqual(tc.verbose, True)
        tc = Client('127.0.0.1', 7000, user='user')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        self.assertEqual(tc.verbose, False)
        tc = Client('127.0.0.1', 7000, password='secret')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        self.assertEqual(tc.verbose, False)
    
    def testAdd(self):
        tc = Client()
        data = 'data'
        expected = {'method': 'torrent-add', 'arguments': {'metainfo': data}, 'ids': [], 'require_ids': False}
        self.assertTransmissionRequest(expected, tc, tc.add, data)
        expected = {'method': 'torrent-add', 'arguments': {'metainfo': data, 'paused': 1}, 'ids': [], 'require_ids': False}
        self.assertTransmissionRequest(expected, tc, tc.add, data, paused=True)
        expected = {'method': 'torrent-add', 'arguments': {'metainfo': data, 'download-dir': '/tmp'}, 'ids': [], 'require_ids': False}
        self.assertTransmissionRequest(expected, tc, tc.add, data, download_dir='/tmp')
        expected = {'method': 'torrent-add', 'arguments': {'metainfo': data, 'peer-limit': 10}, 'ids': [], 'require_ids': False}
        self.assertTransmissionRequest(expected, tc, tc.add, data, peer_limit=10)
        expected = {'method': 'torrent-add', 'arguments': {'metainfo': data, 'paused': 1, 'download-dir': '/tmp', 'peer-limit': 10}, 'ids': [], 'require_ids': False}
        self.assertTransmissionRequest(expected, tc, tc.add, data, paused=True, download_dir='/tmp', peer_limit=10)
        
        self.failUnlessRaises(ValueError, tc.add, data, peer_limit='apa')
    
    def testAddUrl(self):
        pass

def suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(client)
    return suite
