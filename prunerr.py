#!/usr/bin/env python

import sys
import os
import os.path
import itertools
import socket
import base64
import shlex
import collections
import json
import shutil
import subprocess
import time
import logging
from optparse import OptionParser

try:
    import readline  # noqa
except:
    pass
import cmd

import six
from six import moves
from six.moves import urllib

import servicelogging

import transmission_rpc
from transmission_rpc import utils
from transmission_rpc import error

__author__ = "Erik Svensson <erik.public@gmail.com>"
__version__ = "0.2"
__copyright__ = "Copyright (c) 2008 Erik Svensson"
__license__ = "MIT"

logger = logging.getLogger("prunerr")


class TransmissionTimeout(Exception):
    """A transmission operation took too long."""


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
        "Error removing %r (%s)",
        path,
        ".".join((function.__module__, function.__name__)),
        exc_info=excinfo,
    )


class Prunerr(cmd.Cmd):

    settings = {}

    def __init__(self, settings_file=None):
        cmd.Cmd.__init__(self)
        self.intro = "Prunerr %s" % (__version__)
        self.doc_leader = """
Prunerr is a command line interface that communicates with Transmission
bittorent client through json-rpc. To run prunerr in interactive mode
start without a command.
"""
        self.settings_file = settings_file or os.path.join(
            get_home(), "info", "settings.json"
        )

    def connect(self, address=None, port=None, username=None, password=None):
        self.tc = transmission_rpc.Client(address, port, username, password)
        urlo = urllib.parse.urlparse(self.tc.url)
        if urlo.port:
            self.prompt = "Prunerr %s:%d> " % (urlo.hostname, urlo.port)
        else:
            self.prompt = "Prunerr %s> " % (urlo.hostname)
        self.do_update("")

    def arg_tokenize(self, argstr):
        return [token for token in shlex.split(argstr)] or [""]

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
        item = args[-1] if len(args) > 1 else ""
        return self._complete_torrent(item, endidx - begidx)

    def help_quit(self):
        print("quit|exit\n")
        print("Exit to shell.\n")

    def do_quit(self, line):
        sys.exit("")

    # Alias
    do_exit = do_quit
    help_exit = help_quit
    do_EOF = do_quit

    def help_update(self):
        print("update\n")
        print("Update the torrents list and settings.\n")

    def do_update(self, line):
        self.torrents = self.tc.get_torrents(
            arguments=(
                "id",
                "name",
                "status",
                "error",
                "errorString",
                "trackers",
                "bandwidthPriority",
                "downloadDir",
                "totalSize",
                "uploadRatio",
                "priorities",
                "wanted",
                "files",
            )
        )
        if isinstance(self.settings_file, six.string_types):
            self.settings = json.load(
                open(self.settings_file), object_pairs_hook=collections.OrderedDict
            )

    def help_add(self):
        print("add <torrent file or url> [<target dir> paused=(yes|no) peer-limit=#]\n")
        print("Add a torrent to the transfer list.\n")

    def do_add(self, line):
        args = self.arg_tokenize(line)

        if len(args) == 0:
            print("Specify a torrent file or url")
            return

        torrent_url = args[0]
        args = args[1:]
        torrent_file = None
        if os.path.exists(torrent_url):
            torrent_file = open(torrent_url, "r")
        else:
            try:
                torrent_file = urllib.request.urlopen(torrent_url)
            except:
                torrent_file = None
        if not torrent_file:
            print('Couldn\'t find torrent "%s"' % torrent_url)
            return

        add_args = {}
        if len(args) > 0:
            for arg in args:
                try:
                    (k, v) = arg.split("=")
                    add_args[str(k)] = str(v)
                except:
                    if "download_dir" not in add_args:
                        try:
                            os.mkdir(arg)
                            add_args["target"] = arg
                            continue
                        except:
                            pass
                    print('Unknown argument: "%s"' % arg)

        torrent_data = base64.b64encode(torrent_file.read())
        try:
            self.tc.add(torrent_data, **add_args)
        except transmissionrpc.TransmissionError as e:
            print('Failed to add torrent "%s"' % e)

    def do_magnet(self, line):
        args = self.arg_tokenize(line)

        if len(args) == 0:
            print("Specify a torrent file or url")
            return

        torrent_url = args[0]

        try:
            self.tc.add_uri(torrent_url)
        except transmissionrpc.TransmissionError as e:
            print('Failed to add torrent "%s"' % e)

    def complete_remove(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)

    def help_remove(self):
        print("remove <torrent id> [,<torrent id>, ...]\n")
        print("Remove one or more torrents from the transfer list.\n")

    def do_remove(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError("No torrent id")
        self.tc.remove(args)

    def complete_start(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)

    def help_start(self):
        print("start <torrent id> [,<torrent id>, ...]\n")
        print("Start one or more queued torrent transfers.\n")

    def do_start(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError("No torrent id")
        self.tc.start(args)

    def complete_stop(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)

    def help_stop(self):
        print("stop <torrent id> [,<torrent id>, ...]\n")
        print("Stop one or more active torrent transfers.\n")

    def do_stop(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError("No torrent id")
        self.tc.stop(args)

    def complete_verify(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)

    def help_verify(self):
        print("verify <torrent id> [,<torrent id>, ...]\n")
        print("Verify one or more torrent transfers.\n")

    def do_verify(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError("No torrent id")
        self.tc.verify(args)

    def complete_info(self, text, line, begidx, endidx):
        return self._complete_torrent_command(text, line, begidx, endidx)

    def help_info(self):
        print("info [<torrent id>, ...]\n")
        print(
            "Get details for a torrent. If no torrent id is provided, all torrents are displayed.\n"
        )

    def do_info(self, line):
        args = self.arg_tokenize(line)
        if len(args) == 0:
            raise ValueError("No torrent id")
        result = self.tc.get_torrents(args)
        for torrent in result:
            print(self._torrent_detail(torrent))

    def help_list(self):
        print("list\n")
        print("List all torrent transfers.\n")

    def do_list(self, line):
        args = self.arg_tokenize(line)
        if args:
            raise ValueError("'list' takes no arguments")
        result = self.tc.list()
        self._list_torrents(result)

    def help_files(self):
        print("files [<torrent id>, ...]\n")
        print("Get the file list for one or more torrents\n")

    def do_files(self, line):
        args = self.arg_tokenize(line)
        result = self.tc.get_files(args)
        for tid, files in result.items():
            print("torrent id: %d" % tid)
            for fid, file in files.items():
                print("  %d: %s" % (fid, file["name"]))

    def do_set(self, line):
        args = self.arg_tokenize(line)
        set_args = {}
        ids = []
        add_ids = True

        if len(args) > 0:
            for arg in args:
                try:
                    (k, v) = arg.split("=")
                    set_args[str(k)] = str(v)
                    add_ids = False
                except:
                    if add_ids:
                        ids.append(arg)
                    else:
                        print('Unknown argument: "%s"' % arg)
        if len(ids) > 0:
            self.tc.change(ids, **set_args)

    def complete_session(self, text, line, begidx, endidx):
        return self.word_complete(text, ["get", "set", "stats"])

    def help_session(self):
        print("session (get|stats)\n")
        print("Get session parameters or session statistics.\n")

    def do_session(self, line):
        args = self.arg_tokenize(line)
        if len(args[0]) == 0 or args[0] == "get":
            self.tc.get_session()
            print(self.tc.session)
        elif args[0] == "stats":
            print(self.tc.session_stats())

    def help_copy(self):
        print("copy <torrent id> destination [-- command...]\n")
        print(
            "Copy the torrent to the destination by piping the relative\n"
            "torrent file paths to the shell command on stdin.\n"
            "Leaves the command running in the background.\n"
            "The command defaults to: rsync -tSmP --files-from=-\n"
            "Example: copy 1 192.168.1.1:/path/to/library/ "
            "rsync -tSmPvv --files-from=-\n"
        )

    def do_copy(self, line):
        """Copy a torrent using the given command."""
        args = self.arg_tokenize(line)
        if len(args) < 2:
            raise ValueError(
                "'copy' command requires a torrent id and a destination path"
            )
        elif len(args) < 3:
            args.extend(["rsync", "-tSmP", "--files-from=-"])
        torrent_id, destination = args[:2]
        command = args[2:]
        torrent = self.tc.get_torrent(torrent_id)
        self.copy(torrent, destination, command)

    def list_torrent_files(self, torrent, download_dir=None):
        """
        Iterate over all torrent selected file paths that exist.
        """
        if download_dir is None:
            download_dir = torrent.downloadDir

        torrent_files = torrent.files()
        assert torrent_files, "Must be able to find torrent files to copy"

        return (
            file_["name"]
            for file_ in torrent_files.values()
            if file_.get("selected")
            and os.path.exists(os.path.join(download_dir, file_["name"]))
        )

    def copy(self, torrent, destination, command):
        """Launch the copy subprocess and return the popen object."""
        session = self.tc.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")
        relative = os.path.relpath(torrent.downloadDir, session.download_dir)

        # Use a temporary file to keep feeding the file list to the
        # subprocess from blocking us
        import tempfile

        files = tempfile.TemporaryFile(mode="w")
        files.writelines(
            os.path.join(relative, subpath) + "\n"
            for subpath in self.list_torrent_files(torrent)
        )
        files.seek(0)

        popen_cmd = command + [session.download_dir, destination]
        logger.info("Launching copy command: %s", " ".join(popen_cmd))
        popen = subprocess.Popen(popen_cmd, stdin=files, text=True)

        return popen

    def help_daemon(self):
        print("daemon destination [command...]\n")
        print(
            """\
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

'daemon-poll' defaults to 1 minute, and 'seeding-dir' defaults to a 'seeding'
directory next to the 'download-dir'.
"""
        )

    def do_daemon(self, line):
        """Loop running several regular commands every interval."""
        args = self.arg_tokenize(line)
        destination = args[0]
        command = args[1:]

        self.popen = self.copying = None
        self.corrupt = {}
        while True:
            while True:
                try:
                    # Don't loop until we successfully update everything
                    session = self.tc.get_session()
                    session.download_dir = session.download_dir.strip(" `'\"")
                    self.do_update("")
                except (socket.error, error.TransmissionError):
                    logger.exception("Connection error while updating from server")
                    pass
                else:
                    break

            try:
                self._daemon_inner(session, destination, command)
            except socket.error:
                logger.exception("Connection error while running daemon")
                pass

            # Wait for the next interval
            start = time.time()
            poll = self.settings.get("daemon-poll", 60)
            # Loop early if the copy process finishes early
            while (
                self.popen is None or self.popen.poll() is None
            ) and time.time() - start < poll:
                time.sleep(1)

    def _daemon_inner(self, session, destination, command):
        """'daemon' command innner loop."""
        session = self.tc.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")
        seeding_dir = self.settings.get(
            "seeding-dir",
            os.path.join(os.path.dirname(session.download_dir), "seeding"),
        )
        retry_codes = self.settings.get("daemon-retry-codes", [10, 12, 20, 30, 35, 255])

        # Keep track of torrents being verified to resume them
        # when verification is complete
        self.corrupt.update(self.verify_corrupted())
        for torrent_id, torrent in list(self.corrupt.items()):
            try:
                torrent.update()
            except KeyError as exc:
                logger.error(
                    "Error updating corrupt %s, " "may have been removed: %s",
                    torrent,
                    exc,
                )
                del self.corrupt[torrent_id]
            else:
                if not torrent.status.startswith("check"):
                    logger.info("Resuming verified torrent: %s", torrent)
                    torrent.start()
                    torrent.update()
                    del self.corrupt[torrent_id]
        if self.corrupt:
            logger.info(
                "Waiting for torrents to verify:\n%s",
                "\n".join(map(str, self.corrupt.values())),
            )

        # Start copying the most optimal torrent that is fully downloaded and
        # in the downloads directory.
        to_copy = sorted(
            (
                torrent
                for torrent in self.torrents
                if torrent.status == "seeding"
                and not os.path.relpath(
                    torrent.downloadDir, self.settings["download-dir"],
                ).startswith(os.pardir + os.sep)
            ),
            # 1. Copy lower priority torrents first so they may be deleted
            # first.
            # 2. Copy smaller torrents first to avoid huge torrents preventing
            # timely download of others.
            key=lambda item: (item.bandwidthPriority, item.totalSize),
        )
        if self.popen is not None:
            if self.popen.poll() is None:
                if not to_copy or self.copying.id == to_copy[0].id:
                    logger.info("Letting running copy finish: %s", self.copying)
                    to_copy = None
                else:
                    logger.info("Terminating running copy: %s", self.copying)
                    self.popen.terminate()
            elif self.popen.returncode == 0:
                # Copy process succeeded
                # Move a torrent preserving subpath and block until done.
                self.move_torrent(
                    self.copying, old_path=session.download_dir, new_path=seeding_dir
                )
                if to_copy and self.copying.id == to_copy[0].id:
                    to_copy.pop(0)
                self.copying = None
                self.popen = None
            elif self.popen.returncode not in retry_codes:
                logger.error(
                    "Copy failed with return code %s, pausing %s",
                    self.popen.returncode,
                    self.copying,
                )
                try:
                    self.copying.stop()
                    self.copying.update()
                except KeyError:
                    logger.exception("Error pausing %s", self.copying)
                self.popen = None

        if to_copy:
            logger.info(
                "Enabling upload speed limit during copy: %s", session.speed_limit_up
            )
            self.tc.set_session(speed_limit_up_enabled=True)
            logger.info("Copying torrent: %s", to_copy[0])
            self.popen = self.copy(to_copy[0], destination, command)
            self.copying = to_copy[0]
        elif self.popen is None:
            logger.info("Disabling upload speed limit while not copying")
            self.tc.set_session(speed_limit_up_enabled=False)

        # Do any other cleanup
        self.do_update_priorities("")
        self.do_free_space("")

    def move_timeout(self, torrent, download_dir, move_timeout=5 * 60):
        """
        Block until a torrents files are no longer in the old location.

        Useful for both moving and deleting.
        """
        # Wait until the files are finished moving
        start = time.time()
        while list(self.list_torrent_files(torrent, download_dir)):
            if time.time() - start > move_timeout:
                raise TransmissionTimeout(
                    "Timed out waiting for {torrent} to move "
                    "from {download_dir!r}".format(**locals())
                )
            time.sleep(1)

    def help_update_priorities(self):
        print("update_priorities\n")
        print(
            "Set the bandwidth priority for each torrent using the settings JSON "
            '"tracker-priorities" array/list where each item is itself an array '
            "consisting of the tracker hostname and an integer priority value."
        )

    def lookup_tracker_priority(self, torrent):
        """
        Determine which tracker hostname and priority apply to the torrent if any.
        """
        for tracker in torrent.trackers:
            for action in ("announce", "scrape"):
                parsed = urllib.parse.urlsplit(tracker[action])
                for hostname, priority in self.settings["tracker-priorities"]:
                    if parsed.hostname and parsed.hostname.endswith(hostname):
                        return hostname, priority
        return None, None

    def get_torrent_priority_key(self, trackers_ordered, torrent):
        """
        Combine tracker ranking, torrent priority, and ratio into a sort key.
        """
        hostname, priority = self.lookup_tracker_priority(torrent)
        traker_rank = -1
        if hostname in trackers_ordered:
            traker_rank = trackers_ordered.index(hostname)
        return (
            traker_rank,
            torrent.bandwidthPriority,
            -torrent.ratio,
        )

    def do_update_priorities(self, line):
        """Set torrent priority by private/public trackers"""
        if line:
            raise ValueError("'update_priorities' command doesn't accept args")

        changed = []
        for torrent in self.torrents:
            hostname, priority = self.lookup_tracker_priority(torrent)
            if priority is not None:
                if torrent.bandwidthPriority != priority:
                    logger.info("Marking %s as priority %s", torrent, priority)
                    self.tc.change([torrent.id], bandwidthPriority=priority)
                    torrent.update()
                    changed.append(torrent)
            else:
                priority = self.settings.get("default-priority")
                if priority is None or torrent.bandwidthPriority == priority:
                    continue
                logger.info("Marking %s as default priority %s", torrent, priority)
                self.tc.change([torrent.id], bandwidthPriority=priority)
                torrent.update()
                changed.append(torrent)

    def help_free_space(self):
        print("free_space\n")
        print(
            "Delete torrents if there's not enough free space\n"
            'according to the "free-space" JSON setting.'
        )

    def do_free_space(self, line):
        """Delete some torrents if running out of disk space."""
        if line:
            raise ValueError("'free_space' command doesn't accept args")

        session = self.tc.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")
        trackers_ordered = [
            hostname
            for hostname, priority in reversed(self.settings["tracker-priorities"])
        ]

        # Delete any torrents that have already been copied and are no longer
        # recognized by their tracker: e.g. when a private tracker removes a
        # duplicate/invalid/unauthorized torrent
        for torrent in self.torrents:
            if (
                (
                    torrent.status == "downloading"
                    or torrent.downloadDir.startswith(
                        self.settings.get(
                            "seeding-dir",
                            os.path.join(
                                os.path.dirname(session.download_dir), "seeding"
                            ),
                        )
                    )
                )
                and torrent.error == 2
                and "unregistered torrent" in torrent.errorString.lower()
            ):
                logger.error(
                    "Deleting seeding %s " "no longer registered with tracker", torrent
                )
                self.tc.remove_torrent(torrent.id, delete_data=True)

        statvfs = os.statvfs(session.download_dir)
        if statvfs.f_frsize * statvfs.f_bavail >= self.settings["free-space"]:
            return self._resume_down(session)

        # First find orphaned files, remove smallest files first
        # Update torrent.downloadDir first to identify orphans
        self.do_update("")
        download_dirs = (
            self.settings.get(
                "seeding-dir",
                os.path.join(os.path.dirname(session.download_dir), "seeding"),
            ),
            session.download_dir,
        )
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
        # TODO Windows compatibility
        du_cmd = ["du", "-s", "--block-size=1", "--files0-from=-"]
        du = subprocess.Popen(
            du_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0
        )
        orphans = sorted(
            itertools.chain(
                *(
                    self._list_orphans(torrent_dirs, torrent_paths, du, download_dir)
                    for download_dir in download_dirs
                )
            ),
            key=lambda orphan: int(orphan[0]),
        )
        du.stdin.close()
        # Remove orphans, smallest first until enough space is freed
        # or there are no more orphans
        statvfs = os.statvfs(session.download_dir)
        while (
            statvfs.f_frsize * statvfs.f_bavail < self.settings["free-space"]
            and orphans
        ):
            size, orphan = orphans.pop(0)
            logger.warn(
                "Deleting orphaned path %r to free space: " "%0.2f %s + %0.2f %s",
                orphan,
                *itertools.chain(
                    utils.format_size(statvfs.f_frsize * statvfs.f_bavail),
                    utils.format_size(size),
                ),
            )
            if os.path.isdir(orphan):
                shutil.rmtree(orphan, onerror=log_rmtree_error)
            else:
                os.remove(orphan)
            session.update()
            statvfs = os.statvfs(session.download_dir)
        du.wait()
        if du.returncode:
            raise subprocess.CalledProcessError(du.returncode, du_cmd)
        statvfs = os.statvfs(session.download_dir)
        if statvfs.f_frsize * statvfs.f_bavail >= self.settings["free-space"]:
            # No need to process seeding torrents
            # if removing orphans already freed enough space
            return self._resume_down(session)

        # Next remove seeding and copied torrents
        by_ratio = sorted(
            (
                (index, torrent)
                for index, torrent in enumerate(self.torrents)
                # only those previously synced and moved
                if torrent.status == "seeding"
                and torrent.downloadDir.startswith(
                    self.settings.get(
                        "seeding-dir",
                        os.path.join(os.path.dirname(session.download_dir), "seeding"),
                    )
                )
            ),
            # remove lowest priority and highest ratio first
            key=lambda item: self.get_torrent_priority_key(trackers_ordered, item[1]),
        )
        removed = []
        while statvfs.f_frsize * statvfs.f_bavail < self.settings["free-space"]:
            if not by_ratio:
                logger.error(
                    "Running out of space but no torrents can be removed: %s",
                    utils.format_size(statvfs.f_frsize * statvfs.f_bavail),
                )
                kwargs = dict(speed_limit_down=0, speed_limit_down_enabled=True)
                logger.info("Stopping downloading: %s", kwargs)
                self.tc.set_session(**kwargs)
                break
            index, remove = by_ratio.pop(0)
            hostname, priority = self.lookup_tracker_priority(remove)
            logger.info(
                "Deleting seeding %s to free space, "
                "%0.2f %s + %0.2f %s: tracker=%s, priority=%s, ratio=%0.2f",
                remove,
                *(
                    utils.format_size(statvfs.f_frsize * statvfs.f_bavail)
                    + utils.format_size(remove.totalSize)
                    + (hostname, remove.bandwidthPriority, remove.ratio)
                ),
            )
            download_dir = remove.downloadDir
            self.tc.remove_torrent(remove.id, delete_data=True)
            self.move_timeout(remove, download_dir)
            removed.append(remove)
            session.update()
            statvfs = os.statvfs(session.download_dir)
        else:
            self._resume_down(session)

        if removed:
            # Update the list of torrents if we removed any
            self.do_update("")

    def _list_orphans(self, torrent_dirs, torrent_paths, du, path):
        """Recursively list paths that aren't a part of any torrent."""
        for entry in os.listdir(path):
            entry_path = os.path.join(path, entry)
            if entry_path not in torrent_paths and entry_path not in torrent_dirs:
                du.stdin.write(entry_path.encode("utf-8") + b"\0")
                du_line = du.stdout.readline()
                size, du_path = du_line[:-1].split(b"\t", 1)[:2]
                yield (int(size), entry_path)
            elif entry_path in torrent_dirs:
                for orphan in self._list_orphans(
                    torrent_dirs, torrent_paths, du, entry_path
                ):
                    yield orphan

    def _resume_down(self, session):
        """
        Resume downloading if it's been stopped.
        """
        speed_limit_down = self.settings.get("daemon-speed-limit-down")
        if session.speed_limit_down_enabled and (
            not speed_limit_down or speed_limit_down != session.speed_limit_down
        ):
            if speed_limit_down:
                kwargs = dict(speed_limit_down=speed_limit_down)
            else:
                kwargs = dict(speed_limit_down_enabled=False)
            logger.info("Resuming downloading: %s", kwargs)
            self.tc.set_session(**kwargs)

    def help_verify_corrupted(self):
        print("verify_corrupted\n")
        print(
            "Verify any incomplete torrents " "that are paused because of corruption."
        )

    def do_verify_corrupted(self, line):
        """
        Verify any incomplete torrents that are paused because of corruption.
        """
        if line:
            raise ValueError("'verify_corrupted' command doesn't accept args")
        self.do_update("")
        self.verify_corrupted()

    def verify_corrupted(self):
        """
        Verify any incomplete torrents that are paused because of corruption.
        """
        corrupt = dict(
            (torrent.id, torrent)
            for torrent in self.torrents
            if torrent.status == "stopped"
            and torrent.error == 3
            and (
                "verif" in torrent.errorString.lower()
                or "corrput" in torrent.errorString.lower()
            )
        )
        if corrupt:
            logger.info(
                "Verifying corrupt torrents:\n%s", "\n".join(map(str, corrupt.values()))
            )
            self.tc.verify_torrent(list(corrupt.keys()))
            for torrent in corrupt.values():
                torrent.update()

        return corrupt

    def move_torrent(self, torrent, old_path, new_path):
        """
        Move the given torrent relative to its old path.
        """
        download_dir = torrent.downloadDir
        relative = os.path.relpath(download_dir, os.path.dirname(old_path))
        split = splitpath(relative)[1:]
        subpath = split and os.path.join(*split) or ""
        torrent_location = os.path.join(new_path, subpath)
        logger.info("Moving %s to %s", torrent, torrent_location)
        torrent.move_data(torrent_location)
        try:
            self.move_timeout(torrent, download_dir)
        except TransmissionTimeout as exc:
            logger.error("Moving torrent timed out, pausing: %s", exc)
            torrent.stop()
        finally:
            torrent.update()

        return torrent_location

    def do_recopy_seeding(self, line):
        """
        Re-copy all seeding torrents managed by the `daemon` command.

        Move all seeding torrents back to the downloads directory so that the
        `daemon` command will re-copy them.  Useful to recover from any remote
        data loss as much as is still possible with what torrents are still
        local.
        """
        if line:
            raise ValueError("'recopy_seeding' command doesn't accept args")
        self.do_update("")
        session = self.tc.get_session()

        for torrent in self.torrents:
            if torrent.status != "seeding" or torrent.downloadDir.startswith(
                session.download_dir
            ):
                continue

            self.move_torrent(
                torrent,
                old_path=self.settings.get(
                    "seeding-dir",
                    os.path.join(os.path.dirname(session.download_dir), "seeding"),
                ),
                new_path=session.download_dir,
            )

    def help_recopy_seeding(self):
        print("recopy_seeding\n")
        print(self.do_recopy_seeding.__doc__)

    def do_request(self, line):
        (method, sep, args) = line.partition(" ")
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
            for tid, torrent in torrents.items():
                print(self._torrent_brief(torrent))

    def _torrent_brief_header(self):
        return " Id   Done   ETA           Status       Download     Upload       Ratio  Name"

    def _torrent_brief(self, torrent):
        s = "% 3d: " % (torrent.id)
        try:
            s += "%5.1f%%" % torrent.progress
        except:
            pass
        try:
            s += " %- 13s" % torrent.format_eta()
        except:
            s += " -            "
        try:
            s += " %- 12s" % torrent.status
        except:
            s += " -status     "
            pass
        try:
            s += " %6.1f %- 5s" % utils.format_speed(torrent.rateDownload)
            s += " %6.1f %- 5s" % utils.format_speed(torrent.rateUpload)
        except:
            s += " -rate      "
            s += " -rate      "
            pass
        try:
            s += " %4.2f  " % torrent.ratio
        except:
            s += " -ratio"
            pass
        s += " " + torrent.name
        return s

    def _torrent_detail(self, torrent):
        s = ""
        s += "            id: " + str(torrent.id)
        s += "\n          name: " + torrent.name
        s += "\n          hash: " + torrent.hashString
        s += "\n"
        try:  # size
            f = ""
            f += "\n      progress: %.2f%%" % torrent.progress
            f += "\n         total: %.2f %s" % utils.format_size(torrent.totalSize)
            f += "\n      reqested: %.2f %s" % utils.format_size(torrent.sizeWhenDone)
            f += "\n     remaining: %.2f %s" % utils.format_size(torrent.leftUntilDone)
            f += "\n      verified: %.2f %s" % utils.format_size(torrent.haveValid)
            f += "\n  not verified: %.2f %s" % utils.format_size(torrent.haveUnchecked)
            s += f + "\n"
        except KeyError:
            pass
        try:  # activity
            f = ""
            f += "\n        status: " + str(torrent.status)
            f += "\n      download: %.2f %s" % utils.format_speed(torrent.rateDownload)
            f += "\n        upload: %.2f %s" % utils.format_speed(torrent.rateUpload)
            f += "\n     available: %.2f %s" % utils.format_size(
                torrent.desiredAvailable
            )
            f += "\ndownload peers: " + str(torrent.peersSendingToUs)
            f += "\n  upload peers: " + str(torrent.peersGettingFromUs)
            s += f + "\n"
        except KeyError:
            pass
        try:  # history
            f = ""
            f += "\n         ratio: %.2f" % torrent.ratio
            f += "\n    downloaded: %.2f %s" % utils.format_size(torrent.downloadedEver)
            f += "\n      uploaded: %.2f %s" % utils.format_size(torrent.uploadedEver)
            f += "\n        active: " + utils.format_timestamp(torrent.activityDate)
            f += "\n         added: " + utils.format_timestamp(torrent.addedDate)
            f += "\n       started: " + utils.format_timestamp(torrent.startDate)
            f += "\n          done: " + utils.format_timestamp(torrent.doneDate)
            s += f + "\n"
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
        return os.path.expanduser("~")


def main(args=None, connect_timeout=5 * 60):
    """Main entry point"""
    if sys.version_info[0] <= 2 and sys.version_info[1] <= 5:
        socket.setdefaulttimeout(30)
    if args is None:
        args = sys.argv[1:]
    parser = OptionParser(usage="Usage: %prog [options] [[address]:[port]] [command]")
    parser.add_option(
        "-u", "--username", dest="username", help="Athentication username."
    )
    parser.add_option(
        "-p", "--password", dest="password", help="Athentication password."
    )
    parser.add_option(
        "-s",
        "--settings",
        dest="settings",
        help="JSON file containing settings [default: ~/info/settings.json].",
    )
    parser.add_option(
        "-d",
        "--debug",
        dest="debug",
        help="Enable debug messages.",
        action="store_true",
    )
    (values, args) = parser.parse_args(args)
    commands = [cmd[3:] for cmd in moves.filter(lambda c: c[:3] == "do_", dir(Prunerr))]
    address = "localhost"
    port = DEFAULT_PORT
    command = None

    if not values.username:
        # Default to using ~/.netrc for authentication
        import netrc

        authenticators = netrc.netrc(os.path.join(get_home(), ".netrc")).authenticators(
            address
        )
        if authenticators:
            values.username, account, values.password = authenticators

    servicelogging.basicConfig()
    # Want just our logger, not transmission-rpc's to log INFO
    logger.setLevel(logging.INFO)
    if values.debug:
        logging.getLogger("prunerr").setLevel(logging.DEBUG)
    for arg in args:
        if arg in commands:
            command = arg
            break
        try:
            (address, port) = utils.inet_address(arg, DEFAULT_PORT)
        except utils.INetAddressError:
            address = arg
            port = None
    prunerr = Prunerr(values.settings)
    if not command or command.lower() != "help":
        start = time.time()
        while not getattr(prunerr, "tc", None):
            try:
                prunerr.connect(address, port, values.username, values.password)
            except socket.error:
                logger.exception("Connection error while connecting to server")
            except transmissionrpc.TransmissionError as error:
                print(error)
                parser.print_help()
                return 1
            if time.time() - start > connect_timeout:
                return "Timed out trying to connect to the server"
            time.sleep(1)

    if command:
        line = " ".join([command] + args[args.index(command) + 1 :])
        prunerr.onecmd(line)
    else:
        try:
            prunerr.cmdloop()
        except KeyboardInterrupt:
            prunerr.do_quit("")


if __name__ == "__main__":
    sys.exit(main())
