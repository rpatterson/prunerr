#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

import os, time, datetime
import re
import socket, httplib, urllib2, base64
import simplejson
from constants import *
from utils import *

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
    
    def __repr__(self):
        return '<Torrent %d \"%s\">' % (self.fields['id'], self.fields['name'])
    
    def __str__(self):
        return 'torrent %s' % self.fields['name']
    
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
            s += u' -status     '
            pass
        try:
            s += u' %5.1f %- 5s' % format_speed(self.rateDownload)
            s += u' %5.1f %- 5s' % format_speed(self.rateUpload)
        except:
            s += u' -rate     '
            s += u' -rate     '
            pass
        try:
            s += u' %6.2f' % self.ratio
        except:    
            s += u' -ratio'
            pass
        s += u' ' + self.name
        return s
    
    def detail(self):
        s = ''
        s +=   '            id: ' + str(self.fields['id'])
        s += '\n          name: ' + self.fields['name']
        s += '\n          hash: ' + self.fields['hashString']
        s += '\n'
        try: # size
            f = ''
            f += '\n      progress: %.2f%%' % self.progress
            f += '\n         total: %.2f %s' % format_size(self.totalSize)
            f += '\n      reqested: %.2f %s' % format_size(self.sizeWhenDone)
            f += '\n     remaining: %.2f %s' % format_size(self.leftUntilDone)
            f += '\n      verified: %.2f %s' % format_size(self.haveValid)
            f += '\n  not verified: %.2f %s' % format_size(self.haveUnchecked)
            s += f + '\n'
        except KeyError:
            pass
        try: # activity
            f = ''
            f += '\n        status: ' + str(self.status)
            f += '\n      download: %.2f %s' % format_speed(self.rateDownload)
            f += '\n        upload: %.2f %s' % format_speed(self.rateUpload)
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
            f += '\n        active: ' + format_timestamp(self.activityDate)
            f += '\n         added: ' + format_timestamp(self.addedDate)
            f += '\n       started: ' + format_timestamp(self.startDate)
            f += '\n          done: ' + format_timestamp(self.doneDate)
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
        return STATUS[self.fields['status']]
    
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
        """Get the "eta" as datetime.timedelta."""
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
        self.fields = {}
        for k, v in fields.iteritems():
            key = k.replace('-', '_')
            self.fields[key] = v
    
    def update(self, other):
        """Update the torrent data from a Transmission arguments dictinary"""
        
        fields = None
        if isinstance(other, dict):
            fields = other
        elif isinstance(other, Torrent):
            fields = other.fields
        else:
            raise ValueError('Cannot update with supplied data')
        
        for k, v in fields.iteritems():
            self.fields[k.replace('-', '_')] = v
    
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

class Transmission(object):
    def __init__(self, address='localhost', port=DEFAULT_PORT, verbose=False):
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
            self._http_connection.close()
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
        elif method == 'session-stats':
            self._update_session(data['arguments']['session-stats'])
        
        self._http_connection.close()
        return data
    
    def _format_ids(self, args):
        """Take things and make them valid torrent identifiers"""
        re_range = re.compile('^(\d*):(\d*)$')
        ids = []
        for line in args:
            if isinstance(line, (str, unicode)):
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
            elif isinstance(line, (int, long)):
                ids.append(line)
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
            * `download_dir`, path, The directory where the downloaded contents will be saved in.
            * `peer_limit`, number, Limits the number of peers for this transfer.
        """
        args = {'metainfo': data}
        if 'paused' in kwargs:
            args['paused'] = rpc_bool(kwargs['paused'])
        if 'download_dir' in kwargs:
            args['download-dir'] = kwargs['downloadDir']
        if 'peer_limit' in kwargs:
            args['peer-limit'] = int(kwargs['peerLimit'])
        self._request('torrent-add', args)
    
    def add_url(self, torrent_url, **kwargs):
        """
        Add torrent to transfers list. Takes a url to a .torrent file.
        Additional arguments are:
        
            * `paused`, boolean, Whether to pause the transfer on add.
            * `download_dir`, path, The directory where the downloaded contents will be saved in.
            * `peer_limit`, number, Limits the number of peers for this transfer.
        """
        torrent_file = None
        if os.path.exists(torrent_url):
            torrent_file = open(torrent_url, 'r')
        else:
            try:
                torrent_file = urllib2.urlopen(torrent_url)
            except:
                torrent_file = None
        
        if not torrent_file:
            raise TransmissionError('File does not exist.')
        
        torrent_data = base64.b64encode(torrent_file.read())
        self.add(torrent_data, **kwargs)
    
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
        """verify torrent(s) with provided id(s)"""
        self._request('torrent-verify', {'ids': self._format_ids(ids)})
    
    def info(self, ids=[]):
        """Get detailed information for torrent(s) with provided id(s)."""
        fields = FIELDS
        args = {'fields': fields}
        if len(ids) > 0:
            args['ids'] = self._format_ids(ids)
        self._request('torrent-get', args)
        result = {}
        if 'ids' not in args:
            result = self.torrents
        else:
            for id, torrent in self.torrents.iteritems():
                if id in args['ids']:
                    result[id] = torrent
                elif torrent.hashString in args['ids']:
                    result[id] = torrent
        return result
    
    def files(self, ids):
        """Get list of files for provided torrent id(s)."""
        fields = ['id', 'name', 'hashString', 'files', 'priorities', 'wanted']
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
    
    def list(self):
        """list torrent(s) with provided id(s)"""
        fields = ['id', 'hashString', 'name', 'sizeWhenDone', 'leftUntilDone', 'eta', 'status', 'rateUpload', 'rateDownload', 'uploadedEver', 'downloadedEver']
        self._request('torrent-get', {'fields': fields})
        return self.torrents

    def change(self, ids, **kwargs):
        args = {}
        args['ids'] = self._format_ids(ids)
        if len(args['ids']) == 0:
            raise ValueError()
        try:
            files = [int(file) for file in re.split('[ ,]+', kwargs['filesWanted'])]
            args['files-wanted'] = files
        except KeyError:
            pass
        try:
            files = [int(file) for file in re.split('[ ,]+', kwargs['filesUnwanted'])]
            args['files-unwanted'] = files
        except KeyError:
            pass
        try:
            args['peer-limit'] = int(kwargs['peerLimit'])
        except KeyError:
            pass
        try:
            args['priority-high'] = list(kwargs['priorityHigh'])
        except KeyError:
            pass
        try:
            args['priority-normal'] = list(kwargs['priorityNormal'])
        except KeyError:
            pass
        try:
            args['priority-low'] = list(kwargs['priorityLow'])
        except KeyError:
            pass
        try:
            args['speed-limit-up'] = int(kwargs['speedLimitUp'])
        except KeyError:
            pass
        try:
            args['speed-limit-up-enabled'] = rpc_bool(kwargs['speedLimitUpEnabled'])
        except KeyError:
            pass
        try:
            args['speed-limit-down'] = int(kwargs['speedLimitDown'])
        except KeyError:
            pass
        try:
            args['speed-limit-down-enabled'] = rpc_bool(kwargs['speedLimitDownEnabled'])
        except KeyError:
            pass
        
        if len(args) > 1:
            self._request('torrent-set', args)
    
    def session_get(self):
        self._request('session-get', {})
        return self.session
    
    def session_set(self, **kwargs):
        args = {}
        
        try:
            encryption = str(kwargs['encryption'])
            if encryption in ['required', 'preferred', 'tolerated']:
                args['encryption'] = encryption
            else:
                raise ValueError('Invalid encryption value')
        except KeyError:
            pass
        try:
            args['download-dir'] = kwargs['downloadDir']
        except KeyError:
            pass
        try:
            args['peer-limit'] = int(kwargs['peerLimit'])
        except KeyError:
            pass
        try:
            args['pex-allowed'] = rpc_bool(kwargs['pexAllowed'])
        except KeyError:
            pass
        try:
            args['port'] = int(kwargs['port'])
        except KeyError:
            pass
        try:
            args['port-forwarding-enabled'] = rpc_bool(kwargs['portForwardingEnabled'])
        except KeyError:
            pass
        try:
            args['speed-limit-down'] = int(kwargs['speedLimitDown'])
        except KeyError:
            pass
        try:
            args['speed-limit-down-enabled'] = int(kwargs['speedLimitDownEnabled'])
        except KeyError:
            pass
        try:
            args['speed-limit-up'] = int(kwargs['speedLimitUp'])
        except KeyError:
            pass
        try:
            args['speed-limit-up-enabled'] = int(kwargs['speedLimitUpEnabled'])
        except KeyError:
            pass
        
        if len(args) > 1:
            self._request('session-set', args)
    
    def session_stats(self):
        self._request('session-stats', {})
        return self.session
