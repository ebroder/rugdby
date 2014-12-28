import os
import sys
import unittest

import gdb

import rugdby

class GDBTest(unittest.TestCase):
    def setUp(self):
        gdb.execute('set python print-stack full')

        try:
            gdb.parse_and_eval('vm_exec_core')
            bp = gdb.Breakpoint('vm_exec_core')
            bp.condition = 'th != 0'
        except gdb.error as e:
            if not e.args[0].startswith('No symbol'):
                raise
            bp = gdb.Breakpoint('ruby_exec')

        bp.silent = True

        try:
            gdb.execute('run -e ""')
        finally:
            bp.delete()

    def assertPretty(self, val, pretty):
        if isinstance(val, str):
            val = gdb.parse_and_eval(val)
        self.assertEqual(str(val), pretty)
