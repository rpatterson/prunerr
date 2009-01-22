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
import transmissionrpc
from transmissionrpc.utils import *

__author__    = u'Erik Svensson <erik.public@gmail.com>'
__version__   = u'0.1'
__copyright__ = u'Copyright (c) 2008 Erik Svensson'
__license__   = u'MIT'

class Helical(cmd.Cmd):
    def __init__(self):
        cmd.Cmd.__init__(self)
        self.intro = u'Helical %s' % (__version__)
        self.verbose = False
        self.set_daemon()
        self.doc_leader = u'''
Helical is a command line interface that communicates with Transmission
bittorent client through json-rpc. To run helical in interactive mode
start without a command.
'''
    
    def set_daemon(self, address=None):
        if address:
            (addr, port) = inet_address(address, transmissionrpc.DEFAULT_PORT)
        else:
            addr = u'localhost'
            port = transmissionrpc.DEFAULT_PORT
        self.address = (addr, port)
        self.tc = transmissionrpc.Client(addr, port, verbose=self.verbose)
        self.prompt = u'Helical %s:%d> ' % (self.address[0], self.address[1])
    
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
    
    def help_quit(self):
        print(u'quit|exit\n')
        print(u'Exit to shell.\n')
    
    def do_quit(self, line):
        sys.exit('')
    #Alias
    do_exit = do_quit
    help_exit = help_quit
    do_EOF = do_quit
    
    def help_add(self):
        print(u'add <torrent file or url> [<target dir> paused=(yes|no) peer-limit=#]\n')
        print(u'Add a torrent to the transfer list.\n')

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
        except transmissionrpc.TransmissionError, e:
            print(u'Failed to add torrent "%s"' % e)
    
    def complete_remove(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def help_remove(self):
        print(u'remove <torrent id> [,<torrent id>, ...]\n')
        print(u'Remove one or more torrents from the transfer list.\n')
    
    def do_remove(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.remove(args)
    
    def complete_start(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def help_start(self):
        print(u'start <torrent id> [,<torrent id>, ...]\n')
        print(u'Start one or more queued torrent transfers.\n')
    
    def do_start(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.start(args)
    
    def complete_stop(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def help_stop(self):
        print(u'stop <torrent id> [,<torrent id>, ...]\n')
        print(u'Stop one or more active torrent transfers.\n')
    
    def do_stop(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.stop(args)
    
    def complete_verify(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def help_verify(self):
        print(u'verify <torrent id> [,<torrent id>, ...]\n')
        print(u'Verify one or more torrent transfers.\n')
    
    def do_verify(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        self.tc.verify(args)
    
    def complete_info(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)
    
    def help_info(self):
        print(u'info [<torrent id>, ...]\n')
        print(u'Get details for a torrent. If no torrent id is provided, all torrents are displayed.\n')
    
    def do_info(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError(u'No torrent id')
        result = self.tc.info(args)
        for id, torrent in result.iteritems():
            print(self._torrent_detail(torrent))
    
    def help_list(self):
        print(u'list\n')
        print(u'List all torrent transfers.\n')
    
    def do_list(self, line):
        args = self.arg_tokenize(line)
        result = self.tc.list()
        self._list_torrents(result)
    
    def help_files(self):
        print(u'files [<torrent id>, ...]\n')
        print(u'Get the file list for one or more torrents\n')
    
    def do_files(self, line):
        args = self.arg_tokenize(line)
        result = self.tc.get_files(args)
        for tid, files in result.iteritems():
            print('torrent id: %d' % tid)
            for fid, file in files.iteritems():
                print('  %d: %s' % (fid, file['name']))
    
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
    
    def help_session(self):
        print(u'session (get|stats)\n')
        print(u'Get session parameters or session statistics.\n')
    
    def do_session(self, line):
        args = self.arg_tokenize(line)
        if len(args[0]) == 0 or args[0] == u'get':
            self.tc.get_session()
            print(self.tc.session)
        elif args[0] == u'stats':
            print(self.tc.session_stats())
    
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
    
    def _list_torrents(self, torrents):
        if len(torrents) > 0:
            print(self._torrent_brief_header())
            for tid, torrent in torrents.iteritems():
                print(self._torrent_brief(torrent))
    
    def _torrent_brief_header(self):
        return u' Id  Done   ETA           Status       Download    Upload      Ratio  Name'
            
    def _torrent_brief(self, torrent):
        s = u'% 3d: ' % (torrent.id)
        try:
            s += u'%5.1f%%' % torrent.progress
        except:
            pass
        try:
            if torrent.fields['eta'] > 0:
                s += u' %- 13s' % torrent.format_eta()
            else:
                s += u' -            '
        except:
            pass
        try:
            s += u' %- 12s' % torrent.status
        except:
            s += u' -status     '
            pass
        try:
            s += u' %5.1f %- 5s' % format_speed(torrent.rateDownload)
            s += u' %5.1f %- 5s' % format_speed(torrent.rateUpload)
        except:
            s += u' -rate     '
            s += u' -rate     '
            pass
        try:
            s += u' %6.2f' % torrent.ratio
        except:    
            s += u' -ratio'
            pass
        s += u' ' + torrent.name
        return s
    
    def _torrent_detail(self, torrent):
        s = ''
        s +=   '            id: ' + str(torrent.fields['id'])
        s += '\n          name: ' + torrent.fields['name']
        s += '\n          hash: ' + torrent.fields['hashString']
        s += '\n'
        try: # size
            f = ''
            f += '\n      progress: %.2f%%' % torrent.progress
            f += '\n         total: %.2f %s' % format_size(torrent.totalSize)
            f += '\n      reqested: %.2f %s' % format_size(torrent.sizeWhenDone)
            f += '\n     remaining: %.2f %s' % format_size(torrent.leftUntilDone)
            f += '\n      verified: %.2f %s' % format_size(torrent.haveValid)
            f += '\n  not verified: %.2f %s' % format_size(torrent.haveUnchecked)
            s += f + '\n'
        except KeyError:
            pass
        try: # activity
            f = ''
            f += '\n        status: ' + str(torrent.status)
            f += '\n      download: %.2f %s' % format_speed(torrent.rateDownload)
            f += '\n        upload: %.2f %s' % format_speed(torrent.rateUpload)
            f += '\n     available: %.2f %s' % format_size(torrent.desiredAvailable)
            f += '\ndownload peers: ' + str(torrent.peersSendingToUs)
            f += '\n  upload peers: ' + str(torrent.peersGettingFromUs)
            s += f + '\n'
        except KeyError:
            pass
        try: # history
            f = ''
            f += '\n         ratio: %.2f' % torrent.ratio
            f += '\n    downloaded: %.2f %s' % format_size(torrent.downloadedEver)
            f += '\n      uploaded: %.2f %s' % format_size(torrent.uploadedEver)
            f += '\n        active: ' + format_timestamp(torrent.activityDate)
            f += '\n         added: ' + format_timestamp(torrent.addedDate)
            f += '\n       started: ' + format_timestamp(torrent.startDate)
            f += '\n          done: ' + format_timestamp(torrent.doneDate)
            s += f + '\n'
        except KeyError:
            pass
        return s

def main(args=None):
    """Main entry point"""
    if args is None:
        args = sys.argv[1:]
    
    helical = Helical()
    
    # parse flags
    if len(args) > 0:
        if args[0] == u'-d':
            helical.verbose = True
            args = args[1:]
        elif args[0] in [u'-h', u'--help', u'help']:
            arg = ''
            try:
                arg = args[1]
            except:
                pass
            sys.exit(helical.do_help(arg))
    
    # parse daemon address
    if len(args) > 0:
        try:
            helical.set_daemon(args[0])
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
        helical.onecmd(command + command_args)
    else:
        try:
            helical.tc.list()
        except transmissionrpc.TransmissionError, e:
            print(e)
            helical.exit(helical.do_help(u''))
        
        try:
            helical.cmdloop()
        except KeyboardInterrupt:
            helical.do_quit('')

if __name__ == '__main__':
    sys.exit(main())
