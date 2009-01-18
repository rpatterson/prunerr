# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>

import sys, os.path, base64
import unittest

if sys.version_info[0] >= 2 and sys.version_info[1] >= 6:
    import json
else:
    import simplejson as json

import transmission.constants
from transmission import TransmissionError, Client

class client(unittest.TestCase):
    def assertTransmissionRequest(self, expected, client, call, *args, **kwargs):
        def request(method, arguments={}, ids=[], require_ids=False):
            self.assertEqual(method, expected['method'])
            self.assertEqual(arguments, expected['arguments'])
            self.assertEqual(ids, expected['ids'])
            self.assertEqual(require_ids, expected['require_ids'])
        original_request = client._request
        client._request = request
        call(*args, **kwargs)
        client._request = original_request
    
    def assertTransmissionQuery(self, expected, result, client, call, *args, **kwargs):
        def query(q):
            data = json.loads(q)
            self.assertEqual(data['method'], expected['method'])
            self.assertEqual(data['arguments'], expected['arguments'])
            result['result'] = 'success'
            return json.dumps(result)
        original_method = client._http_query
        client._http_query = query
        call(*args, **kwargs)
        client._http_query = original_method
    
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
        # test exception for non integer peer_limit
        self.failUnlessRaises(ValueError, tc.add, data, peer_limit='apa')
    
    def testAddUrl(self):
        dirpath = os.path.dirname(os.path.abspath(__file__))
        tc = Client()
        data = base64.b64encode('torrent')
        expected = {'method': 'torrent-add', 'arguments': {'metainfo': data, 'paused': 1, 'download-dir': '/tmp', 'peer-limit': 10}, 'ids': [], 'require_ids': False}
        self.assertTransmissionRequest(expected, tc, tc.add_url, '%s/torrent.txt' % (dirpath), paused=True, download_dir='/tmp', peer_limit=10)
        self.failUnlessRaises(TransmissionError, tc.add_url, 'torrent.torrent')
        # TODO: Add test for real web url's?
    
    def testRemove(self):
        tc = Client()
        ids = ['0123456789abcdef', 2, 3]
        # test at query interface
        expected = {'method': 'torrent-remove', 'arguments': {'delete-local-data': 0}, 'ids': ids, 'require_ids': True}
        self.assertTransmissionRequest(expected, tc, tc.remove, ids)
        # test at http interface
        expected = {'method': 'torrent-remove', 'arguments': {'ids': ids, 'delete-local-data': 0}}
        self.assertTransmissionQuery(expected, {}, tc, tc.remove, ids)
    
    def testStart(self):
        tc = Client()
        ids = ['0123456789abcdef', 2, 3]
        # test at query interface
        expected = {'method': 'torrent-start', 'arguments': {}, 'ids': ids, 'require_ids': True}
        self.assertTransmissionRequest(expected, tc, tc.start, ids)
        # test at http interface
        expected = {'method': 'torrent-start', 'arguments': {'ids': ids}}
        self.assertTransmissionQuery(expected, {}, tc, tc.start, ids)
    
    def testStop(self):
        tc = Client()
        ids = ['0123456789abcdef', 2, 3]
        # test at query interface
        expected = {'method': 'torrent-stop', 'arguments': {}, 'ids': ids, 'require_ids': True}
        self.assertTransmissionRequest(expected, tc, tc.stop, ids)
        # test at http interface
        expected = {'method': 'torrent-stop', 'arguments': {'ids': ids}}
        self.assertTransmissionQuery(expected, {}, tc, tc.stop, ids)
    
    def testVerify(self):
        tc = Client()
        ids = ['0123456789abcdef', 2, 3]
        # test at query interface
        expected = {'method': 'torrent-verify', 'arguments': {}, 'ids': ids, 'require_ids': True}
        self.assertTransmissionRequest(expected, tc, tc.verify, ids)
        # test at http interface
        expected = {'method': 'torrent-verify', 'arguments': {'ids': ids}}
        self.assertTransmissionQuery(expected, {}, tc, tc.verify, ids)
    
    def testInfo(self):
        tc = Client()
        fields = transmission.constants.FIELDS
        ids = [2, 3]
        # test at query interface
        expected = {'method': 'torrent-get', 'arguments': {'fields': fields}, 'ids': ids, 'require_ids': False}
        self.assertTransmissionRequest(expected, tc, tc.info, ids)
        # test at http interface
        # following failes because get wants to receive torrent data
        #result = {}
        #expected = {'method': 'torrent-get', 'arguments': {'ids': ids, 'fields': fields}}
        #self.assertTransmissionQuery(expected, {}, tc, tc.info, ids)

def suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(client)
    return suite
