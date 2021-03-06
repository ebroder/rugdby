from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class RegexpTest(gdbtest.GDBTest):
    def test_no_flags(self):
        val = gdb.parse_and_eval('rb_eval_string("/^a/")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertPretty(val, "/^a/")

    def test_flags(self):
        val = gdb.parse_and_eval('rb_eval_string("/^a/imx")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertPretty(val, '/^a/ixm')

    def test_slashes(self):
        val = gdb.parse_and_eval('rb_eval_string("%r[^a/b]")')
        self.assertPretty(val, '%r{^a/b}')
