#! /usr/bin/python

import sys
import tup_client

def if_true(ifs):
    if(not ifs):
        return True
    if(False in ifs):
        return False
    return True

def process_if(line, ifs, val):
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

def parse(filename):
    m = open(filename, 'r')
    line = ""
    makevars = {}
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
    if(obj in objfiles):
        return ""
    cfile = obj[:-2] + ".c"
    print ":", cfile, "|> !cc_linux |>", obj
    objfiles[obj] = True
    return obj

def process_y(obj, makevars, objfiles):
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
    print "Process m:", obj

makevars = parse('Makefile')
cfiles = {}

if('obj-y' in makevars):
    objlist = []
    for i in makevars['obj-y']:
        objlist.append(process_y(i, makevars, cfiles))
    print ":", ' '.join(objlist), "|> !ld_linux |> built-in.o"
else:
    print ": |> ^ EMPTY %o^ ar crs %o |> built-in.o"

if('obj-m' in makevars):
    for i in makevars['obj-m']:
        process_m(i, makevars)
