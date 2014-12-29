from __future__ import print_function

import string

import gdb
import rugdby

from test.lib import gdbtest

class ObjectTest(gdbtest.GDBTest):
    def test_object_with_ivars(self):
        val = gdb.parse_and_eval("""rb_eval_string("class Test; end; x = Test.new; x.instance_variable_set(:@foo, 'bar'); x")""")
        self.assertPretty(val, "<Test @foo='bar'>")

    def test_many_ivars(self):
        val = gdb.parse_and_eval("""rb_eval_string("class Test; end; x = Test.new; (:@a..:@z).each {|k| x.instance_variable_set(k, 'bar')}; x")""")
        ivars = ' '.join(['@%s=%r' % (c, 'bar') for c in string.ascii_lowercase])
        self.assertPretty(val, "<Test %s>" % (ivars,))

    def test_self_reference(self):
        val = gdb.parse_and_eval("""rb_eval_string("class Test; end; x = Test.new; x.instance_variable_set(:@foo, x); x")""")
        self.assertPretty(val, "<Test @foo=<...>>")
