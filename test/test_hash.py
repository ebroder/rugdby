from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class HashTest(gdbtest.GDBTest):
    def test_pretty(self):
        val = gdb.parse_and_eval("""rb_eval_string("{'a' => 1, 'b' => 2, 'c' => 3}")""")
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubyRHash)
        self.assertPretty(val, "{'a' => 1, 'b' => 2, 'c' => 3}")

    def test_empty(self):
        # Ruby doesn't seem to allocate the st_table for an empty hash
        val = gdb.parse_and_eval('rb_eval_string("{}")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertEqual(0, rval._gdbval['ntbl'])
        self.assertPretty(val, '{}')

    def test_self_referential(self):
        val = gdb.parse_and_eval('rb_eval_string("x = {}; x[:x] = x; x")')
        self.assertPretty(val, "{:x => {...}}")
