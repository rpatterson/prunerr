# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>

import unittest

class client(unittest.TestCase):
    pass

def suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(client)
    return suite
