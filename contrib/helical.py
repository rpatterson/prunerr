#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

import sys, os, os.path, re, itertools
import socket, urllib2, urlparse, base64, shlex
import shutil
import subprocess
import time
import logging
from logging import handlers
from optparse import OptionParser
try:
    import readline
except:
    pass
import cmd
import transmissionrpc
from transmissionrpc import utils
from transmissionrpc.constants import DEFAULT_PORT

__author__    = u'Erik Svensson <erik.public@gmail.com>'
__version__   = u'0.2'
__copyright__ = u'Copyright (c) 2008 Erik Svensson'
__license__   = u'MIT'

logger = logging.getLogger('transmissionrpc.helical')


def splitpath(path, platform=os.path):
    """Split all path elements"""
    result = []
    head, tail = platform.split(path)
    result.append(tail)
    while head:
        head, tail = platform.split(head)
        result.append(tail or platform.sep)
        if not tail and head == platform.sep:
            break
    result.reverse()
    return result

def log_rmtree_error(function, path, excinfo):
    logger.error(
        'Error removing %r (%s)',
        path, '.'.join((function.__module__, function.__name__)),
        exc_info=excinfo)


class Helical(cmd.Cmd):

    settings = {}

    def __init__(self, settings_file=None):
        cmd.Cmd.__init__(self)
        self.intro = u'Helical %s' % (__version__)
        self.doc_leader = u'''
Helical is a command line interface that communicates with Transmission
bittorent client through json-rpc. To run helical in interactive mode
start without a command.
'''
        self.settings_file = settings_file or os.path.join(
            get_home(), 'info', 'settings.json')

    def connect(self, address=None, port=None, username=None, password=None):
        self.tc = transmissionrpc.Client(address, port, username, password)
        urlo = urlparse.urlparse(self.tc.url)
        if urlo.port:
            self.prompt = u'Helical %s:%d> ' % (urlo.hostname, urlo.port)
        else:
            self.prompt = u'Helical %s> ' % (urlo.hostname)
        self.do_update('')

    def arg_tokenize(self, argstr):
        return [unicode(token, 'utf-8') for token in shlex.split(argstr.encode('utf-8'))] or ['']

    def word_complete(self, text, words):
        suggestions = []
        for word in words:
            if word.startswith(text):
                suggestions.append(word)
        return suggestions

    def _complete_torrent(self, name, offset):
        words = [torrent.name for torrent in self.torrents]
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

    def help_update(self):
        print(u'update\n')
        print(u'Update the torrents list and settings.\n')

    def do_update(self, line):
        self.torrents = self.tc.get_torrents()
        if isinstance(self.settings_file, (str, unicode)):
            import json
            self.settings = json.load(open(self.settings_file))

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

    def do_magnet(self, line):
        args = self.arg_tokenize(line)

        if len(args) == 0:
            print(u'Specify a torrent file or url')
            return

        torrent_url = args[0]

        try:
            self.tc.add_uri(torrent_url)
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
        result = self.tc.get_torrents(args)
        for torrent in result:
            print(self._torrent_detail(torrent))

    def help_list(self):
        print(u'list\n')
        print(u'List all torrent transfers.\n')

    def do_list(self, line):
        args = self.arg_tokenize(line)
        if args:
            raise ValueError(u"'list' takes no arguments")
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
            self.tc.change(ids, **set_args)

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

    def help_copy(self):
        print(u'copy <torrent id> destination [-- command...]\n')
        print(u'Copy the torrent to the destination by piping the relative\n'
              u'torrent file paths to the shell command on stdin.\n'
              u'Leaves the command running in the background.\n'
              u'The command defaults to: rsync -tSmP --files-from=-\n'
              u'Example: copy 1 192.168.1.1:/path/to/library/ '
              u'rsync -tSmPvv --files-from=-\n')

    def do_copy(self, line):
        """Copy a torrent using the given command."""
        args = self.arg_tokenize(line)
        if len(args) < 2:
            raise ValueError(
                u"'copy' command requires a torrent id and a destination path")
        elif len(args) < 3:
            args.extend(['rsync', '-tSmP', '--files-from=-'])
        torrent_id, destination = args[:2]
        command = args[2:]
        self.copy(torrent_id, destination, command)

    def copy(self, torrent_id, destination, command):
        """Launch the copy subprocess and return the popen object."""
        torrent = self.tc.get_torrent(torrent_id)
        session = self.tc.get_session()
        relative = os.path.relpath(torrent.downloadDir,
                                   session.download_dir).encode('utf-8')

        # Use a temporary file to keep feeding the file list to the
        # subprocess from blocking us
        import tempfile
        files = tempfile.TemporaryFile()
        files.writelines(os.path.join(relative,
                                      file_['name'].encode('utf-8')) + '\n'
                         for file_ in torrent.files().itervalues()
                         if file_.get('selected') and os.path.exists(
                                 os.path.join(
                                     torrent.downloadDir.encode('utf-8'),
                                     file_['name'].encode('utf-8'))))
        files.seek(0)

        command.extend([session.download_dir.encode('utf-8'), destination])
        logger.info('Launching copy command: %s', ' '.join(command))
        popen = subprocess.Popen(command, stdin=files)

        return popen

    def help_daemon(self):
        print(u'daemon destination [command...]\n')
        print(u"""\
Run as a monitoring process that does a series of operations every
'daemon-poll' seconds from settings JSON.

1. Run 'copy' on the smallest seeding torrent that hasn't already been moved to
   the 'seeding-dir' directory from settings JSON using the destination and
   command (see 'help copy' for details).  This also kills an existing running
   copy if the smallest seeding torrent is a different torrent.  If the command
   fails with a return/exit code included in "daemon-retry-codes" from settings
   JSON, then the copy will be retried.  Otherwise, the torrent will be paused
   so as not to keep retrying a failing copy.  The default "daemon-retry-codes"
   cover the codes rsync uses for network issues or intentional
   signals/interruptions/kills (10, 12, 20, 30, and 35).
2. If a torrent copy process succeeded, move the torrent to the 'seeding-dir'.
3. Run 'update_priorities'
4. Run 'free_space'
5. Run 'verify_corrupted'
6. Resume any previously verified torrents.

'daemon-poll' defaults to 15 minutes, and 'seeding-dir' defaults to a 'seeding'
directory next to the 'download-dir'.
""")

    def do_daemon(self, line):
        """Loop running several regular commands every interval."""
        # setup syslog for daemon messages
        root = logging.getLogger()
        for handler in root.handlers:
            if isinstance(handler, handlers.SysLogHandler):
                break
        else:
            # Linux
            address = '/dev/log'
            if not os.path.exists(address):
                # OS X
                address = '/var/run/syslog'
            if os.path.exists(address):
                handler = handlers.SysLogHandler(
                    address, facility=handlers.SysLogHandler.LOG_DAEMON)
            else:
                # Windows
                handler = handlers.SysLogHandler(
                    facility=handlers.SysLogHandler.LOG_DAEMON)
            handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
            handler.setLevel(logging.INFO)
            root.addHandler(handler)

        self.popen = self.copying = None
        self.corrupt = {}
        while True:
            try:
                self._daemon_inner(line)
            except socket.error:
                logger.exception('Connection error while running daemon')
                pass

            while True:
                try:
                    # update everything from the server
                    self.tc.get_session()
                    self.do_update('')
                except socket.error:
                    logger.exception(
                        'Connection error while updating from server')
                    pass
                else:
                    break

    def _daemon_inner(self, line):
        """'daemon' command innner loop."""
        session = self.tc.get_session()
        seeding_dir = self.settings.get(
            'seeding-dir', os.path.join(
                os.path.dirname(session.download_dir), 'seeding'))
        retry_codes = self.settings.get(
            'daemon-retry-codes', [10, 12, 20, 30, 35])

        # Keep track of torrents being verified to resume them
        # when verification is complete
        self.corrupt.update(self.verify_corrupted())
        for torrent_id, torrent in self.corrupt.items():
            torrent.update()
            if not torrent.status.startswith('check'):
                logger.info('Resuming verified torrent: %s', torrent)
                self.tc.start([torrent_id])
                torrent.update()
                del self.corrupt[torrent_id]
        if self.corrupt:
            logger.info('Waiting for torrents to verify:\n%s',
                        '\n'.join(map(str, self.corrupt.itervalues())))

        # Find any torrents that have finished downloading but
        # hasn't already been moved to the seeding directory
        to_copy = sorted(
            (torrent for torrent in self.torrents
             if torrent.status == 'seeding' and
             os.path.relpath(
                 torrent.downloadDir, seeding_dir
                 ).startswith(os.pardir + os.sep)),
            # copy smaller torrents first
            key=lambda item: item.totalSize)
        if self.popen is not None:
            if self.popen.poll() is None:
                if not to_copy or self.copying.id == to_copy[0].id:
                    logger.info('Letting running copy finish: %s',
                                self.copying)
                    to_copy = None
                else:
                    logger.info('Terminating running copy: %s', self.copying)
                    self.popen.terminate()
            elif self.popen.returncode == 0:
                # Copy process succeeded
                self.move(self.copying, session.download_dir, seeding_dir)
                if to_copy and self.copying.id == to_copy[0].id:
                    to_copy.pop(0)
                self.copying = None
                self.popen = None
            elif self.popen.returncode not in retry_codes:
                logger.error(
                    'Copy failed with return code %s, pausing %s',
                    self.popen.returncode, self.copying)
                self.tc.stop_torrent([self.copying.id])
                self.copying.update()

        if to_copy:
            logger.info('Copying torrent: %s', to_copy[0])
            args = self.arg_tokenize(line)
            destination = args[0]
            command = args[1:]
            self.popen = self.copy(to_copy[0].id, destination, command)
            self.copying = to_copy[0]

        # Do any other cleanup
        self.do_update_priorities('')
        self.do_free_space('')

        # Wait for the next interval
        start = time.time()
        poll = self.settings.get("daemon-poll", 15 * 60)
        # Loop early if the copy process finishes early
        while ((self.popen is None or self.popen.poll() is None) and
               time.time() - start < poll):
            time.sleep(1)

    def move(self, torrent, src_path, dst_path):
        """Move a torrent preserving subpath."""
        relative = os.path.relpath(
            torrent.downloadDir, os.path.dirname(src_path))
        split = splitpath(relative)[1:]
        subpath = split and os.path.join(*split) or ''
        torrent_location = os.path.join(dst_path, subpath)
        logger.info('Moving torrent %s to %s', torrent, torrent_location)
        self.tc.move([torrent.id], torrent_location)
        torrent.update()

    def help_update_priorities(self):
        print(u'update_priorities\n')
        print(u'Set the bandwidth priority for each torrent using the '
              u'settings JSON\n"tracker-priorities" object where each property '
              u'name is a tracker\nand the value is the priority.')

    def do_update_priorities(self, line):
        """Set torrent priority by private/public trackers"""
        if line:
            raise ValueError(u"'update_priorities' command doesn't accept args")

        changed = []
        for torrent in self.torrents:
            found = False
            for tracker in torrent.trackers:
                for action in ('announce', 'scrape'):
                    parsed = urlparse.urlsplit(tracker[action])
                    for hostname, priority in self.settings[
                            'tracker-priorities'].iteritems():
                        if not parsed.hostname.endswith(hostname):
                            continue

                        found = True
                        if torrent.bandwidthPriority != priority:
                            logger.info('Marking torrent %s as priority %s',
                                        torrent, priority)
                            self.tc.change([torrent.id],
                                            bandwidthPriority=priority)
                            torrent.update()
                            changed.append(torrent)

                        break
                    if found:
                        break
                if found:
                    break

            else:
                priority = self.settings.get('default-priority')
                if (priority is None or
                    torrent.bandwidthPriority == priority):
                    continue
                logger.info('Marking torrent %s as default priority %s',
                            torrent, priority)
                self.tc.change([torrent.id], bandwidthPriority=priority)
                torrent.update()
                changed.append(torrent)

    def help_free_space(self):
        print(u'free_space\n')
        print(u"Delete torrents if there's not enough free space\n"
              u'according to the "free-space" JSON setting.')

    def do_free_space(self, line):
        """Delete some torrents if running out of disk space."""
        if line:
            raise ValueError(u"'free_space' command doesn't accept args")

        session = self.tc.get_session()
        if session.download_dir_free_space >= self.settings["free-space"]:
            if self.tc.get_session().speed_limit_down_enabled:
                kwargs = dict(speed_limit_down_enabled=False)
                logger.info('Resuming downloading: %s', kwargs)
                self.tc.set_session(**kwargs)
            return

        # First find orphaned files, remove smallest files first
        download_dirs = (
            self.settings.get('seeding-dir', os.path.join(
                os.path.dirname(session.download_dir), 'seeding')),
            session.download_dir, session.incomplete_dir)
        # Assemble all directories whose descendants are torrents
        torrent_dirs = set()
        torrent_paths = set()
        for torrent in self.torrents:
            torrent_dir, tail = os.path.split(torrent.downloadDir + os.sep)
            # Include the ancestors of the torrent's path
            # so we know what dirs to descend into when looking for orphans
            while torrent_dir not in torrent_dirs or torrent_dir != os.sep:
                torrent_dirs.add(torrent_dir)
                torrent_dir, tail = os.path.split(torrent_dir)
            torrent_paths.add(os.path.join(torrent.downloadDir, torrent.name))
        # Sort the orphans by total directory size
        du_cmd = ['du', '-s', '--files0-from=-']  # TODO Windows compatibility
        du = subprocess.Popen(
            du_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        orphans = sorted(
            itertools.chain(*(
                self._list_orphans(
                    torrent_dirs, torrent_paths, du, download_dir)
                for download_dir in download_dirs)),
            key=lambda orphan: int(orphan[0]))
        du.stdin.close()
        # Remove orphans, smallest first until enough space is freed
        # or there are no more orphans
        while (
                session.download_dir_free_space < self.settings["free-space"]
                and orphans):
            size, orphan = orphans.pop(0)
            logger.warn(
                'Deleting orphaned path %r to free space: '
                '%0.2f %s + %0.2f %s', orphan,
                *itertools.chain(
                    utils.format_size(session.download_dir_free_space),
                    utils.format_size(size)))
            if os.path.isdir(orphan):
                shutil.rmtree(orphan, onerror=log_rmtree_error)
            else:
                os.remove(orphan)
            session.update()
        du.wait()
        if du.returncode:
            raise subprocess.CalledProcessError(du.returncode, du_cmd)
        if session.download_dir_free_space >= self.settings["free-space"]:
            # No need to process seeding torrents
            # if removing orphans already freed enough space
            if self.tc.get_session().speed_limit_down_enabled:
                kwargs = dict(speed_limit_down_enabled=False)
                logger.info('Resuming downloading: %s', kwargs)
                self.tc.set_session(**kwargs)
            return

        # Next remove seeding and copied torrents
        by_ratio = sorted(
            ((index, torrent) for index, torrent in enumerate(self.torrents)
             # only those previously synced and moved
             if torrent.status == 'seeding'
             and torrent.downloadDir.startswith(self.settings.get(
                 'seeding-dir', os.path.join(
                     os.path.dirname(session.download_dir), 'seeding')))),
            # remove lowest priority and highest ratio first
            key=lambda item: (0 - item[1].bandwidthPriority, item[1].ratio))
        removed = []
        while session.download_dir_free_space < self.settings["free-space"]:
            if not by_ratio:
                logger.error(
                    'Running out of space but no torrents can be removed: %s',
                    session.download_dir_free_space)
                kwargs = dict(speed_limit_down=0,
                              speed_limit_down_enabled=True)
                logger.info('Stopping downloading: %s', kwargs)
                self.tc.set_session(**kwargs)
                break
            index, remove = by_ratio.pop()
            logger.info(
                'Deleting seeding torrent %s to free space, '
                '%0.2f %s + %0.2f %s: priority=%s, ratio=%0.2f', remove,
                *(utils.format_size(session.download_dir_free_space) +
                  utils.format_size(remove.totalSize) +
                  (remove.bandwidthPriority, remove.ratio)))
            self.tc.remove(remove.id, delete_data=True)
            removed.append(remove)
            self.torrents.pop(index)

            session.update()
        else:
            if self.tc.get_session().speed_limit_down_enabled:
                kwargs = dict(speed_limit_down_enabled=False)
                logger.info('Resuming downloading: %s', kwargs)
                self.tc.set_session(**kwargs)

    def _list_orphans(self, torrent_dirs, torrent_paths, du, path):
        """Recursively list paths that aren't a part of any torrent."""
        for entry in os.listdir(path):
            entry_path = os.path.join(
                path, entry.decode('utf-8')).encode('utf-8')
            if (
                    entry_path not in torrent_paths and
                    entry_path not in torrent_dirs):
                du.stdin.write(entry_path + '\0')
                size, du_path = du.stdout.readline()[:-1].split('\t', 1)[:2]
                yield (size, entry_path)
            elif entry_path in torrent_dirs:
                for orphan in self._list_orphans(
                        torrent_dirs, torrent_paths, du, entry_path):
                    yield orphan

    def help_verify_corrupted(self):
        print(u'verify_corrupted\n')
        print(u"Verify local data for any corrupt torrents.")

    def do_verify_corrupted(self, line):
        """Verify local data if corrupt."""
        if line:
            raise ValueError(u"'verify_corrupted' command doesn't accept args")
        self.verify_corrupted()

    def verify_corrupted(self):
        """Verify local data if corrupt."""
        self.do_update('')
        corrupt = dict(
            (torrent.id, torrent) for torrent in self.torrents if (
                torrent.status in ['stopped', 'seeding'] and (
                    torrent.error == 3 or torrent.corruptEver)))
        if corrupt:
            logger.info('Verifying corrupt torrents:\n%s',
                        '\n'.join(map(str, corrupt.itervalues())))
            self.tc.verify(corrupt.keys())
            for torrent in corrupt.itervalues():
                torrent.update()

        return corrupt

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
        return u' Id   Done   ETA           Status       Download     Upload       Ratio  Name'

    def _torrent_brief(self, torrent):
        s = u'% 3d: ' % (torrent.id)
        try:
            s += u'%5.1f%%' % torrent.progress
        except:
            pass
        try:
            s += u' %- 13s' % torrent.format_eta()
        except:
            s += u' -            '
        try:
            s += u' %- 12s' % torrent.status
        except:
            s += u' -status     '
            pass
        try:
            s += u' %6.1f %- 5s' % utils.format_speed(torrent.rateDownload)
            s += u' %6.1f %- 5s' % utils.format_speed(torrent.rateUpload)
        except:
            s += u' -rate      '
            s += u' -rate      '
            pass
        try:
            s += u' %4.2f  ' % torrent.ratio
        except:
            s += u' -ratio'
            pass
        s += u' ' + torrent.name
        return s

    def _torrent_detail(self, torrent):
        s = ''
        s +=   '            id: ' + str(torrent.id)
        s += '\n          name: ' + torrent.name
        s += '\n          hash: ' + torrent.hashString
        s += '\n'
        try: # size
            f = ''
            f += '\n      progress: %.2f%%' % torrent.progress
            f += '\n         total: %.2f %s' % utils.format_size(torrent.totalSize)
            f += '\n      reqested: %.2f %s' % utils.format_size(torrent.sizeWhenDone)
            f += '\n     remaining: %.2f %s' % utils.format_size(torrent.leftUntilDone)
            f += '\n      verified: %.2f %s' % utils.format_size(torrent.haveValid)
            f += '\n  not verified: %.2f %s' % utils.format_size(torrent.haveUnchecked)
            s += f + '\n'
        except KeyError:
            pass
        try: # activity
            f = ''
            f += '\n        status: ' + str(torrent.status)
            f += '\n      download: %.2f %s' % utils.format_speed(torrent.rateDownload)
            f += '\n        upload: %.2f %s' % utils.format_speed(torrent.rateUpload)
            f += '\n     available: %.2f %s' % utils.format_size(torrent.desiredAvailable)
            f += '\ndownload peers: ' + str(torrent.peersSendingToUs)
            f += '\n  upload peers: ' + str(torrent.peersGettingFromUs)
            s += f + '\n'
        except KeyError:
            pass
        try: # history
            f = ''
            f += '\n         ratio: %.2f' % torrent.ratio
            f += '\n    downloaded: %.2f %s' % utils.format_size(torrent.downloadedEver)
            f += '\n      uploaded: %.2f %s' % utils.format_size(torrent.uploadedEver)
            f += '\n        active: ' + utils.format_timestamp(torrent.activityDate)
            f += '\n         added: ' + utils.format_timestamp(torrent.addedDate)
            f += '\n       started: ' + utils.format_timestamp(torrent.startDate)
            f += '\n          done: ' + utils.format_timestamp(torrent.doneDate)
            s += f + '\n'
        except KeyError:
            pass
        return s

def get_home():
    try:
        # Don't rely on os.environ['HOME'] such as under cron jobs
        import pwd
        return pwd.getpwuid(os.getuid()).pw_dir
    except ImportError:
        # Windows
        return os.path.expanduser('~')

def main(args=None):
    """Main entry point"""
    if sys.version_info[0] <= 2 and sys.version_info[1] <= 5:
        socket.setdefaulttimeout(30)
    if args is None:
        args = sys.argv[1:]
    parser = OptionParser(usage='Usage: %prog [options] [[address]:[port]] [command]')
    parser.add_option('-u', '--username', dest='username',
                    help='Athentication username.')
    parser.add_option('-p', '--password', dest='password',
                    help='Athentication password.')
    parser.add_option('-s', '--settings', dest='settings',
                      help='JSON file containing settings '
                      '[default: ~/info/settings.json].')
    parser.add_option('-d', '--debug', dest='debug',
                    help='Enable debug messages.', action="store_true")
    (values, args) = parser.parse_args(args)
    commands = [cmd[3:] for cmd in itertools.ifilter(lambda c: c[:3] == 'do_', dir(Helical))]
    address = 'localhost'
    port = DEFAULT_PORT
    command = None

    if not values.username:
        # Default to using ~/.netrc for authentication
        import netrc
        authenticators = netrc.netrc(
            os.path.join(get_home(), '.netrc')).authenticators(address)
        if authenticators:
            values.username, account, values.password = authenticators

    logging.basicConfig()
    # Want just our logger, not transmissionrpc's to log INFO
    logger.setLevel(logging.INFO)
    if values.debug:
        logging.getLogger('transmissionrpc').setLevel(logging.DEBUG)
    for arg in args:
        if arg in commands:
            command = arg
            break
        try:
            (address, port) = utils.inet_address(arg, DEFAULT_PORT)
        except utils.INetAddressError:
            address = arg
            port = None
    helical = Helical(values.settings)
    if not command or command.lower() != 'help':
        try:
            helical.connect(address, port, values.username, values.password)
        except transmissionrpc.TransmissionError, error:
            print(error)
            parser.print_help()
            return

    if command:
        line = u' '.join([command] + args[args.index(command)+1:])
        helical.onecmd(line)
    else:
        try:
            helical.cmdloop()
        except KeyboardInterrupt:
            helical.do_quit('')

if __name__ == '__main__':
    sys.exit(main())
