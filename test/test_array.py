from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class ArrayTest(gdbtest.GDBTest):
    def test_embedded(self):
        val = gdb.parse_and_eval('rb_eval_string("[1, 2, 3]")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubyRArray)
        self.assertPretty(val, '[1, 2, 3]')

    def test_non_embedded(self):
        val = gdb.parse_and_eval('rb_eval_string("[1] * 100")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubyRArray)
        self.assertPretty(val, repr([1] * 100))

    def test_self_referential(self):
        val = gdb.parse_and_eval('rb_eval_string("x = [1]; x << x; x")')
        self.assertPretty(val, "[1, [...]]")
