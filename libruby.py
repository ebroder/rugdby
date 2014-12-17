#!/usr/bin/python
"""Python gdb hooks for Ruby

From gdb 7 onwards, you can build in Python, allowing for extensions
written in Python code. It's kind of silly to inspect Ruby state from
Python, but here we go.

Also, apparently gdb is sometimes built against Python 2 and sometimes
Python 3, so we need to bend over to work with both.

Much of this logic is either inspired by or taken from the equivalent
hooks for Python.

"""

from __future__ import print_function, with_statement
import gdb
import collections
import sys

if sys.version_info[0] >= 3:
    unichr = chr
    xrange = range
    long = int

RUBY_T_OBJECT = 0x01
RUBY_T_CLASS  = 0x02
RUBY_T_MODULE = 0x03
RUBY_T_FLOAT  = 0x04
RUBY_T_STRING = 0x05
RUBY_T_REGEXP = 0x06
RUBY_T_ARRAY  = 0x07
RUBY_T_HASH   = 0x08
RUBY_T_STRUCT = 0x09
RUBY_T_BIGNUM = 0x0a
RUBY_T_FILE   = 0x0b
RUBY_T_DATA   = 0x0c
RUBY_T_MATCH  = 0x0d
RUBY_T_COMPLEX  = 0x0e
RUBY_T_RATIONAL = 0x0f

RUBY_T_NIL    = 0x11
RUBY_T_TRUE   = 0x12
RUBY_T_FALSE  = 0x13
RUBY_T_SYMBOL = 0x14
RUBY_T_FIXNUM = 0x15

RUBY_T_UNDEF  = 0x1b
RUBY_T_NODE   = 0x1c
RUBY_T_ICLASS = 0x1d
RUBY_T_ZOMBIE = 0x1e

RUBY_T_MASK   = 0x1f

_void_p = gdb.lookup_type('void').pointer()
_double = gdb.lookup_type('double')

# With Ruby 2.0 and the introduction of floating-point numbers
# ("flonums") as an immediate value type, true, false, nil, and the
# immediate mask all changed.
#
# This seems to be the best way to detect (without access to macros)
# whether or not this verison of Ruby was built with flonum support.
def Qtrue():
    if Qtrue._Qtrue is None:
        rb_equal, _ = gdb.lookup_symbol('rb_equal')
        if rb_equal is None:
            raise "Unable to find rb_equal symbol to discovery 'true'"
        Qtrue._Qtrue = int(rb_equal.value()(0, 0))
    return Qtrue._Qtrue
Qtrue._Qtrue = None

def Qfalse():
    return 0

def Qnil():
    if Qtrue() == 2:
        return 4
    elif Qtrue() == 20:
        return 8
    else:
        raise "Unknown determine Qnil from unknown value for true: %s" % Qtrue()

def IMMEDIATE_MASK():
    if Qtrue() == 2:
        return 0x3
    elif Qtrue() == 20:
        return 0x7
    else:
        raise "Can't determine IMMEDIATE_MASK from unknown value for true: %s" % Qtrue()

def FIXNUM_FLAG():
    return 0x1

def FLONUM_MASK():
    if Qtrue() == 2:
        # No value ANDed with FLONUM_MASK is non-zero
        return 0x0
    elif Qtrue() == 20:
        return 0x2
    else:
        raise "Can't determine FLONUM_MASK from unknown value for true: %s" % Qtrue()

def FLONUM_FLAG():
    return 0x2

# This is not how Ruby does it, but I find Ruby's way confusing
def SYMBOL_MASK():
    return 0xff

def SYMBOL_FLAG():
    return 0xc

class ImmediateRubyVALUE(RuntimeError):
    pass

class RubyVALUE(object):
    """
    Class wrapping a gdb.Value that is a VALUE type
    """

    _type = None

    def __init__(self, gdbval, cast_to=None):
        if cast_to:
            self._gdbval = gdbval.cast(cast_to)
        else:
            self._gdbval = gdbval

    def proxyval(self, visited):
        class FakeRepr(object):
            """
            Class representing a non-descript VALUE in the inferior
            process for when we either don't have a custom scraper or
            the object is corrupted somehow. Mostly just has a sane
            repr()
            """
            def __init__(self, address):
                self.address = address
            def __repr__(self):
                return '<VALUE at remote 0x%x>' % (self.address)
        return FakeRepr(long(self._gdbval))

    def type(self):
        immediate = long(self._gdbval)

        # deal with specials
        if immediate == Qfalse():
            return RUBY_T_FALSE

        if immediate == Qnil():
            return RUBY_T_NIL

        if immediate == Qtrue():
            return RUBY_T_TRUE

        # deal with immediates
        if immediate & FIXNUM_FLAG():
            return RUBY_T_FIXNUM

        if immediate & FLONUM_MASK() == FLONUM_FLAG():
            return RUBY_T_FLOAT

        if immediate & SYMBOL_MASK() == SYMBOL_FLAG():
            return RUBY_T_SYMBOL

        return RubyRBasic(self._gdbval).type()

    def is_immediate(self):
        return bool(IMMEDIATE_MASK() & long(self._gdbval))

    @classmethod
    def all_subclasses(cls):
        if cls.__all_subclasses__ is None:
            cls.__all_subclasses__ = set()
            q = [cls]
            while q:
                parent = q.pop()
                for child in parent.__subclasses__():
                    if child not in cls.__all_subclasses__:
                        cls.__all_subclasses__.add(child)
                        q.append(child)
        return cls.__all_subclasses__
    __all_subclasses__ = None

    @classmethod
    def subclass_from_value(cls, v):
        t = v.type()

        # special cases first
        if t == RUBY_T_FLOAT:
            if long(v._gdbval) & FLONUM_MASK() == FLONUM_FLAG():
                return RubyFlonum
            else:
                return RubyRFloat

        for subclass in cls.all_subclasses():
            if subclass._type and subclass._type == t:
                return subclass

        # Otherwise, use the base class
        return cls

    @classmethod
    def from_value(cls, gdbval):
        """
        Try to locate the appropriate class dynamically, and cast as appropriate
        """
        try:
            v = RubyVALUE(gdbval)
            cls = cls.subclass_from_value(v)

            # Only cast if we have a non-immediate
            if issubclass(cls, RubyRBasic):
                return cls(gdbval, cast_to=cls.get_gdb_type())
            else:
                return cls(gdbval)
        except RuntimeError:
            # Handle any kind of error by just using the base class
            pass
        return cls(gdbval)

# Immediates and other specials:

class RubyFixnum(RubyVALUE):
    """
    Class wrapping a gdb.Value that is a Fixnum
    """
    _type = RUBY_T_FIXNUM
    def proxyval(self, visited):
        return long(self._gdbval) >> 1

class RubyFlonum(RubyVALUE):
    """
    Class wrapping immediate floating-point numbers (not RFloats)
    """
    def rotr(self, v, b):
        return (v >> b) | (v << ((v.type.sizeof * 8) - 3))

    def proxyval(self, visited):
        if long(self._gdbval) == 0x8000000000000002:
            return 0.0
        else:
            v = self._gdbval.cast(gdb.lookup_type('unsigned long'))
            b63 = v >> 63
            t = (2 - b63) | (v & ~3)
            t = self.rotr(t, 3)
            return float(t.cast(_void_p).cast(_double))

class RubyNil(RubyVALUE):
    _type = RUBY_T_NIL
    def proxyval(self, visited):
        return None

class RubyTrue(RubyVALUE):
    _type = RUBY_T_TRUE
    def proxyval(self, visited):
        return True

class RubyFalse(RubyVALUE):
    _type = RUBY_T_FALSE
    def proxyval(self, visited):
        return False

class RubyRBasic(RubyVALUE):
    """
    Class wrapping a gdb.Value that is a non-immediate Ruby VALUE
    """

    _typename = 'RBasic'

    def flags(self):
        if self.is_immediate():
            raise ImmediateRubyVALUE(self)

        return long(self._gdbval.cast(RubyRBasic.get_gdb_type()).dereference()['flags'])

    def type(self):
        return self.flags() & RUBY_T_MASK

    @classmethod
    def get_gdb_type(cls):
        return gdb.lookup_type('struct ' + cls._typename).pointer()

class RubyRFloat(RubyRBasic):
    _typename = 'RFloat'
    def proxyval(self, visited):
        return float(self._gdbval.dereference()['float_value'])

class RubyRObject(RubyRBasic):
    _typename = 'RObject'

class RubyRClass(RubyRBasic):
    _typename = 'RClass'

class RubyRString(RubyRBasic):
    RSTRING_NOEMBED = 

    _typename = 'RString'
    def proxyval(self, visited):
        
