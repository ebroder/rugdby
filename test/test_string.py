from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class StringTest(gdbtest.GDBTest):
    def test_pretty_embedded_string(self):
        s = 'hello'
        val = gdb.parse_and_eval('rb_eval_string("%s")' % (repr(s).replace('"', '\\"'),))
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubyRString)
        self.assertFalse(rval.flags() & rugdby.RubyRString.RSTRING_NOEMBED())
        self.assertPretty(val, repr(s))

    def test_pretty_long_string(self):
        s = 'hello' * 100
        val = gdb.parse_and_eval('rb_eval_string("%s")' % (repr(s).replace('"', '\\"'),))
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubyRString)
        self.assertTrue(rval.flags() & rugdby.RubyRString.RSTRING_NOEMBED())
        self.assertPretty(val, repr(s))
