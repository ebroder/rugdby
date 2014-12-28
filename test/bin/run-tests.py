#!/usr/bin/env python

from __future__ import print_function

import os
import subprocess
import sys

def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ruby = subprocess.check_output(['ruby', '-r', 'rubygems', '-e', 'puts Gem.ruby']).strip()

    os.execlp(
        'gdb',
        'gdb',
        '-q',
        '--batch-silent',
        '-nx', # Don't read gdbinit
        '--ex', 'add-auto-load-safe-path %s' % (root,),
        '--ex', 'file %s' % (ruby,),
        '--ex', 'set height 0',
        '--eval-command', 'python sys.argv = %r' % (sys.argv,),
        '--eval-command', 'python import runpy',
        '--eval-command', 'python runpy.run_path(%r, globals())' % (os.path.join(root, 'test/lib/wrap.py'),),
    )

if __name__ == '__main__':
    main()
