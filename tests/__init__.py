# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>

import unittest
import utils

def suite():
    suite = unittest.TestSuite()
    suite.addTest(utils.suite())
    #suite.addTest(torrent.suite())
    #suite.addTest(client.suite())
    return suite
