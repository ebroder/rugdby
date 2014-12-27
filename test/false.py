from __future__ import print_function

import unittest
import gdbtest

class FalseTest(gdbtest.GDBTest):
    def test_pretty_print(self):
        self.assertPretty('rb_eval_string("false")', 'False')

unittest.main('<run_path>')
