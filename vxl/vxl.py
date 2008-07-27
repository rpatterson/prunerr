#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

import sys, os, os.path, re
import urllib2, base64, shlex
try:
    import readline
except:
    pass
import cmd
import transmission
from utils import inet_address, INetAddressError
from constants import DEFAULT_PORT

__author__    = u"Erik Svensson <erik.public@gmail.com>"
__version__   = u"0.1"
__copyright__ = u"Copyright (c) 2008 Erik Svensson"
__license__   = u"MIT"

class Vxl(cmd.Cmd):
    def __init__(self):
        cmd.Cmd.__init__(self)
        self.intro = u'Vxl %s' % (__version__)
        self.verbose = False
        self.set_daemon()
    
    def set_daemon(self, address=None):
        if address:
            (addr, port) = inet_address(address, DEFAULT_PORT)
        else:
            addr = u'localhost'
            port = DEFAULT_PORT
        self.address = (addr, port)
        self.tc = transmission.Transmission(addr, port, verbose=self.verbose)
        self.prompt = u'vxl %s:%d> ' % (self.address[0], self.address[1])
    
    def arg_tokenize(self, argstr):
        return [unicode(token, 'utf-8') for token in shlex.split(argstr.encode('utf-8'))] or ['']

    def word_complete(self, text, words):
        suggestions = []
        for word in words:
            if word.startswith(text):
                suggestions.append(word)
        return suggestions
    
    def _complete_torrent(self, name, offset):
        words = [torrent.name for id, torrent in self.tc.torrents.iteritems()]
        suggestions = []
        cut_index = len(name) - offset
        for word in words:
            if word.startswith(name):
                suggestions.append(word[cut_index:])
        return suggestions
    
    def _complete_torrent_command(self, text, line, begidx, endidx):
        args = self.arg_tokenize(line)
        item = args[-1] if len(args) > 1 else ''
        return self._complete_torrent(item, endidx - begidx)
    
    def do_quit(self, line):
        sys.exit('')
    #Alias
    do_exit = do_quit
    do_EOF = do_quit
    
    def help_add(self):
        print(u'Add a torrent to the transfer list.\n')
        print(u'add <torrent file or url> [<target dir> paused=yes|no peer-limit=#]\n')

    def do_add(self, line):
        args = self.arg_tokenize(line)
        
        if len(args) == 0:
            print(u'Specify a torrent file or url')
            return
        
        torrent_url = args[0]
        args = args[1:]
        torrent_file = None
        if os.path.exists(torrent_url):
            torrent_file = open(torrent_url, 'r')
        else:
            try:
                torrent_file = urllib2.urlopen(torrent_url)
            except:
                torrent_file = None
        if not torrent_file:
            print(u'Couldn\'t find torrent "%s"' % torrent_url)
            return
        
        add_args = {}
        if len(args) > 0:
            for arg in args:
                try:
                    (k,v) = arg.split('=')
                    add_args[str(k)] = str(v)
                except:
                    if 'download_dir' not in add_args:
                        try:
                            os.mkdir(arg)
                            add_args['target'] = arg
                            continue
                        except:
                            pass
                    print(u'Unknown argument: "%s"' % arg)
        
        torrent_data = base64.b64encode(torrent_file.read())
        try:
            self.tc.add(torrent_data, **add_args)
        except transmission.TransmissionError, e:
            print(u'Failed to add torrent "%s"' % e)
    
    def complete_remove(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def do_remove(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.remove(args)
    
    def complete_start(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def do_start(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.start(args)
    
    def complete_stop(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def do_stop(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.stop(args)
    
    def complete_verify(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def do_verify(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.verify(args)
    
    def complete_info(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def do_info(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        result = self.tc.info(args)
        for id, torrent in result.iteritems():
            print(torrent.detail())
    
    def do_list(self, line):
        args = self.arg_tokenize(line)
        result = self.tc.list()
        print(transmission.Torrent.brief_header())
        for id, torrent in result.iteritems():
            print(torrent.brief())
    
    def do_files(self, line):
        args = self.arg_tokenize(line)
        result = self.tc.files(args)
        for id, torrent in result.iteritems():
            print(torrent.files())
    
    def do_set(self, line):
        args = self.arg_tokenize(line)
        set_args = {}
        ids = []
        add_ids = True
        
        if len(args) > 0:
            for arg in args:
                try:
                    (k,v) = arg.split(u'=')
                    set_args[str(k)] = str(v)
                    add_ids = False
                except:
                    if add_ids:
                        ids.append(arg)
                    else:
                        print(u'Unknown argument: "%s"' % arg)        
        if len(ids) > 0:
            result = self.tc.change(ids, **set_args)
    
    def complete_session(self, text, line, begidx, endidx):
        return self.word_complete(text, [u'get', u'set', u'stats'])
    
    def do_session(self, line):
        args = self.arg_tokenize(line)
        if args[0] == u'get':
            self.tc.session_get()
            print(self.tc.session)
        elif args[0] == u'stats':
            result = self.tc.session_stats()
            for k, v in result.iteritems():
                print("% 32s : %s" % (k, v))
        else:
            raise NotImplementedError(line)
    
    def do_request(self, line):
        (method, sep, args) = line.partition(' ')
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

def main(args=None):
    """Main entry point"""
    if args is None:
        args = sys.argv[1:]
    
    vxl = Vxl()
    
    # parse flags
    if len(args) > 0:
        if args[0] == u'-d':
            vxl.verbose = True
            args = args[1:]
        elif args[0] in [u'-h', u'--help', u'help']:
            arg = ''
            try:
                arg = args[1]
            except:
                pass
            sys.exit(vxl.do_help(arg))
    
    # parse daemon address
    if len(args) > 0:
        try:
            vxl.set_daemon(args[0])
            args = args[1:]
        except:
            pass
    
    # parse command and arguments
    if len(args) > 0:
        # we must put arguments in quotes to help the world peace
        command_args = u''
        command = args[0]
        if len(args) > 0:
            command_args += u' '.join([u'"%s"' % arg for arg in args[1:]])
        vxl.onecmd(command + command_args)
    else:
        try:
            vxl.tc.list()
        except transmission.TransmissionError, e:
            print(e)
            sys.exit(vxl.do_help(u''))
        
        try:
            vxl.cmdloop()
        except KeyboardInterrupt:
            vxl.do_quit('')

if __name__ == '__main__':
    sys.exit(main())
