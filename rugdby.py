#!/usr/bin/python
"""
Python gdb hooks for Ruby

From gdb 7 onwards, you can build in Python, allowing for extensions
written in Python code. It's kind of silly to inspect Ruby state from
Python, but here we go.

Also, apparently gdb is sometimes built against Python 2 and sometimes
Python 3, so we need to bend over to work with both.

Much of this logic is either inspired by or taken from the equivalent
hooks for Python.

Note: These hooks have been tested on Ruby 1.9.3 and later. It
definitely doesn't work on 1.8
"""

from __future__ import print_function, with_statement
import gdb
import collections
import fractions
import functools
import re
import sys

if sys.version_info[0] >= 3:
    unichr = chr
    xrange = range
    long = int

def cache(f):
    memo = {}
    @functools.wraps(f)
    def cached(*args):
        if args not in memo:
            memo[args] = f(*args)
        return memo[args]
    return cached

# ===============
# Pretty printers
# ===============
#
# To pretty-print Ruby values, we basically have to re-implement the
# Ruby type-system in bizarro Python infused with gdb's concept of C
# types.

MAX_OUTPUT_LEN = 1024

class StringTruncated(RuntimeError):
    pass

class TruncatedStringIO(object):
    '''Similar to cStringIO, but can truncate the output by raising a
    StringTruncated exception'''
    def __init__(self, maxlen=None):
        self._val = ''
        self.maxlen = maxlen

    def write(self, data):
        if self.maxlen:
            if len(data) + len(self._val) > self.maxlen:
                # Truncation:
                self._val += data[0:self.maxlen - len(self._val)]
                raise StringTruncated()

        self._val += data

    def getvalue(self):
        return self._val

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

RUBY_SPECIAL_SHIFT = 8

_void_p = gdb.lookup_type('void').pointer()
_unsigned_long = gdb.lookup_type('unsigned long')
_double = gdb.lookup_type('double')
_char = gdb.lookup_type('char')

# With Ruby 2.0 and the introduction of floating-point numbers
# ("flonums") as an immediate value type, true, false, nil, and the
# immediate mask all changed.
#
# This seems to be the best way to detect (without access to macros)
# whether or not this verison of Ruby was built with flonum support.
#
# Also, we have to use gdb.parse_and_eval so that this works on older
# gdbs, which don't have gdb.Symbol.value() support
@cache
def Qtrue():
    return int(gdb.parse_and_eval('rb_equal(0, 0)'))

def Qfalse():
    return 0

def Qnil(): # pragma: no cover
    if Qtrue() == 2:
        return 4
    elif Qtrue() == 20:
        return 8
    else:
        raise "Unable to determine Qnil from unknown value for true: %s" % Qtrue()

def Qundef(): # pragma: no cover
    if Qtrue() == 2:
        return 6
    elif Qtrue() == 20:
        return 52
    else:
        raise "Unable to determine Qundef from unknown value for true: %s" % Qtrue()

def IMMEDIATE_MASK(): # pragma: no cover
    if Qtrue() == 2:
        return 0x3
    elif Qtrue() == 20:
        return 0x7
    else:
        raise "Can't determine IMMEDIATE_MASK from unknown value for true: %s" % Qtrue()

def FIXNUM_FLAG():
    return 0x1

def FLONUM_MASK(): # pragma: no cover
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

def SYMBOL_FLAG(): # pragma: no cover
    if Qtrue() == 2:
        return 0xe
    elif Qtrue() == 20:
        return 0xc
    else:
        raise "Can't determine SYMBOL_FLAG from unknown value for true: %s" % Qtrue()

def FL_USHIFT():
    return 12

def FL_USER(n):
    return 1 << (FL_USHIFT() + n)

class ImmediateRubyVALUE(RuntimeError):
    pass

class RubyVal(object):
    """
    A generic wrapper for any gdb.Value that might have meaning to the
    Ruby runtime
    """
    _typename = None
    _typepointer = False

    def __init__(self, gdbval, cast_to=None):
        if cast_to:
            self._gdbval = gdbval.cast(cast_to)
        elif self.get_gdb_type():
            self._gdbval = gdbval.cast(self.get_gdb_type())
        else:
            self._gdbval = gdbval

    def as_address(self):
        return long(self._gdbval)

    @classmethod
    @cache
    def get_gdb_type(cls):
        if cls._typename is None:
            return None

        t = gdb.lookup_type(cls._typename)
        if cls._typepointer:
            return t.pointer()
        else:
            return t

    def proxyval(self, visited):
        class FakeRepr(object):
            """
            Class representing a non-descript VALUE in the inferior
            process for when we either don't have a custom scraper or
            the object is corrupted somehow. Mostly just has a sane
            repr()
            """
            def __init__(self, address, type):
                self.address = address
                self.type = type
            def __repr__(self):
                return '<%s at remote 0x%x>' % (str(self.type), self.address)
        return FakeRepr(self.as_address(), self.get_gdb_type())

    def write_repr(self, out, visited):
        out.write(repr(self.proxyval(visited)))

    def get_truncated_repr(self, maxlen):
        '''
        Get a repr-like string for the data, but truncate it at "maxlen" bytes
        (ending the object graph traversal as soon as you do)
        '''
        out = TruncatedStringIO(maxlen)
        try:
            self.write_repr(out, set())
        except StringTruncated:
            # Truncation occurred:
            return out.getvalue() + '...(truncated)'

        # No truncation occurred:
        return out.getvalue()

    @classmethod
    @cache
    def all_subclasses(cls):
        all_subclasses = set()
        q = [cls]
        while q:
            parent = q.pop()
            for child in parent.__subclasses__():
                if child not in all_subclasses:
                    all_subclasses.add(child)
                    q.append(child)
        return all_subclasses

class RubyVALUE(RubyVal):
    """
    Class wrapping a gdb.Value that is a VALUE type
    """

    _type = None
    _types = []
    _typename = 'VALUE'

    def type(self):
        immediate = self.as_address()

        # deal with specials
        if immediate == Qfalse():
            return RUBY_T_FALSE

        if immediate == Qnil():
            return RUBY_T_NIL

        if immediate == Qtrue():
            return RUBY_T_TRUE

        if immediate == Qundef():
            return RUBY_T_UNDEF

        # deal with immediates
        if immediate & FIXNUM_FLAG():
            return RUBY_T_FIXNUM

        if immediate & FLONUM_MASK() == FLONUM_FLAG():
            return RUBY_T_FLOAT

        if immediate & SYMBOL_MASK() == SYMBOL_FLAG():
            return RUBY_T_SYMBOL

        return RubyRBasic(self._gdbval).type()

    def is_immediate(self):
        return bool(IMMEDIATE_MASK() & self.as_address())

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
            if ((subclass._type and subclass._type == t) or
                (subclass._types and t in subclass._types)):
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

            type = cls.get_gdb_type()
            # Only cast if we have a non-immediate
            if type:
                return cls(gdbval, cast_to=type)
            else:
                return cls(gdbval)
        except RuntimeError:
            # Handle any kind of error by just using the base class
            pass
        return cls(gdbval)

    @classmethod
    def proxyval_from_value(cls, v, visited=None):
        if visited is None:
            visited = set()

        return cls.from_value(v).proxyval(visited)

class ProxyAlreadyVisited(object):
    """
    Placeholder proxy to use when protecting against infinite
    recursion due to loops in the object graph.

    Analogous to the values emitted by the users of Py_ReprEnter and
    Py_ReprLeave
    """
    def __init__(self, rep):
        self._rep = rep

    def __repr__(self):
        return self._rep

class RubySTTable(RubyVal):
    """
    Special wrapper class for st_table *, which Ruby uses for hashes
    """
    _typename = 'struct st_table'
    _typepointer = True

    def __init__(self, gdbval, keyproxy=None, valueproxy=None):
        if keyproxy is None:
            keyproxy = lambda x: x
        if valueproxy is None:
            valueproxy = lambda x: x

        self.keyproxy = keyproxy
        self.valueproxy = valueproxy

        super(RubySTTable, self).__init__(gdbval, self.get_gdb_type())

    def items(self):
        new_style = 'as' in [f.name for f in self._gdbval.dereference().type.fields()]
        if self._gdbval['entries_packed']:
            if new_style:
                for i in xrange(long(self._gdbval['as']['packed']['real_entries'])):
                    entry = self._gdbval['as']['packed']['entries'][i]
                    yield entry['key'], entry['val']
            else:
                for i in xrange(long(self._gdbval['num_entries'])):
                    yield self._gdbval['bins'][i * 2], self._gdbval['bins'][i * 2 + 1]
        else:
            if new_style:
                ptr = self._gdbval['as']['big']['head']
            else:
                ptr = self._gdbval['head']

            while ptr:
                yield ptr['key'], ptr['record']
                ptr = ptr['fore']

    def __getitem__(self, needle):
        for k, v in self.items():
            if k == needle:
                return v
        raise KeyError(needle)

    def proxyval(self, visited):
        result = dict()
        for k, v in self.items():
            result[self.keyproxy(k)] = self.valueproxy(v)
        return result

# Immediates and other specials:

class RubyFixnum(RubyVALUE):
    """
    Class wrapping a gdb.Value that is a Fixnum
    """
    _type = RUBY_T_FIXNUM
    def proxyval(self, visited):
        return self.as_address() >> 1

class RubyFlonum(RubyVALUE):
    """
    Class wrapping immediate floating-point numbers (not RFloats)
    """
    # Don't specify _type because RubyVALUE will handle the dispatch
    def rotr(self, v, b):
        return (v >> b) | (v << ((v.type.sizeof * 8) - 3))

    def proxyval(self, visited):
        if self._gdbval == gdb.Value(0x8000000000000002):
            return 0.0
        else:
            v = self._gdbval.cast(_unsigned_long)
            b63 = v >> 63
            t = (2 - b63) | (v & ~3)
            t = self.rotr(t, 3)
            return float(t.cast(_void_p).cast(_double))

class RubyNil(RubyVALUE):
    _type = RUBY_T_NIL
    def proxyval(self, visited):
        return None

    def write_repr(self, out, visited):
        out.write('nil')

class RubyTrue(RubyVALUE):
    _type = RUBY_T_TRUE
    def proxyval(self, visited):
        return True

    def write_repr(self, out, visited):
        out.write('true')

class RubyFalse(RubyVALUE):
    _type = RUBY_T_FALSE
    def proxyval(self, visited):
        return False

    def write_repr(self, out, visited):
        out.write('false')

class RubyID(RubyVal):
    _typename = 'ID'

    # TODO: Even in Ruby 2.2 (where symbols are GC'd), once a given ID
    # is assigned it's never reused, so we could do a lot of caching
    # here for efficiency

    @staticmethod
    @cache
    def global_symbols():
        return gdb.parse_and_eval('global_symbols')

    @staticmethod
    def ID_SCOPE_SHIFT():
        return 4

    def __long__(self):
        return long(self._gdbval)

    def __int__(self):
        return int(self._gdbval)

    def __str__(self):
        return self.string(set())

    def __repr__(self):
        return ':' + str(self)

    def string(self, visited):
        global_symbols = RubyID.global_symbols()
        try:
            if 'id_str' in [f.name for f in global_symbols.type.fields()]:
                table = RubySTTable(global_symbols['id_str'])
                return RubyVALUE.proxyval_from_value(table[self._gdbval], visited)
            else:
                serial = self._gdbval >> self.ID_SCOPE_SHIFT()
                ids = RubyVALUE.from_value(global_symbols['ids'])
                id_entry_unit = RubyVALUE.from_value(ids[0]).length() / 2

                idx = serial / id_entry_unit
                ary = RubyVALUE.from_value(ids[idx])
                return RubyVALUE.proxyval_from_value(ary[(serial % id_entry_unit) * 2], visited)
        except:
            return "<Unknown symbol ID 0x%x>" % long(self)

    def proxyval(self, visited):
        return ':' + self.string(visited)

class RubySymbol(RubyVALUE):
    _type = RUBY_T_SYMBOL

    @classmethod
    def intern(cls, s):
        global_symbols = RubyID.global_symbols()
        if 'id_str' in [f.name for f in global_symbols.type.fields()]:
            table = RubySTTable(global_symbols['id_str'])
            for k, v in table.items():
                if RubyVALUE.proxyval_from_value(v) == s:
                    return k
        else:
            ids = RubyVALUE.from_value(global_symbols['ids'])
            for idx in xrange(long(ids.length())):
                ary = RubyVALUE.from_value(ids[idx])
                for i in xrange(0, long(ary.length()), 2):
                    if RubyVALUE.proxyval_from_value(ary[i]) == s:
                        return ary[i + 1]

    def sym2id(self):
        return RubyID(self._gdbval >> RUBY_SPECIAL_SHIFT)

    def proxyval(self, visited):
        return self.sym2id()

# VALUE types that are pointers

class RubyRBasic(RubyVALUE):
    """
    Class wrapping a gdb.Value that is a non-immediate Ruby VALUE
    """
    _typename = 'struct RBasic'
    _typepointer = True

    def flags(self):
        if self.is_immediate():
            raise ImmediateRubyVALUE(self)

        return long(self._gdbval.cast(RubyRBasic.get_gdb_type()).dereference()['flags'])

    def type(self):
        return self.flags() & RUBY_T_MASK

    def klass(self):
        return self._gdbval['basic']['klass']

class RubyRFloat(RubyRBasic):
    _typename = 'struct RFloat'
    def proxyval(self, visited):
        return float(self._gdbval.dereference()['float_value'])

class RubyRObject(RubyRBasic):
    _type = RUBY_T_OBJECT
    _typename = 'struct RObject'

    @staticmethod
    def ROBJECT_EMBED():
        return FL_USER(1)

    def iv_index_tbl(self):
        return RubyRClass(self.klass()).real_class().iv_index_tbl()

    def ivptr(self):
        if self.flags() & self.ROBJECT_EMBED():
            return self._gdbval['as']['ary']
        else:
            return self._gdbval['as']['heap']['ivptr']

    def ivars(self):
        # TODO: bounds-check the indexes in iv_index_tbl
        ivptr = self.ivptr()
        iv_index_tbl = RubySTTable(self.iv_index_tbl())
        if iv_index_tbl.as_address():
            for k, v in iv_index_tbl.items():
                if ivptr[v] != Qundef():
                    yield RubyID(k), RubyVALUE.from_value(ivptr[v])

    def write_repr(self, out, visited):
        if self.as_address() in visited:
            out.write('<...>')
            return
        visited.add(self.as_address())

        out.write('<')
        out.write(RubyRClass(self.klass()).name())
        for k, v in self.ivars():
            out.write(' ')
            out.write(str(k))
            out.write('=')
            v.write_repr(out, visited)
        out.write('>')

class RubyRClass(RubyRBasic):
    _types = [RUBY_T_CLASS, RUBY_T_MODULE, RUBY_T_ICLASS]
    _typename = 'struct RClass'

    # Strategy: self->ptr->iv_tbl hopefully includes a :__classpath__
    # hidden variable. If that's not there, we have to do a search of
    # the constant tree (starting from the constants over Object) and
    # discover it.

    @staticmethod
    @cache
    def classpathSymbol():
        return RubySymbol.intern('__classpath__')

    @staticmethod
    def FL_SINGLETON():
        return FL_USER(0)

    @staticmethod
    @cache
    def cObject():
        return RubyVALUE.from_value(gdb.parse_and_eval('rb_cObject'))

    def real_class(self):
        cls = self
        while cls.flags() & self.FL_SINGLETON():
            cls = RubyRClass(self._gdbval['super'])
        return cls

    def iv_index_tbl(self):
        try:
            return self._gdbval['ptr']['iv_index_tbl']
        except gdb.error as e:
            if e.args[0] != 'There is no member named iv_index_tbl.':
                raise
            return self._gdbval['iv_index_tbl']

    def constants(self):
        tbl = self._gdbval['ptr']['const_tbl']
        if not tbl:
            return None
        return RubySTTable(tbl)

    def classpath(self):
        table = RubySTTable(self._gdbval['ptr']['iv_tbl'])
        if not table.as_address():
            table = {}
        return table[self.classpathSymbol()]

    @staticmethod
    @cache
    def rb_const_entry_t():
        return gdb.lookup_type('rb_const_entry_t')

    def searchForClass(self, target, visited=None):
        if visited is None:
            visited = set([self.as_address()])

        constants = self.constants()
        if constants is None:
            return None

        for k, v in constants.items():
            value = v.cast(self.rb_const_entry_t().pointer())['value']

            if long(value) == target.as_address():
                return str(RubyID(k))

            if long(value) in visited:
                continue
            visited.add(long(value))

            if RubyVALUE(value).type() in [RUBY_T_CLASS, RUBY_T_MODULE]:
                child = RubyRClass(value).searchForClass(target, visited)
                if child is not None:
                    return '%s::%s' % (RubyID(k), child)

    def name(self):
        try:
            return RubyVALUE.proxyval_from_value(self.classpath())
        except KeyError:
            search = self.cObject().searchForClass(self)
            if search == None:
                return "%s:0x%s" % ("Module" if self.type() == RUBY_T_MODULE else "Class", self.as_address())
            else:
                return search

    def write_repr(self, out, visited):
        out.write('#<')
        out.write(self.name())
        out.write('>')

class RubyRString(RubyRBasic):
    _type = RUBY_T_STRING
    _typename = 'struct RString'

    @staticmethod
    def RSTRING_NOEMBED():
        return FL_USER(1)

    def __str__(self):
        if self.flags() & RubyRString.RSTRING_NOEMBED():
            ptr = self._gdbval['as']['heap']['ptr']
            length = self._gdbval['as']['heap']['len']
        else:
            ptr = self._gdbval['as']['ary']
            length = (self.flags() >> (2 + FL_USHIFT())) & 31
        return ptr.cast(_char.array(long(length)).pointer()).dereference().string()

    def proxyval(self, visited):
        return str(self)

class RubyRArray(RubyRBasic):
    _type = RUBY_T_ARRAY
    _typename = 'struct RArray'

    @staticmethod
    def RARRAY_EMBED_FLAG():
        return FL_USER(1)

    def array(self):
        if self.flags() & RubyRArray.RARRAY_EMBED_FLAG():
            return self._gdbval['as']['ary']
        else:
            return self._gdbval['as']['heap']['ptr']

    def length(self):
        if self.flags() & RubyRArray.RARRAY_EMBED_FLAG():
            return (self.flags() >> (3 + FL_USHIFT())) & 3
        else:
            return self._gdbval['as']['heap']['len']

    def __getitem__(self, i):
        if i > self.length():
            raise IndexError("list index out of range")
        return self.array()[i]

    def proxyval(self, visited):
        if self.as_address() in visited:
            return ProxyAlreadyVisited('[...]')
        visited.add(self.as_address())

        ary = self.array()
        length = self.length()
        return [RubyVALUE.proxyval_from_value(ary[i], visited)
                for i in xrange(long(length))]

class RubyRRegexp(RubyRBasic):
    _type = RUBY_T_REGEXP
    _typename = 'struct RRegexp'

    ONIG_OPTION_IGNORECASE = 1 << 0
    ONIG_OPTION_EXTEND = 1 << 1
    ONIG_OPTION_MULTILINE = 1 << 2

    def proxyval(self, visited):
        flags = 0
        opts = self._gdbval['ptr']['options']
        if opts & self.ONIG_OPTION_IGNORECASE:
            flags |= re.IGNORECASE
        if opts & self.ONIG_OPTION_EXTEND:
            flags |= re.VERBOSE
        if opts & self.ONIG_OPTION_MULTILINE:
            flags |= re.MULTILINE

        return re.compile(RubyVALUE.proxyval_from_value(self._gdbval['src'], visited),
                          flags)

    def write_repr(self, out, visited):
        src = RubyVALUE.proxyval_from_value(self._gdbval['src'], visited)
        if '/' in src:
            begin, end = '%r{', '}'
        else:
            begin = end = '/'
        out.write(begin)
        out.write(src)
        out.write(end)

        opts = self._gdbval['ptr']['options']
        if opts & self.ONIG_OPTION_IGNORECASE:
            out.write('i')
        if opts & self.ONIG_OPTION_EXTEND:
            out.write('x')
        if opts & self.ONIG_OPTION_MULTILINE:
            out.write('m')

class RubyRHash(RubyRBasic):
    _type = RUBY_T_HASH
    _typename = 'struct RHash'

    def items(self):
        return RubySTTable(self._gdbval['ntbl']).items()

    def proxyval(self, visited):
        if self.as_address() in visited:
            return ProxyAlreadyVisited('{...}')
        visited.add(self.as_address())

        if not self._gdbval['ntbl']:
            return {}

        result = {}
        for k, v in self.items():
            k = RubyVALUE.proxyval_from_value(k, visited)
            v = RubyVALUE.proxyval_from_value(v, visited)
            result[k] = v
        return result

    def write_repr(self, out, visited):
        if self.as_address() in visited:
            out.write('{...}')
            return
        visited.add(self.as_address())

        out.write('{')

        if self._gdbval['ntbl']:
            first = True
            for k, v in self.items():
                if first:
                    first = False
                else:
                    out.write(', ')

                RubyVALUE.from_value(k).write_repr(out, visited)
                out.write(' => ')
                RubyVALUE.from_value(v).write_repr(out, visited)

        out.write('}')

class RubyRFile(RubyRBasic):
    _type = RUBY_T_FILE
    _typename = 'struct RFile'

    def write_repr(self, out, visited):
        fptr = self._gdbval['fptr']
        if not fptr:
            return super(RubyRFile, self).write_repr(out, visited)

        out.write('#<')
        out.write(RubyRClass(self.klass()).name())
        out.write(':')
        path = RubyVALUE.proxyval_from_value(fptr['pathv'], visited)
        if path:
            out.write(path)
        elif fptr['fd'] >= 0:
            out.write('fd %d' % (fptr['fd'],))

        if fptr['fd'] < 0:
            out.write(' (closed)')

        out.write('>')

class RubyRRational(RubyRBasic):
    _type = RUBY_T_RATIONAL
    _typename = 'struct RRational'

    def proxyval(self, visited):
        num = RubyVALUE.proxyval_from_value(self._gdbval['num'], visited)
        den = RubyVALUE.proxyval_from_value(self._gdbval['den'], visited)
        return fractions.Fraction(num, den)

class RubyRComplex(RubyRBasic):
    _type = RUBY_T_COMPLEX
    _typename = 'struct RComplex'

    def proxyval(self, visited):
        real = RubyVALUE.proxyval_from_value(self._gdbval['real'], visited)
        imag = RubyVALUE.proxyval_from_value(self._gdbval['imag'], visited)
        return complex(real, imag)

class RubyValPrinter(object):
    def __init__(self, gdbval):
        self.gdbval = gdbval

    def to_string(self):
        return RubyVALUE.from_value(self.gdbval).get_truncated_repr(MAX_OUTPUT_LEN)

def pretty_printer_lookup(gdbval):
    for cls in RubyVALUE.all_subclasses():
        if cls.get_gdb_type() == gdbval.type.unqualified():
            return RubyValPrinter(gdbval)

def register(obj):
    if obj == None:
        obj = gdb
    obj.pretty_printers.append(pretty_printer_lookup)
register(gdb.current_objfile())
