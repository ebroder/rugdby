from __future__ import print_function

import unittest
import gdbtest

class NilTest(gdbtest.GDBTest):
    def test_pretty_print(self):
        self.assertPretty('rb_eval_string("nil")', 'None')

unittest.main('<run_path>')
