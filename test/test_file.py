from __future__ import print_function

import gdb
import rugdby

from test.lib import gdbtest

class FileTest(gdbtest.GDBTest):
    def test_builtin_fd(self):
        val = gdb.parse_and_eval('rb_eval_string("STDERR")')
        self.assertPretty(val, '#<IO:<STDERR>>')

    def test_no_path_fd(self):
        val = gdb.parse_and_eval('rb_eval_string("IO.for_fd(2)")')
        self.assertPretty(val, '#<IO:fd 2>')

    def test_closed_fd(self):
        val = gdb.parse_and_eval('rb_eval_string("x = IO.for_fd(2); x.close; x")')
        self.assertPretty(val, '#<IO: (closed)>')

    def test_closed_path(self):
        val = gdb.parse_and_eval('rb_eval_string("STDERR.close; STDERR")')
        self.assertPretty(val, '#<IO:<STDERR> (closed)>')
