#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

import os, time, datetime
import re
import socket, httplib, urllib2, base64
import simplejson
from constants import *
from utils import *

__author__    = u'Erik Svensson <erik.public@gmail.com>'
__version__   = u'0.1'
__copyright__ = u'Copyright (c) 2008 Erik Svensson'
__license__   = u'MIT'

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
    
    def files(self):
        """
        .. _transmission-torrent-files:
        
        Get list of files for this torrent.

        This function returns a dictionary with file information for each file.
        The file information is has following fields:
        
        ::
        
            {
                <file id>: {
                    'name': <file name>,
                    'size': <file size in bytes>,
                    'completed': <bytes completed>,
                    'priority': <priority ('high'|'normal'|'low')>,
                    'selected': <selected for download>
                }
                
                ...
            }

        Example:
        ::
        
            {
                0: {
                    'priority': 'normal',
                    'completed': 729186304,
                    'selected': True,
                    'name': 'ubuntu-8.10-beta-desktop-i386.iso',
                    'size': 729186304
                }
            }
        """
        result = {}
        if 'files' in self.fields:
            indicies = xrange(len(self.fields['files']))
            files = self.fields['files']
            priorities = self.fields['priorities']
            wanted = self.fields['wanted']
            index = 1
            for item in zip(indicies, files, priorities, wanted):
                selected = True if item[3] else False
                priority = PRIORITY[item[2]]
                result[item[0]] = {
                    'selected': selected,
                    'priority': priority,
                    'size': item[1]['length'],
                    'name': item[1]['name'],
                    'completed': item[1]['bytesCompleted']}
        return result
    
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

class Client(object):
    """
    This is it. This class implements the Json-RPC protocol to communicate with Transmission.
    """
    
    def __init__(self, address='localhost', port=DEFAULT_PORT, verbose=False):
        self._http_connection = httplib.HTTPConnection(address, port)
        self._sequence = 0
        self.verbose = verbose
        self.session = Session()
    
    def _request(self, method, arguments={}, ids=[], require_ids = False):
        """Send json-rpc request to Transmission using http POST"""
        
        if not isinstance(method, (str, unicode)):
            raise ValueError('request takes method as string')
        if not isinstance(arguments, dict):
            raise ValueError('request takes arguments as dict')
        ids = self._format_ids(ids)
        if len(ids) > 0:
            arguments['ids'] = ids
        elif require_ids:
            raise ValueError('request require ids')
        
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
        
        self._http_connection.close()
        
        if self.verbose:
            print(simplejson.dumps(data, indent=2))
        
        if data['result'] != 'success':
            raise TransmissionError('Query failed with result \"%s\"' % data['result'])
        
        results = {}
        if method == 'torrent-get':
            for item in data['arguments']['torrents']:
                results[item['id']] = Torrent(item)
        elif method == 'torrent-add':
            for item in data['arguments']['torrent-added']:
                results[item['id']] = Torrent(item)
        elif method == 'session-get':
            self._update_session(data['arguments'])
        elif method == 'session-stats':
            self._update_session(data['arguments']['session-stats'])
        
        if len(results) > 0:
            return results
        else:
            return None
    
    def _format_ids(self, args):
        """Take things and make them valid torrent identifiers"""
        re_range = re.compile('^(\d+):(\d+)$')
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
                        # handle index ranges i.e. 5:10
                        match = re_range.match(item)
                        if match:
                            try:
                                idx_from = int(match.group(1))
                                idx_to = int(match.group(2))
                                addition = range(idx_from, idx_to + 1)
                            except:
                                pass
                    if not addition:
                        raise ValueError('Invalid torrent id, \"%s\"' % item)
                    ids.extend(addition)
            elif isinstance(line, (int, long)):
                ids.append(line)
        return ids
    
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
        return self._request('torrent-add', args)
    
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
        return self.add(torrent_data, **kwargs)
    
    def remove(self, ids):
        """remove torrent(s) with provided id(s)"""
        self._request('torrent-remove', {}, ids, True)
    
    def start(self, ids):
        """start torrent(s) with provided id(s)"""
        self._request('torrent-start', {}, ids, True)
    
    def stop(self, ids):
        """stop torrent(s) with provided id(s)"""
        self._request('torrent-stop', {}, ids, True)
    
    def verify(self, ids):
        """verify torrent(s) with provided id(s)"""
        self._request('torrent-verify', {}, ids, True)
    
    def info(self, ids=[]):
        """Get detailed information for torrent(s) with provided id(s)."""
        return self._request('torrent-get', {'fields': FIELDS}, ids)
    
    def get_files(self, ids=[]):
        """
        .. _transmission-client-get_files:
        
        Get list of files for provided torrent id(s).
        This function returns a dictonary for each requested torrent id holding the information about the files.
        See :ref:`Torrent.files() <transmission-torrent-files>`.
        
        ::
        
            {
                <torrent id>: {
                    <file id>: {
                        'name': <file name>,
                        'size': <file size in bytes>,
                        'completed': <bytes completed>,
                        'priority': <priority ('high'|'normal'|'low')>,
                        'selected': <selected for download>
                    }
                    
                    ...
                }
                
                ...
            }
        
        Example:
        ::
        
            {
                1: {
                    0: {
                        'name': 'ubuntu-8.10-beta-desktop-i386.iso',
                        'size': 729186304,
                        'completed': 729186304,
                        'priority': 'normal',
                        'selected': True
                    }
                }
            }
        """
        fields = ['id', 'name', 'hashString', 'files', 'priorities', 'wanted']
        request_result = self._request('torrent-get', {'fields': fields}, ids)
        result = {}
        for id, torrent in request_result.iteritems():
            result[id] = torrent.files()
        return result
    
    def set_files(self, items):
        """
        .. _transmission-client-set_files:
        
        Set file properties. Takes a dictonary with similar contents as the result of :ref:`get_files() <transmission-client-get_files>`.
        Also see :ref:`Torrent.files() <transmission-torrent-files>`.
        
        ::
        
            {
                <torrent id>: {
                    <file id>: {
                        'priority': <priority ('high'|'normal'|'low')>,
                        'selected': <selected for download>
                    }
                    
                    ...
                }
                
                ...
            }
        
        Example:
        ::
        
            items = {
                1: {
                    0: {
                        'priority': 'normal',
                        'selected': True,
                    }
                    1: {
                        'priority': 'low',
                        'selected': True,
                    }
                }
                2: {
                    0: {
                        'priority': 'high',
                        'selected': False,
                    }
                    1: {
                        'priority': 'low',
                        'selected': True,
                    }
                }
            }
            
            client.set_files(items)
        
        """
        if not isinstance(files, dict):
            raise ValueError('Invalid file description')
        for tid, files in items:
            if not isinstance(items, dict):
                continue
            wanted = []
            unwanted = []
            priority_high = []
            priority_normal = []
            priority_low = []
            for fid, file in files:
                if not isinstance(file, dict):
                    continue
                if 'selected' in file and file['selected']:
                    wanted.append(fid)
                else:
                    unwanted.append(fid)
                if 'priority' in file:
                    if file['priority'] == 'high':
                        priority_high.append(fid)
                    elif file['priority'] == 'normal':
                        priority_normal.append(fid)
                    elif file['priority'] == 'low':
                        priority_low.append(fid)
            self.change(tid, wanted, unwanted, priority_high, priority_normal, priority_low)
    
    def list(self):
        """list torrent(s) with provided id(s)"""
        fields = ['id', 'hashString', 'name', 'sizeWhenDone', 'leftUntilDone', 'eta', 'status', 'rateUpload', 'rateDownload', 'uploadedEver', 'downloadedEver']
        return self._request('torrent-get', {'fields': fields})

    def change(self, ids, **kwargs):
        """
        Change torrent parameters. This is the list of parameters that.
        """
        
        try:
            files = [int(file) for file in re.split('[ ,]+', kwargs['files_wanted'])]
            args['files-wanted'] = files
        except KeyError:
            pass
        try:
            files = [int(file) for file in re.split('[ ,]+', kwargs['files_unwanted'])]
            args['files-unwanted'] = files
        except KeyError:
            pass
        try:
            args['peer-limit'] = int(kwargs['peer_limit'])
        except KeyError:
            pass
        try:
            args['priority-high'] = list(kwargs['priority_high'])
        except KeyError:
            pass
        try:
            args['priority-normal'] = list(kwargs['priority_normal'])
        except KeyError:
            pass
        try:
            args['priority-low'] = list(kwargs['priority_low'])
        except KeyError:
            pass
        try:
            args['speed-limit-up'] = int(kwargs['speed_limit_up'])
        except KeyError:
            pass
        try:
            args['speed-limit-up-enabled'] = rpc_bool(kwargs['speed_limit_up_enabled'])
        except KeyError:
            pass
        try:
            args['speed-limit-down'] = int(kwargs['speed_limit_down'])
        except KeyError:
            pass
        try:
            args['speed-limit-down-enabled'] = rpc_bool(kwargs['speed_limit_down_enable'])
        except KeyError:
            pass
        
        if len(args) > 1:
            self._request('torrent-set', args, ids, True)
    
    def session_get(self):
        """Get session parameters"""
        self._request('session-get')
        return self.session
    
    def session_set(self, **kwargs):
        """Set session parameters"""
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
            args['download-dir'] = kwargs['download_dir']
        except KeyError:
            pass
        try:
            args['peer-limit'] = int(kwargs['peer_limit'])
        except KeyError:
            pass
        try:
            args['pex-allowed'] = rpc_bool(kwargs['pex_allowed'])
        except KeyError:
            pass
        try:
            args['port'] = int(kwargs['port'])
        except KeyError:
            pass
        try:
            args['port-forwarding-enabled'] = rpc_bool(kwargs['port_forwarding_enabled'])
        except KeyError:
            pass
        try:
            args['speed-limit-down'] = int(kwargs['speed_limit_down'])
        except KeyError:
            pass
        try:
            args['speed-limit-down-enabled'] = int(kwargs['speed_limit_down_enabled'])
        except KeyError:
            pass
        try:
            args['speed-limit-up'] = int(kwargs['speed_limit_up'])
        except KeyError:
            pass
        try:
            args['speed-limit-up-enabled'] = int(kwargs['speed_limit_up_enabled'])
        except KeyError:
            pass
        
        if len(args) > 1:
            self._request('session-set', args)
    
    def session_stats(self):
        """Get session statistics"""
        self._request('session-stats')
        return self.session
