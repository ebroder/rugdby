from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class FixnumTest(gdbtest.GDBTest):
    def test_pretty_print(self):
        val = gdb.parse_and_eval('rb_eval_string("123")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubyFixnum)
        self.assertPretty(val, '123')
