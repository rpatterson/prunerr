#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

import time, datetime
import re, itertools
import socket, httplib
import simplejson
from constants import *
from utils import format_size, format_timedelta, rpc_bool

class TransmissionError(Exception):
    pass

class Torrent(object):
    """
    Torrent is a class holding the data raceived from Transmission regarding a bittorrent transfer.
    All fetched torrent fields are accessable through this class using attributes.
    This class has a few convenience properties using the torrent data.
    """
    
    def __init__(self, fields):
        if 'id' not in fields:
            raise ValueError('Torrent requires an id')
        self.fields = fields
    
    def update(self, other):
        """Update the torrent data from a Transmission arguments dictinary"""

        fields = None
        if isinstance(other, dict):
            fields = other
        elif isinstance(other, Torrent):
            fields = other.fields
        else:
            raise ValueError('Cannot update with supplied data')
        self.fields.update(fields)

    @classmethod
    def brief_header(self):
        s  = u' Id  Done   ETA           Status       Download    Upload      Ratio  Name'
        return s
    
    def brief(self):
        s = u'% 3d: ' % (self.id)
        try:
            s += u'%5.1f%%' % self.progress
        except:
            pass
        try:
            if self.fields['eta'] > 0:
                s += u' %- 13s' % self.format_eta()
            else:
                s += u' -            '
        except:
            pass
        try:
            s += u' %- 12s' % self.status
        except:
            pass
        try:
            s += u' %5.1f % 3s/s' % format_size(self.rateDownload)
            s += u' %5.1f % 3s/s' % format_size(self.rateUpload)
        except:
            pass
        try:
            s += u' %6.2f' % self.ratio
        except:
            pass
        s += u' ' + self.name
        return s
    
    def __str__(self):
        s = ''
        s +=   '            id: ' + str(self.fields['id'])
        s += '\n          name: ' + self.fields['name']
        s += '\n          hash: ' + self.fields['hashString']
        s += '\n'
        try: # size
            f = ''
            f += '\n      progress: %.2f%%' % self.progress
            f += '\n    total size: %.2f %s' % format_size(self.totalSize)
            f += '\n reqested size: %.2f %s' % format_size(self.sizeWhenDone)
            f += '\nremaining size: %.2f %s' % format_size(self.leftUntilDone)
            f += '\n    valid size: %.2f %s' % format_size(self.haveValid)
            f += '\nunchecked size: %.2f %s' % format_size(self.haveUnchecked)
            s += f + '\n'
        except KeyError:
            pass
        try: # activity
            f = ''
            f += '\n        status: ' + str(self.status)
            f += '\n      download: %.2f %s/s' % format_size(self.rateDownload)
            f += '\n        upload: %.2f %s/s' % format_size(self.rateUpload)
            f += '\n     available: %.2f %s' % format_size(self.desiredAvailable)
            f += '\ndownload peers: ' + str(self.peersSendingToUs)
            f += '\n  upload peers: ' + str(self.peersGettingFromUs)
            s += f + '\n'
        except KeyError:
            pass
        try: # history
            f = ''
            f += '\n         ratio: %.2f' % self.ratio
            f += '\n    downloaded: %.2f %s' % format_size(self.downloadedEver)
            f += '\n      uploaded: %.2f %s' % format_size(self.uploadedEver)
            f += '\n        active: ' + str(self.date_active)
            f += '\n         added: ' + str(self.date_added)
            f += '\n       started: ' + str(self.date_started)
            f += '\n          done: ' + str(self.date_done)
            s += f + '\n'
        except KeyError:
            pass
        return s
    
    def files(self):
        s = ''
        indicies = xrange(len(self.fields['files']))
        files = self.fields['files']
        prio = self.fields['priorities']
        wanted = self.fields['wanted']
        index = 1
        for file in zip(indicies, files, prio, wanted):
            (size, unit) = format_size(file[1]['length'])
            selected = 'selected' if file[3] else 'not selected'
            priority = PRIORITY[file[2]]
            s += "% 3d: %- 7s %- 13s %5.1f %- 3s %s\n" % (file[0], priority, selected, size, unit, file[1]['name'])
            index += 1
        return s
    
    def __getattr__(self, name):
        try:
            return self.fields[name]
        except KeyError, e:
            raise AttributeError('No attribute %s' % name)
    
    @property
    def status(self):
        """Get the status as string."""
        return flag_list(self.fields['status'], STATUS)[0]
    
    @property
    def progress(self):
        """Get the download progress in percent as float."""
        return 100.0 * (self.fields['sizeWhenDone'] - self.fields['leftUntilDone']) / float(self.fields['sizeWhenDone'])
    
    @property
    def ratio(self):
        """Get the upload/download ratio."""
        try:
            return self.fields['uploadedEver'] / float(self.fields['downloadedEver'])
        except ZeroDivisionError:
            return 0.0
    
    @property
    def eta(self):
        """Get the eta as datetime.timedelta."""
        eta = self.fields['eta']
        if eta >= 0:
            return datetime.timedelta(seconds=eta)
        else:
            ValueError('eta not valid')

    @property
    def date_active(self):
        """Get the attribute "activityDate" as datetime.datetime."""
        return datetime.datetime.fromtimestamp(self.fields['activityDate'])

    @property
    def date_added(self):
        """Get the attribute "addedDate" as datetime.datetime."""
        return datetime.datetime.fromtimestamp(self.fields['addedDate'])

    @property
    def date_started(self):
        """Get the attribute "startDate" as datetime.datetime."""
        return datetime.datetime.fromtimestamp(self.fields['startDate'])

    @property
    def date_done(self):
        """Get the attribute "doneDate" as datetime.datetime."""
        return datetime.datetime.fromtimestamp(self.fields['doneDate'])
    
    def format_eta(self):
        """Returns the attribute "eta" formatted as a string."""
        eta = self.fields['eta']
        if eta == -1:
            return 'not available'
        elif eta == -2:
            return 'unknown'
        else:
            return format_timedelta(self.eta)

class Session(object):
    """
    Session is a class holding the session data for a Transmission daemon.
    """
    
    def __init__(self, fields={}):
        self.fields = fields
    
    def update(self, other):
        """Update the torrent data from a Transmission arguments dictinary"""

        fields = None
        if isinstance(other, dict):
            fields = other
        elif isinstance(other, Torrent):
            fields = other.fields
        else:
            raise ValueError('Cannot update with supplied data')
        self.fields.update(fields)
    
    def __getattr__(self, name):
        try:
            return self.fields[name]
        except KeyError, e:
            raise AttributeError('No attribute %s' % name)
    
    def __str__(self):
        text = ''
        for k, v in self.fields.iteritems():
            text += "% 32s: %s\n" % (k[-32:], v)
        return text

class TransmissionClient(object):    
    def __init__(self, address=None, port=None, verbose=False):
        self._http_connection = httplib.HTTPConnection(address, port)
        self._sequence = 0
        self.verbose = verbose
        self.torrents = {}
        self.session = Session()
    
    def _request(self, method, arguments):
        """Send json-rpc request to Transmission using http POST"""

        if not isinstance(method, (str, unicode)):
            raise ValueError('request takes method as string')
        if not isinstance(arguments, dict):
            raise ValueError('request takes arguments as dict')
        query = {'tag': self._sequence, 'method': method, 'arguments': arguments}
        self._sequence += 1
        start = time.time()
        if self.verbose:
            print(simplejson.dumps(query, indent=2))
        try:
            self._http_connection.request('POST', '/transmission/rpc', simplejson.dumps(query))
        except socket.error, e:
            raise TransmissionError('Failed to connect to daemon: %s' % (e))
        response = self._http_connection.getresponse()
        if response.status != 200:
            raise TransmissionError('Server responded with %d: \"%s\"' % (response.status, response.reason))
        http_data = response.read()
        elapsed = time.time() - start
        if self.verbose:
            print('http request took %.3f s' % (elapsed))
        
        data = simplejson.loads(http_data)

        if self.verbose:
            print(simplejson.dumps(data, indent=2))
        
        if data['result'] != 'success':
            raise TransmissionError('Query failed with result \"%s\"' % data['result'])

        if method == 'torrent-get':
            self._update_torrents(data['arguments']['torrents'])
        elif method == 'torrent-add':
            self._update_torrents([data['arguments']['torrent-added']])
        elif method == 'session-get':
            self._update_session(data['arguments'])

        return data
    
    def _format_ids(self, args):
        """Take things and make them valid torrent identifiers"""
        re_range = re.compile('^(\d*):(\d*)$')
        ids = []
        for line in args:
            for item in re.split(u'[ ,]+', line):
                if len(item) == 0:
                    continue
                addition = None
                try:
                    # handle index
                    addition = [int(item)]
                except ValueError:
                    pass
                if not addition:
                    # handle hashes
                    try:
                        int(item, 16)
                        addition = [item]
                    except:
                        pass
                if not addition:
                    # handle index ranges i.e. 5:10, 5:, :10
                    match = re_range.match(item)
                    if match:
                        from_ok = True
                        to_ok = True
                        idx_from = min(self.torrents.iterkeys())
                        idx_to = max(self.torrents.iterkeys())
                        try:
                            idx_from = int(match.group(1))
                        except:
                            from_ok = False
                        try:
                            idx_to = int(match.group(2))
                        except:
                            to_ok = False
                        if from_ok or to_ok:
                            addition = range(idx_from, idx_to + 1)
                if not addition:
                    # handle torrent names
                    for id, torrent in self.torrents.iteritems():
                        if torrent.name == item:
                            addition = [torrent.id]
                if not addition:
                    raise ValueError('Invalid torrent id, \"%s\"' % item)
                ids.extend(addition)
        return ids

    def _update_torrents(self, data):
        for fields in data:
            if fields['id'] in self.torrents:
                self.torrents[fields['id']].update(fields)
            else:
                self.torrents[fields['id']] = Torrent(fields)

    def _update_session(self, data):
        self.session.update(data)
    
    def add(self, data, **kwargs):
        """
        Add torrent to transfers list. Takes a base64 encoded .torrent file in data.
        Additional arguments are:
        
            * `paused`, boolean, Whether to pause the transfer on add.
            * `download_dir`, path, The directory where the downloaded contents saved in.
            * `peer_limit`, number, Limits the number of peers for this transfer.
        """
        args = {'metainfo': data}
        if 'paused' in kwargs:
            args['paused'] = rpc_bool(kwargs['paused'])
        if 'download_dir' in kwargs:
            args['download-dir'] = kwargs['download_dir']
        if 'peer_limit' in kwargs:
            args['peer-limit'] = int(kwargs['peer_limit'])
        self._request('torrent-add', args)
    
    def remove(self, ids):
        """remove torrent(s) with provided id(s)"""
        self._request('torrent-remove', {'ids': self._format_ids(ids)})
    
    def start(self, ids):
        """start torrent(s) with provided id(s)"""
        self._request('torrent-start', {'ids': self._format_ids(ids)})
    
    def stop(self, ids):
        """stop torrent(s) with provided id(s)"""
        self._request('torrent-stop', {'ids': self._format_ids(ids)})
    
    def verify(self, ids):
        """stop torrent(s) with provided id(s)"""
        self._request('torrent-verify', {'ids': self._format_ids(ids)})
    
    def info(self, ids):
        fields = TR_RPC_TORRENT_ACTIVITY | TR_RPC_TORRENT_ID | TR_RPC_TORRENT_HISTORY | TR_RPC_TORRENT_SIZE
        args = {'fields': fields}
        args['ids'] = self._format_ids(ids)
        self._request('torrent-get', args)
        result = {}
        for id, torrent in self.torrents.iteritems():
            if id in args['ids']:
                result[id] = torrent
            elif torrent.hashString in args['ids']:
                result[id] = torrent
        return result
    
    def files(self, ids):
        fields = TR_RPC_TORRENT_ID | TR_RPC_TORRENT_FILES | TR_RPC_TORRENT_PRIORITIES
        args = {'fields': fields}
        args['ids'] = self._format_ids(ids)
        self._request('torrent-get', args)
        result = {}
        for id, torrent in self.torrents.iteritems():
            if id in args['ids']:
                result[id] = torrent
            elif torrent.hashString in args['ids']:
                result[id] = torrent
        return result
    
    def list(self, fields=[], ids=None):
        """list torrent(s) with provided id(s)"""
        
        field_flag = 0
        for field in fields:
            if field in FIELDS:
                field_flag += FIELDS[field]
        if field_flag == 0:
            field_flag = TR_RPC_TORRENT_ACTIVITY | TR_RPC_TORRENT_ID | TR_RPC_TORRENT_HISTORY | TR_RPC_TORRENT_SIZE
        #print(field_flag)
        self._request('torrent-get', {'fields': field_flag})
        return self.torrents

    def change(self, ids, **kwargs):
        args = {}
        args['ids'] = self._format_ids(ids)
        if len(args['ids']) == 0:
            raise ValueError()        
        try:
            files = [int(file) for file in re.split('[ ,]+', kwargs['files-enabled'])]
            args['files-wanted'] = files
        except:
            pass
        try:
            files = [int(file) for file in re.split('[ ,]+', kwargs['files-disabled'])]
            args['files-unwanted'] = files
        except:
            pass
        try:
            args['peer-limit'] = int(kwargs['peer-limit'])
        except:
            pass
        try:
            args['priority-high'] = list(kwargs['files-high'])
        except:
            pass
        try:
            args['priority-high'] = list(kwargs['files-high'])
        except:
            pass
        try:
            args['priority-high'] = list(kwargs['files-high'])
        except:
            pass
        try:
            limit = int(kwargs['limit-up'])
            if limit >= 0:
                args['speed-limit-up'] = limit
            args['speed-limit-up-enabled'] = rpc_bool(limit >= 0)
        except:
            pass
        try:
            limit = int(kwargs['limit-down'])
            if limit >= 0:
                args['speed-limit-down'] = limit
            args['speed-limit-down-enabled'] = rpc_bool(limit >= 0)
        except:
            pass
        if len(args) > 1:
            self._request('torrent-set', args)
    
    def session_get(self):
        self._request('session-get', {})
    
    def session_set(self, **kwargs):        
        self._request('session-set', )

    def session_stats(self):
        return self._request('session-stats', {})['arguments']['session-stats']

if __name__ == '__main__':
    tc = TransmissionClient('localhost', DEFAULT_PORT)
    tc._request('torrent-get', {'fields': TR_RPC_TORRENT_ID | TR_RPC_TORRENT_ACTIVITY})
