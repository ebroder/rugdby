from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class FlonumTest(gdbtest.GDBTest):
    def test_pretty_print(self):
        val = gdb.parse_and_eval('rb_eval_string("1.1")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, (rugdby.RubyFlonum, rugdby.RubyRFloat))
        self.assertPretty(val, '1.1')

    def test_big_flonums(self):
        val = gdb.parse_and_eval('rb_eval_string("1.72723e-77")')
        rval = rugdby.RubyVALUE.from_value(val)
        # This should always be an RFloat
        self.assertIsInstance(rval, rugdby.RubyRFloat)
        self.assertPretty(val, '1.72723e-77')
