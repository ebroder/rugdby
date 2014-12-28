from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class SymbolTest(gdbtest.GDBTest):
    def test_pretty_print(self):
        val = gdb.parse_and_eval('rb_eval_string(":foo")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubySymbol)
        self.assertPretty(val, ':foo')

    def test_missing_symbol(self):
        v = (0xbeef << rugdby.RUBY_SPECIAL_SHIFT) | rugdby.SYMBOL_FLAG()
        val = gdb.Value(v).cast(gdb.lookup_type('VALUE'))
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertIsInstance(rval, rugdby.RubySymbol)
        self.assertPretty(val, ':<Unknown symbol ID 0x%x>' % 0xbeef)
