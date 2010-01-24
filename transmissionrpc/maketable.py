#!/usr/bin/env python
# encoding: utf-8

import transmissionrpc.constants as trc
import transmissionrpc.utils as tru

headers = ('Argument', 'RPC', 'Replaced by', 'Description')

def heading(a, b, c, d):
    ad = ''.join(['=' for i in xrange(0, a)])
    bd = ''.join(['=' for i in xrange(0, b)])
    cd = ''.join(['=' for i in xrange(0, c)])
    dd = ''.join(['=' for i in xrange(0, d)])
    return ad + ' ' + bd + ' ' + cd + ' ' + dd + '\n'

def tablesfor(name, category, fd):
    for op, args in category.iteritems():
        maxarglen = len(headers[0])
        maxverlen = len(headers[1])
        maxrpllen = len(headers[2])
        maxdsclen = len(headers[3])
        fd.write('%s-%s\n\n' % (name, op))
        for arg, arginfo in args.iteritems():
            arg = '``%s``' % tru.make_python_name(arg)
            if len(arg) > maxarglen:
                maxarglen = len(arg)

            if isinstance(arginfo[2], int):
                ver = '%d - %d' % (arginfo[1], arginfo[2])
            else:
                ver = '%d - ' % (arginfo[1])
            if len(ver) > maxverlen:
                maxverlen = len(ver)

            if isinstance(arginfo[4], str):
                rpl = arginfo[4]
            else:
                rpl = ''
            if len(rpl) > maxrpllen:
                maxrpllen = len(rpl)

            if isinstance(arginfo[5], str):
                dsc = arginfo[5]
            else:
                dsc = ''
            if len(dsc) > maxdsclen:
                maxdsclen = len(dsc)
        
        fd.write(heading(maxarglen, maxverlen, maxrpllen, maxdsclen))
        fmt = '%%- %ds %%- %ds %%- %ds %%- %ds\n' % (maxarglen, maxverlen, maxrpllen, maxdsclen)
        fd.write(fmt % headers)
        fd.write(heading(maxarglen, maxverlen, maxrpllen, maxdsclen))
        
        for arg, arginfo in sorted(args.iteritems()):
            arg = '``%s``' % tru.make_python_name(arg)
            if isinstance(arginfo[2], int):
                ver = '%d - %d' % (arginfo[1], arginfo[2])
            else:
                ver = '%d - ' % (arginfo[1])
            if isinstance(arginfo[4], str):
                rpl = arginfo[4]
            else:
                rpl = ''
            if isinstance(arginfo[5], str):
                dsc = arginfo[5]
            else:
                dsc = ''
            fd.write(fmt % (arg, ver, rpl, dsc))
        fd.write(heading(maxarglen, maxverlen, maxrpllen, maxdsclen))
        fd.write('\n')
    
def main():
    fd = open('tables.rst', 'w')
    tablesfor('torrent', trc.TORRENT_ARGS, fd)
    tablesfor('session', trc.SESSION_ARGS, fd)
    fd.close()

if __name__ == '__main__':
    main()

