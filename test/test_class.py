from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class ClassTest(gdbtest.GDBTest):
    def test_name_object(self):
        val = gdb.parse_and_eval('rb_eval_string("Object")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertEqual('Object', rval.name())

    def test_name_top_level(self):
        val = gdb.parse_and_eval('rb_eval_string("String")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertEqual('String', rval.name())

    def test_name_nested_module(self):
        val = gdb.parse_and_eval('rb_eval_string("module A; module B; end; end; A::B")')
        rval = rugdby.RubyVALUE.from_value(val)
        self.assertEqual('A::B', rval.name())

    def test_pretty_class(self):
        val = gdb.parse_and_eval('rb_eval_string("Process::Status")')
        self.assertPretty(val, '#<Process::Status>')
