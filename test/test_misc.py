from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class MiscTest(gdbtest.GDBTest):
    def test_rational(self):
        val = gdb.parse_and_eval('rb_eval_string("Rational(1, 2)")')
        self.assertPretty(val, 'Fraction(1, 2)')

    def test_complex(self):
        val = gdb.parse_and_eval('rb_eval_string("Complex.rect(1, 2)")')
        self.assertPretty(val, '(1+2j)')
