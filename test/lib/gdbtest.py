import os
import sys
import unittest

import gdb

import rugdby

class GDBTest(unittest.TestCase):
    def setUp(self):
        # If Python exceptions, print the whole stacktrace
        gdb.execute('set python print-stack full')
        # Don't print lines about threads starting
        gdb.execute('set print thread-events off')

        try:
            gdb.parse_and_eval('vm_exec_core')
            bp = gdb.Breakpoint('vm_exec_core', internal=True)
            bp.condition = 'th != 0'
        except gdb.error as e:
            if not e.args[0].startswith('No symbol'):
                raise
            bp = gdb.Breakpoint('ruby_exec', internal=True)

        bp.silent = True

        try:
            gdb.execute('run -e ""')
        finally:
            bp.delete()

    def assertPretty(self, val, expected):
        if isinstance(val, str):
            val = gdb.parse_and_eval(val)
        pretty = str(val)
        self.assertTrue(pretty.startswith('(Ruby) '))
        self.assertEqual(pretty[len('(Ruby) '):], expected)
