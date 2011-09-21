# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>
# Licensed under the MIT license.

import time, datetime
import unittest
import transmissionrpc
import transmissionrpc.constants
import transmissionrpc.utils

class torrent(unittest.TestCase):
    def assertPropertyException(self, exception, object, property):
        try:
            getattr(object, property)
        except exception:
            pass
        else:
            self.fail()
    
    def testConstruction(self):
        self.failUnlessRaises(ValueError, transmissionrpc.Torrent, None, {})
        torrent = transmissionrpc.Torrent(None, {'id': 42})
    
    def testAttributes(self):
        torrent = transmissionrpc.Torrent(None, {'id': 42})
        self.assertTrue(hasattr(torrent, 'client'))
        self.assertTrue(hasattr(torrent, 'id'))
        self.assertEqual(torrent.client, None)
        self.assertEqual(torrent.id, 42)
        self.assertPropertyException(KeyError, torrent, 'status')
        self.assertPropertyException(KeyError, torrent, 'progress')
        self.assertPropertyException(KeyError, torrent, 'ratio')
        self.assertPropertyException(KeyError, torrent, 'eta')
        self.assertPropertyException(KeyError, torrent, 'date_active')
        self.assertPropertyException(KeyError, torrent, 'date_added')
        self.assertPropertyException(KeyError, torrent, 'date_started')
        self.assertPropertyException(KeyError, torrent, 'date_done')
        
        self.failUnlessRaises(KeyError, torrent.format_eta)
        self.assertEqual(torrent.files(), {})
        
        data = {
            'id': 1,
            'status': transmissionrpc.constants.TR_STATUS_DOWNLOAD,
            'sizeWhenDone': 1000,
            'leftUntilDone': 500,
            'uploadedEver': 1000,
            'downloadedEver': 2000,
            'uploadRatio': 0.5,
            'eta': 3600,
            'activityDate': time.mktime((2008,12,11,11,15,30,0,0,-1)),
            'addedDate': time.mktime((2008,12,11,8,5,10,0,0,-1)),
            'startDate': time.mktime((2008,12,11,9,10,5,0,0,-1)),
            'doneDate': time.mktime((2008,12,11,10,0,15,0,0,-1)),
        }
        
        torrent = transmissionrpc.Torrent(None, data)
        self.assertEqual(torrent.id, 1)
        self.assertEqual(torrent.leftUntilDone, 500)
        self.assertEqual(torrent.status, 'downloading')
        self.assertEqual(torrent.progress, 50.0)
        self.assertEqual(torrent.ratio, 0.5)
        self.assertEqual(torrent.eta, datetime.timedelta(seconds=3600))
        self.assertEqual(torrent.date_active, datetime.datetime(2008,12,11,11,15,30))
        self.assertEqual(torrent.date_added, datetime.datetime(2008,12,11,8,5,10))
        self.assertEqual(torrent.date_started, datetime.datetime(2008,12,11,9,10,5))
        self.assertEqual(torrent.date_done, datetime.datetime(2008,12,11,10,0,15))
        
        self.assertEqual(torrent.format_eta(), transmissionrpc.utils.format_timedelta(torrent.eta))
        
        torrent.fields['downloadedEver'] = 0
        self.assertEqual(torrent.ratio, 0)
        torrent.fields['sizeWhenDone'] = 0
        self.assertEqual(torrent.progress, 0)

    def testUnicode(self):
        torrent = transmissionrpc.Torrent(None, {'id': 42, 'name': 'あみ'})
        self.assertEqual(torrent.id, 42)
        torrent
        str(torrent)

def suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(torrent)
    return suite
