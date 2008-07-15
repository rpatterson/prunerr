#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik@coldstar.net>

"""
vxl
###

About
=====

vxl is short for växel, the swedish word for gearbox.
"""

import sys, os, os.path, re, socket, urllib2, base64
try:
    import readline
except:
    pass
import cmd
import transmission

class INetAddressError(Exception):
    pass

def inet_address(address, default_port = None, default_address='localhost'):
    addr = address.split(':')
    if len(addr) == 1:
        try:
            port = int(addr[0])
            addr = default_address
        except:
            addr = addr[0]
            port = default_port
    elif len(addr) == 2:
        port = int(addr[1])
        addr = addr[0]
    else:
        raise INetAddressError('Cannot parse address "%s".' % address)
    try:
        socket.getaddrinfo(addr, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror, e:
        raise INetAddressError('Cannot look up address "%s".' % address)
    return (addr, port)

class Vxl(cmd.Cmd):
    def __init__(self, args, verbose):
        cmd.Cmd.__init__(self)
        self.prompt = 'vxl> '
        (addr, port) = inet_address(args[0], 9090)
        self.tc = transmission.TransmissionClient(addr, port, verbose=verbose)
        if len(args[1:]) > 0:
            self.onecmd(' '.join(args[1:]))
        else:
            self.cmdloop()
    
    def do_quit(self, line):
        sys.exit()
    #Alias
    do_exit = do_quit
    do_EOF = do_quit

    def do_add(self, *args):
        if len(args) == 0:
            raise ValueError('No torrent url')
        torrent_url = args[0]
        file = None
        if os.path.exists(torrent_url):
            file = open(torrent_url, 'r')
        else:
            try:
                file = urllib2.urlopen(torrent_url)
            except:
                file = None
        if file:
            data = base64.b64encode(file.read())
            print(u'add ' + torrent_url)
            self.tc.add(data)
        else:
            print(u"Could'n add " + torrent_url)
    
    def do_remove(self, arg):
        args = re.split('\W+', arg)
        if len(args) == 0:
            raise ValueError('No torrent id')
        self.tc.remove(args)
    
    def do_start(self, arg):
        args = re.split('\W+', arg)
        if len(args) == 0:
            raise ValueError('No torrent id')
        self.tc.start(args)
    
    def do_stop(self, arg):
        args = re.split('\W+', arg)
        if len(args) == 0:
            raise ValueError('No torrent id')
        self.tc.stop(args)
    
    def do_verify(self, arg):
        args = re.split('\W+', arg)
        if len(args) == 0:
            raise ValueError('No torrent id')
        self.tc.verify(args)
    
    def do_list(self, arg):
        args = re.split('[\s,;]+', arg)
        self.tc.list(args)
        for id, torrent in self.tc.torrents.iteritems():
            print("%d: %s" % (torrent.id, torrent.name))
    
    def do_request(self, arg):
        (method, sep, args) = arg.partition(' ')
        try:
            args = eval(args)
        except SyntaxError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        verbose = self.tc.verbose
        self.tc.verbose = True
        self.tc._request(method, args)
        self.tc.verbose = verbose

if __name__ == '__main__':
    argv_offset = 1
    verbose = False
    if sys.argv[1] == '-v':
        argv_offset = 2
        verbose = True
    if len(sys.argv[argv_offset:]) < 1:
        print(u'vxl <address> [<cmd>]')
        sys.exit()
    vxl = Vxl(sys.argv[argv_offset:], verbose)
