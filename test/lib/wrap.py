# This file makes sure that gdb exits with a non-0 error code if tests
# fail

import os
import runpy
import sys
import traceback

try:
    runpy.run_path(testfile)
except Exception as e:
    sys.stderr.write('Error running test file')
    traceback.print_exc()
    sys.exit(1)
