import os
import sys
import unittest

import gdb

root = os.path.abspath(os.path.relpath('../../', os.path.dirname(__file__)))
sys.path.append(root)
import libruby

class GDBTest(unittest.TestCase):
    def setUp(self):
        bp = gdb.Breakpoint('vm_exec_core')
        bp.silent = True
        bp.condition = 'th != 0'
        try:
            gdb.execute('run -e ""')
        finally:
            bp.delete()

    def assertPretty(self, val, pretty):
        if isinstance(val, str):
            val = gdb.parse_and_eval(val)
        self.assertEqual(str(val), pretty)
