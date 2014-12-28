from __future__ import print_function

from test.lib import gdbtest

class TrueTest(gdbtest.GDBTest):
    def test_pretty_print(self):
        self.assertPretty('rb_eval_string("true")', 'True')
