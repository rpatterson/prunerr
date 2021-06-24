#!/usr/bin/env python
"""
Remove Servarr download client items to preserve disk space according to rules.
"""

import os
import argparse

import os.path
import itertools
import socket
import shutil
import subprocess
import time
import logging
import pathlib
import urllib
import tempfile

import yaml

import servicelogging

import transmission_rpc
from transmission_rpc import utils
from transmission_rpc import error

logger = logging.getLogger("prunerr")


def yaml_arg_type(arg):
    return yaml.safe_load(argparse.FileType("r")(arg))


parser = argparse.ArgumentParser(
    description=__doc__.strip(), formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "--config",
    "-c",
    type=yaml_arg_type,
    default=str(pathlib.Path.home() / ".config" / "prunerr.yml"),
    help="""\
The path to the Prunerr configuration file. Example:
https://gitlab.com/rpatterson/prunerr/-/blob/master/home/.config/prunerr.yml\
""",
)
subparsers = parser.add_subparsers(help="sub-command help")


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


class Prunerr(object):

    def __init__(self, config):
        self.config = config
        self.popen = self.copying = None
        self.corrupt = {}

    def connect(self):
        url_parsed = urllib.parse.urlsplit(self.config["downloaders"]["url"])
        self.tc = transmission_rpc.client.Client(
            protocol=url_parsed.scheme,
            host=url_parsed.hostname,
            port=url_parsed.port,
            path=url_parsed.path,
            username=url_parsed.username,
            password=url_parsed.password,
        )
        self.update()

    def exec_(self):
        """
        Prune download client items once.
        """
        session = self.tc.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")

        if self.config["downloaders"].get("readd-missing-data"):
            self.readd_missing_data()

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

        if self.config["downloaders"].get("copy"):
            self._exec_copy(session)

        # Do any other cleanup
        self.update_priorities()
        self.free_space()

    def _exec_copy(self, session):
        """
        Launch copy of most optimal, fully downloaded torrent in the downloads dir.
        """
        destination = self.config["downloaders"]["copy"]["destination"]
        command = self.config["downloaders"]["copy"]["command"]
        seeding_dir = self.config["downloaders"].get(
            "seeding-dir",
            os.path.join(os.path.dirname(session.download_dir), "seeding"),
        )
        retry_codes = self.config["downloaders"]["copy"].get(
            "daemon-retry-codes", [10, 12, 20, 30, 35, 255],
        )
        to_copy = sorted(
            (
                torrent
                for torrent in self.torrents
                if torrent.status == "seeding"
                and not os.path.relpath(
                    torrent.downloadDir, self.config["downloaders"]["download-dir"],
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

    def update(self):
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
        if self.config["downloaders"].get("copy"):
            raise ValueError("Cannot copy items without appropriate configuration")
        session = self.tc.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")
        relative = os.path.relpath(torrent.downloadDir, session.download_dir)

        # Use a temporary file to keep feeding the file list to the
        # subprocess from blocking us
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

    def daemon(self):
        """
        Prune download client items continuously.
        """
        while True:
            while True:
                try:
                    # Don't loop until we successfully update everything
                    self.update()
                except (socket.error, error.TransmissionError):
                    logger.exception("Connection error while updating from server")
                    pass
                else:
                    break

            try:
                self.exec_()
            except socket.error:
                logger.exception("Connection error while running daemon")
                pass

            # Wait for the next interval
            start = time.time()
            poll = self.config["daemon"].get("poll", 60)
            # Loop early if the copy process finishes early
            while (
                self.popen is None or self.popen.poll() is None
            ) and time.time() - start < poll:
                time.sleep(1)

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

    def lookup_tracker_priority(self, torrent):
        """
        Determine which tracker hostname and priority apply to the torrent if any.
        """
        # TODO: abstract tracker to indexer with priorities from servarr API
        for tracker in torrent.trackers:
            for action in ("announce", "scrape"):
                parsed = urllib.parse.urlsplit(tracker[action])
                for hostname, priority in self.config["indexers"]["priorities"]:
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

    def update_priorities(self):
        """Set torrent priority by private/public trackers"""

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
                priority = self.config["indexers"].get("default-priority")
                if priority is None or torrent.bandwidthPriority == priority:
                    continue
                logger.info("Marking %s as default priority %s", torrent, priority)
                self.tc.change([torrent.id], bandwidthPriority=priority)
                torrent.update()
                changed.append(torrent)

    def free_space(self):
        """Delete some torrents if running out of disk space."""
        session = self.tc.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")
        trackers_ordered = [
            hostname
            for hostname, priority in reversed(
                self.config["indexers"]["tracker-priorities"],
            )
        ]

        # Delete any torrents that have already been copied and are no longer
        # recognized by their tracker: e.g. when a private tracker removes a
        # duplicate/invalid/unauthorized torrent
        for torrent in self.torrents:
            if (
                (
                    torrent.status == "downloading"
                    or torrent.downloadDir.startswith(
                        self.config["downloaders"].get(
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
        if (
            statvfs.f_frsize * statvfs.f_bavail
            >= self.config["downloaders"]["free-space"]
        ):
            return self._resume_down(session)

        # First find orphaned files, remove smallest files first
        # Update torrent.downloadDir first to identify orphans
        self.update()
        session = self.tc.get_session()
        download_dirs = (
            # Transmission's `incomplete` directory for incomplete, leeching torrents
            session.incomplete_dir,
            # Transmission's `downloads` directory for complete, seeding torrents
            session.download_dir,
            # A Prunerr `seeding` directory that we may move torrents to after
            # successfully copying them.
            self.config["downloaders"].get(
                "seeding-dir",
                os.path.join(os.path.dirname(session.download_dir), "seeding"),
            ),
        )

        # Assemble all directories whose descendants are torrents
        torrent_dirs = set()
        torrent_paths = set()
        for torrent in self.torrents:
            # Transmission's `incomplete` directory for incomplete, leeching torrents
            torrent_paths.add(os.path.join(session.incomplete_dir, torrent.name))
            # Transmission's `downloads` directory for complete, seeding torrents
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
                    if pathlib.Path(download_dir).is_dir()
                )
            ),
            key=lambda orphan: int(orphan[0]),
        )
        du.stdin.close()
        # Remove orphans, smallest first until enough space is freed
        # or there are no more orphans
        statvfs = os.statvfs(session.download_dir)
        while (
            statvfs.f_frsize * statvfs.f_bavail
            < self.config["downloaders"]["free-space"]
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
        if (
            statvfs.f_frsize * statvfs.f_bavail
            >= self.config["downloaders"]["free-space"]
        ):
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
                    self.config["downloaders"].get(
                        "seeding-dir",
                        os.path.join(os.path.dirname(session.download_dir), "seeding"),
                    )
                )
            ),
            # remove lowest priority and highest ratio first
            key=lambda item: self.get_torrent_priority_key(trackers_ordered, item[1]),
        )
        removed = []
        while (
            statvfs.f_frsize * statvfs.f_bavail
            < self.config["downloaders"]["free-space"]
        ):
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
            self.update()

    def _list_orphans(self, torrent_dirs, torrent_paths, du, path):
        """Recursively list paths that aren't a part of any torrent."""
        for entry in os.listdir(path):
            entry_path = os.path.join(path, entry)
            if entry_path not in torrent_paths and entry_path not in torrent_dirs:
                du.stdin.write(entry_path.encode("utf-8") + b"\0")
                du_line = du.stdout.readline()
                size, du_path = du_line[:-1].split(b"\t", 1)[:2]
                size = int(size)
                logger.error(
                    "Found orphan path unrecognized by download client: %s",
                    utils.format_size(int(size)),
                )
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
        speed_limit_down = self.config["downloaders"].get("daemon-speed-limit-down")
        if session.speed_limit_down_enabled and (
            not speed_limit_down or speed_limit_down != session.speed_limit_down
        ):
            if speed_limit_down:
                kwargs = dict(speed_limit_down=speed_limit_down)
            else:
                kwargs = dict(speed_limit_down_enabled=False)
            logger.info("Resuming downloading: %s", kwargs)
            self.tc.set_session(**kwargs)

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

    def readd_missing_data(self):
        """
        Workaround an issue with Transmission when starting torrents with no free space.

        While there's no free space on the device, torrents for which no significant
        data has been downloaded will have no local files created (beyond the
        `./resume/*.resume` file).  When Transmission is later restarted after some
        space has been freed on the device, it will consider the "missing" local files
        an error but no actions can be taken to force it to create the local files anew
        and resume.  Not verifying, not moving, not re-adding the torrent without first
        removing it and certainly not simply resuming:

        https://github.com/transmission/transmission/issues/83

        Work around these issues by keeping the `./torrents/*.torrent` file open so that
        Transmission can't remove it, removing the torrent from Transmission, and
        re-adding the opened torrent file to Transmission.  There's no way I know of to
        distinguish between this very common case and other issues that may result in
        the same `No data found!` error message so there's a chance this can cause
        issues.
        """
        torrents_were_readded = False
        for torrent in self.torrents:
            if not (
                    torrent.status == "stopped"
                    and torrent.error == 3
                    and torrent.errorString.lower().startswith("no data found")
            ):
                continue
            torrent = self.tc.get_torrent(torrent.id)
            logger.error("No data found for %s, re-adding", torrent)
            with open(torrent.torrentFile, mode="r+b") as torrent_opened:
                self.tc.remove_torrent(ids=[torrent.id])
                self.tc.add_torrent(
                    torrent=torrent_opened,
                    # These are the only fields from the `add_torrent()` call signature
                    # in the docs I could see corresponding fields for in the
                    # representation of a torrent.
                    bandwidthPriority=torrent.bandwidthPriority,
                    download_dir=torrent.download_dir,
                    peer_limit=torrent.peer_limit,
                )
            torrents_were_readded = True
        if torrents_were_readded:
            self.update()

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

    def recopy_seeding(self):
        """
        Re-copy all seeding torrents managed by the `daemon` command.

        Move all seeding torrents back to the downloads directory so that the
        `daemon` command will re-copy them.  Useful to recover from any remote
        data loss as much as is still possible with what torrents are still
        local.
        """
        self.update()
        session = self.tc.get_session()

        for torrent in self.torrents:
            if torrent.status != "seeding" or torrent.downloadDir.startswith(
                session.download_dir
            ):
                continue

            self.move_torrent(
                torrent,
                old_path=self.config["downloaders"].get(
                    "seeding-dir",
                    os.path.join(os.path.dirname(session.download_dir), "seeding"),
                ),
                new_path=session.download_dir,
            )


Prunerr.__doc__ = __doc__


def get_home():
    try:
        # Don't rely on os.environ['HOME'] such as under cron jobs
        import pwd

        return pwd.getpwuid(os.getuid()).pw_dir
    except ImportError:
        # Windows
        return os.path.expanduser("~")


def exec_(prunerr):
    prunerr.connect()
    result = prunerr.exec_()
    if prunerr.popen is not None:
        logger.info("Letting running copy finish: %s", prunerr.copying)
        prunerr.popen.wait()
    return result


exec_.__doc__ = Prunerr.exec_.__doc__
parser_exec = subparsers.add_parser("exec", help=exec_.__doc__.strip())
parser_exec.set_defaults(func=exec_)


def daemon(prunerr):
    prunerr.connect()
    return prunerr.daemon()


daemon.__doc__ = Prunerr.daemon.__doc__
parser_daemon = subparsers.add_parser("daemon", help=daemon.__doc__.strip())
parser_daemon.set_defaults(func=daemon)


def main(args=None):
    servicelogging.basicConfig()
    # Want just our logger, not transmission-rpc's to log INFO
    logger.setLevel(logging.INFO)

    parsed_args = parser.parse_args(args)
    prunerr_kwargs = dict(vars(parsed_args))
    del prunerr_kwargs["func"]
    prunerr = Prunerr(**prunerr_kwargs)
    return parsed_args.func(prunerr)


main.__doc__ = __doc__


if __name__ == "__main__":
    main()
