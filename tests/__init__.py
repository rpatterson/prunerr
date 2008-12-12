# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>

import unittest
import torrent, utils

def suite():
    suite = unittest.TestSuite()
    suite.addTest(torrent.suite())
    suite.addTest(utils.suite())
    return suite