# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>

import sys, os, os.path, base64
import unittest
import urlparse

try:
    import json
except ImportError:
    import simplejson as json

import transmissionrpc.constants
from transmissionrpc import TransmissionError, Client, HTTPHandler

class TestHTTPHandler(HTTPHandler):
    def __init__(self, test_name=None):
        self.url = None
        self.user = None
        self.password = None
        self.tests = None
        self.test_index = 0
        if test_name:
            test_file = test_name + '.json'
            here = os.path.dirname(os.path.abspath(__file__))
            test_path = os.path.join(here, 'data', test_file)
            fd = open(test_path, 'r')
            test_data = json.load(fd)
            fd.close()
            if 'test sequence' in test_data:
                self.tests = test_data['test sequence']
    
    def set_authentication(self, url, user, password):
        urlo = urlparse.urlparse(url)
        if urlo.scheme == '':
            raise ValueError('URL should have a scheme.')
        else:
            self.url = url
        if user and password:
            if isinstance(user, (str, unicode)):
                self.user = user
            else:
                raise TypeError('Invalid type for user.')
            if isinstance(password, (str, unicode)):
                self.password = password
            else:
                raise TypeError('Invalid type for password.')
        elif user or password:
            raise ValueError('User AND password or neither.')
    
    def request(self, url, query, headers, timeout):
        response = {}
        if self.url and self.url != url:
            raise ValueError('New URL?!')
        urlo = urlparse.urlparse(url)
        if urlo.scheme == '':
            raise ValueError('URL should have a scheme.')
        else:
            self.url = url
        q = json.loads(query)
        
        if self.tests:
            test_data = self.tests[self.test_index]
            self.test_index += 1
            if test_data['request'] != q:
                raise Exception('Invalid request, %s != %s.' % (q, test_data['request']))
            response = test_data['response']
        else:
            response['tag'] = int(q['tag'])
            response['result'] = 'success'
        return json.dumps(response)

def createClient(*args, **kwargs):
    test_name = None
    if 'test_name' in kwargs:
        test_name = kwargs['test_name']
        del kwargs['test_name']
    kwargs['http_handler'] = TestHTTPHandler(test_name)
    return Client(*args, **kwargs)

class ClientTest(unittest.TestCase):

    def testConstruction(self):
        tc = createClient(test_name='construction')
        self.assertEqual(tc.url, 'http://localhost:%d/transmission/rpc' % (transmissionrpc.constants.DEFAULT_PORT))
        tc = createClient('127.0.0.1', 7000, user='user', password='secret', test_name='construction')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        tc = createClient('127.0.0.1', 7000, user='user', password='secret', test_name='construction')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        tc = createClient('127.0.0.1', 7000, user='user', test_name='construction')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        tc = createClient('127.0.0.1', 7000, password='secret', test_name='construction')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        tc = createClient('127.0.0.1', 7000, password='secret', timeout=0.1, test_name='construction')
        self.assertEqual(tc.url, 'http://127.0.0.1:7000/transmission/rpc')
        self.assertEqual(tc.timeout, 0.1)
        tc = createClient('127.0.0.1', 7000, password='secret', timeout=10, test_name='construction')
        self.assertEqual(tc.timeout, 10.0)
        tc = createClient('127.0.0.1', 7000, password='secret', timeout=10L, test_name='construction')
        self.assertEqual(tc.timeout, 10.0)

    def testTimeoutProperty(self):
        tc = createClient('127.0.0.1', 12345, timeout=10L, test_name='construction')
        self.assertEqual(tc.timeout, 10.0)
        tc.timeout = 0.1
        self.assertEqual(tc.timeout, 0.1)
        tc.timeout = 100L
        self.assertEqual(tc.timeout, 100.0)
        tc.timeout = 100
        self.assertEqual(tc.timeout, 100.0)
        del tc.timeout
        self.assertEqual(tc.timeout, transmissionrpc.constants.DEFAULT_TIMEOUT)
        tc.timeout = '100.1'
        self.assertEqual(tc.timeout, 100.1)
        self.failUnlessRaises(ValueError, tc.set_timeout, '10 years')
            
    def testAdd(self):
        tc = createClient(test_name='add')
        data = 'data'
        
        r = tc.add(data)[0]
        self.assertEqual(r.id, 0)
        self.assertEqual(r.hashString, 'A000')
        self.assertEqual(r.name, 'testtransfer0')
        
        r = tc.add(data, paused=True)[1]
        self.assertEqual(r.id, 1)
        self.assertEqual(r.hashString, 'A001')
        self.assertEqual(r.name, 'testtransfer1')
        
        r = tc.add(data, download_dir='/tmp')[2]
        self.assertEqual(r.id, 2)
        self.assertEqual(r.hashString, 'A002')
        self.assertEqual(r.name, 'testtransfer2')
        
        r = tc.add(data, peer_limit=10)[3]
        self.assertEqual(r.id, 3)
        self.assertEqual(r.hashString, 'A003')
        self.assertEqual(r.name, 'testtransfer3')
        
        r = tc.add(data, paused=True, download_dir='/tmp', peer_limit=10)[4]
        self.assertEqual(r.id, 4)
        self.assertEqual(r.hashString, 'A004')
        self.assertEqual(r.name, 'testtransfer4')
        
        self.failUnlessRaises(ValueError, tc.add, data, peer_limit='apa')

    def testAddUrl(self):
        data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
        tc = createClient(test_name='addurl')
                
        r = tc.add_url(os.path.join(data_path, 'torrent.txt'))[0]
        self.assertEqual(r.id, 0)
        self.assertEqual(r.hashString, 'A000')
        self.assertEqual(r.name, 'testtransfer0')

        r = tc.add_url(os.path.join(data_path, 'torrent.txt'), paused=True, download_dir='/tmp', peer_limit=200)[1]
        self.assertEqual(r.id, 1)
        self.assertEqual(r.hashString, 'A001')
        self.assertEqual(r.name, 'testtransfer1')

        self.failUnlessRaises(TransmissionError, tc.add_url, 'torrent.torrent')

        # TODO: Add test for real web url's?

    def testAddUri(self):
        data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
        tc = createClient(test_name='adduri')

        r = tc.add_uri('torrent.txt', paused=False, download_dir='/var/downloads', peer_limit=1)[0]
        self.assertEqual(r.id, 0)
        self.assertEqual(r.hashString, 'A000')
        self.assertEqual(r.name, 'testtransfer0')

        r = tc.add_uri('file://' + os.path.join(data_path, 'torrent.txt'), paused=True, download_dir='/tmp', peer_limit=200)[1]
        self.assertEqual(r.id, 1)
        self.assertEqual(r.hashString, 'A001')
        self.assertEqual(r.name, 'testtransfer1')

    def testRemove(self):
        tc = createClient(test_name='remove')
        
        tc.remove(['b000', 2, 3])
        tc.remove(1, delete_data=True)
        tc.remove('b002', delete_data=False)

    def testStart(self):
        tc = createClient(test_name='start')
        
        tc.start(['abcdef', 20, 30])
        tc.start(1)
        tc.start('a0123456789')

    def testStop(self):
        tc = createClient(test_name='stop')
        
        tc.stop(2)
        tc.stop('bad')
        tc.stop(['bad', 'ba5', '30', 20])

    def testVerify(self):
        tc = createClient(test_name='verify')
        
        tc.verify(10000)
        tc.verify('d')
        tc.verify(['a', 'b', 'c'])

    def testInfo(self):
        tc = createClient(test_name='info')
        
        r = tc.info()
        self.assertTrue(2 in r)
        self.assertTrue(3 in r)
        t = r[2]
        self.assertEqual(t.id, 2)
        self.assertEqual(t.name, 'ubuntu-10.04-server-amd64.iso')
        self.assertEqual(t.hashString, 'ab8ea951c022d4745a9b06ab8020b952a52b71ca')

def suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(ClientTest)
    return suite
