#! /usr/bin/python
# This script can parse most data-driven linux Makefiles and output a set of
# :-rules for tup to build the kernel. It does not parse make rules themselves,
# so those have to be imported into the Tupfile manually.

import sys
import tup_client

def if_true(ifs):
    """ Return True/False based on whether or not a False if statement
        is contained in the 'ifs' array.

    """
    if(not ifs):
        return True
    if(False in ifs):
        return False
    return True

def process_if(line, ifs, val):
    """ Process an ifeq/ifneq statement, appending the result to 'ifs' """
    lparen = line.find('(')
    comma = line.find(',', lparen+1)
    rparen = line.find(')', comma+1)
    if(lparen == -1 or comma == -1 or rparen == -1):
        raise Exception('Invalid ifeq statement: ' + line)
    if(line[lparen+1:comma] == line[comma+1:rparen]):
        ifs.append(val)
    else:
        ifs.append(not val)

def process_ifdef(sym, ifs, makevars, val):
    """ Process an ifdef/ifndef statement, appending the result to 'ifs' """
    if(sym in makevars):
        ifs.append(val)
        return
    elif(sym.startswith('CONFIG_')):
        value = tup_client.config_var(sym[7:])
        if(value is not None and value != "n"):
            ifs.append(val)
            return
    ifs.append(not val)

def resolve_vars(s, makevars):
    """ Replace all occurances of $(var) in 's' with the corresponding value of
        the variable from 'makevars'. If a variable does not exist in 'makevars'
        and begins with 'CONFIG_', then we also check with tup to see if it
        is defined as an @-variable. Returns the string with all variable
        expressions expanded.

    """
    dollarparen = s.find('$(')
    if(dollarparen == -1):
        return s

    while(True):
        rparen = s.find(')', dollarparen+2)
        if(rparen == -1):
            raise Exception("No right parenthesis found in expression: " + s)
        if(s.find('$(', dollarparen+2, rparen-1) == -1):
            break
        else:
            s = s[0:dollarparen+2] + resolve_vars(s[dollarparen+2:], makevars)

    var = s[dollarparen+2:rparen]
    value = None
    if(var.startswith('subst')):
        spattern = var[6:]
        comma1 = spattern.find(',')
        comma2 = spattern.find(',', comma1+1)
        if(comma1 == -1 or comma2 == -2):
            raise Exception('subst error: Need 2 commas')
        sfind = spattern[0:comma1]
        sreplace = spattern[comma1+1:comma2]
        sstring = spattern[comma2+1:]
        value = sstring.replace(sfind, sreplace)
    elif(var in makevars):
        value = ' '.join(makevars[var])
    elif(var.startswith("CONFIG_")):
        value = tup_client.config_var(var[7:])
        # Some Makefiles, like drivers/storage/usb/Makefile do things
        # like: ifeq ($(CONFIG_USB_LIBUSUAL),) which expect 'n' to be
        # an empty string.
        if(value == "n"):
            value = ""

    rc = []
    if(dollarparen != 0):
        rc.append(s[0:dollarparen])
    if(value is not None):
        rc.append(value)
    if(rparen != len(s)):
        rc.append(resolve_vars(s[rparen+1:], makevars))
    return ''.join(rc)

def parse(filename, makevars):
    """ Parses the given file and returns all variable definitions in 'makevars'.
        Some make syntax is supported, such as if-statements, comments, and
        basic +=, :=, and = statements. Actual make rules are ignored.

    """
    m = open(filename, 'r')
    line = ""
    ifs = []
    for l in m:
        l = l.rstrip('\n')
        linelen = len(l)
        line += l
        if(linelen == 0):
            continue
        if(l[linelen-1] == '\\'):
            line = line.rstrip('\\')
            continue
        line.lstrip()

        hashsym = line.find('#')
        if(hashsym != -1):
            if(hashsym == 0):
                line = ""
            else:
                line = line[0:hashsym-1]
        line = resolve_vars(line, makevars).lstrip()
        if(line.startswith('ifeq')):
            process_if(line, ifs, True)
        elif(line.startswith('ifneq')):
            process_if(line, ifs, False)
        elif(line.startswith('ifdef')):
            process_ifdef(line[6:].lstrip(), ifs, makevars, True)
        elif(line.startswith('ifndef')):
            process_ifdef(line[7:].lstrip(), ifs, makevars, False)
        elif(line.startswith('else')):
            ifs[-1] = not ifs[-1]
        elif(line.startswith('endif')):
            ifs.pop()
        elif(if_true(ifs)):
            eq = line.find('=')
            if(eq != -1):
                eqtype = 1
                end = eq
                if(eq != 0):
                    if(line[eq-1] == '+'):
                        eqtype = 2
                        end -= 1
                    elif(line[eq-1] == ':'):
                        end -= 1
                lval = line[0:end-1].strip()
                rval = line[eq+1:].strip().split()
                if(eqtype == 1):
                    makevars[lval] = rval
                else:
                    if(lval in makevars):
                        makevars[lval].extend(rval)
                    else:
                        makevars[lval] = rval
        line = ""

    return makevars

def obj_compile(obj, objfiles):
    """ Print out a :-rule to compile a .c or .S file to generate the given
        object. Note that we avoid looking at the directory itself to see
        which type of file exists, and just use the .[cS] syntax to pick
        up whichever file is there.

        The 'objfiles' array is used to enforce uniqueness, since we only want
        one :-rule for each object file, even though the object file may be
        listed multiple times in the variable list.

    """
    if(obj in objfiles):
        return ""
    cfile = obj[:-2] + ".[cS]"
    print ":", cfile, "|> !cc_linux |>", obj
    objfiles[obj] = True
    return obj

def process_y(obj, makevars, objfiles):
    """ Process a -y object. The object is either a .o file, or a directory.

        For .o files, we have to check whether it just gets compiled from its
        corresponding .c or .S file, or whether it is really a grouping of
        multiple object files that get linked together to form a new .o. This
        is determined by checking whether for 'foo.o' we have a 'foo-y' or
        'foo-objs' variable that defines more objects, which are recursively
        processed.

        For directories, we simply return the directory name plus 'built-in.o'

        The return value is the object name that should be included in the
        linker rule.

    """
    if(obj.endswith('.o')):
        subvars = []

        var_objs = obj[:-2] + "-objs"
        if(var_objs in makevars):
            subvars.extend(makevars[var_objs])
        var_y = obj[:-2] + "-y"
        if(var_y in makevars):
            subvars.extend(makevars[var_y])

        if(subvars):
            objlist = []
            for i in subvars:
                # Make sure we don't have a thing like:
                # file-mmu-y := file-mmu.o
                # which would cause an infinite recursion here
                if(i == obj):
                    # TODO: Need to add to objlist here?
                    obj_compile(obj, objfiles)
                    continue
                objlist.append(process_y(i, makevars, objfiles))
            if(objlist):
                print ":", ' '.join(objlist), "|> !ld_linux |>", obj
            return obj
        else:
            return obj_compile(obj, objfiles)
    elif(obj.endswith('/')):
        return obj + "built-in.o"
    else:
        print >> sys.stderr, "Who knows:",obj

def process_m(obj, makevars):
    """ Not implemented yet - would create modules """
    print "Process m:", obj

makevars = {}
file_to_parse = 'Makefile'

# Process arguments to see if we have been passed in a different filename, or
# any initial variable definitions.
realargs = sys.argv[1:]
for i in realargs:
    eq = i.find('=')
    if(eq != -1):
        makevars[i[0:eq]] = [i[eq+1:]]
    else:
        file_to_parse = i

# Parse the file to get a list of make variables.
parse(file_to_parse, makevars)
objfiles = {}

# Process the 'obj-y' variable to create our built-in.o file.
if('obj-y' in makevars):
    objlist = []
    for i in makevars['obj-y']:
        objlist.append(process_y(i, makevars, objfiles))
    print ":", ' '.join(objlist), "|> !ld_linux |> built-in.o"
else:
    print ": |> ^ EMPTY %o^ ar crs %o |> built-in.o"

# Not implemented yet - process obj-m to create modules
if('obj-m' in makevars):
    for i in makevars['obj-m']:
        process_m(i, makevars)

# Process the 'lib-y' variable to create our lib.a file.
if('lib-y' in makevars):
    objlist = []
    for i in makevars['lib-y']:
        objlist.append(process_y(i, makevars, objfiles))
    print ":", ' '.join(objlist), "|> !ar |> lib.a"

# Process 'extra-y' to compile extra files that aren't linked in to this
# directory's built-in.o or lib.a
if('extra-y' in makevars):
    for i in makevars['extra-y']:
        process_y(i, makevars, objfiles)
