# This file makes sure that gdb exits with a non-0 error code if tests
# fail

import nose.core
import os
import sys
import traceback

try:
    nose.core.TestProgram()
except Exception as e:
    sys.stderr.write('Error running test file')
    traceback.print_exc()
    sys.exit(1)
