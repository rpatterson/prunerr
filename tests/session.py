# -*- coding: utf-8 -*-
# 2008-12, Erik Svensson <erik.public@gmail.com>

import unittest

class session(unittest.TestCase):
    pass

def suite():
    suite = unittest.TestLoader().loadTestsFromTestCase(session)
    return suite
