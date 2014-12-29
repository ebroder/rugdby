from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class ObjectTest(gdbtest.GDBTest):
    def test_object_with_ivars(self):
        val = gdb.parse_and_eval("""rb_eval_string("class Test; end; x = Test.new; x.instance_variable_set(:@foo, 'bar'); x")""")
        self.assertPretty(val, "<Test @foo='bar'>")
