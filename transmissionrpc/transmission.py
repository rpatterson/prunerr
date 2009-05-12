# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

import sys, os, time, datetime
import re, logging
import httplib, urllib2, base64

try:
    import json
except ImportError:
    import simplejson as json

from constants import *
from utils import *

class TransmissionError(Exception):
    def __init__(self, message='', original=None):
        Exception.__init__(self, message)
        self.original = original

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
        Get list of files for this torrent. This function returns a dictionary with file information for each file.
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
        try:
            return 100.0 * (self.fields['sizeWhenDone'] - self.fields['leftUntilDone']) / float(self.fields['sizeWhenDone'])
        except ZeroDivisionError:
            return 0.0
    
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
    
    Access the session field can be done through attributes.
    The attributes available are the same as the session arguments in the
    Transmission RPC specification, but with underscore instead of hypen.
    ``download-dir`` -> ``download_dir``.
    """
    
    def __init__(self, fields={}):
        self.fields = {}
        for k, v in fields.iteritems():
            key = k.replace('-', '_')
            self.fields[key] = v
    
    def update(self, other):
        """Update the session data from a session arguments dictinary"""
        
        fields = None
        if isinstance(other, dict):
            fields = other
        elif isinstance(other, Session):
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
    This is it. This class implements the json-RPC protocol to communicate with Transmission.
    """
    
    def __init__(self, address='localhost', port=DEFAULT_PORT, user=None, password=None, verbose=False):
        base_url = 'http://' + address + ':' + str(port)
        self.url = base_url + '/transmission/rpc'
        if user and password:
            password_manager = urllib2.HTTPPasswordMgrWithDefaultRealm()
            password_manager.add_password(realm=None, uri=self.url, user=user, passwd=password)
            opener = urllib2.build_opener(
                urllib2.HTTPBasicAuthHandler(password_manager)
                , urllib2.HTTPDigestAuthHandler(password_manager)
                )
            urllib2.install_opener(opener)
        elif user or password:
            logging.warning('Either user or password missing, not using authentication.')
        self._sequence = 0
        self.verbose = verbose
        self.session = Session()
    
    def _http_query(self, query):
        request = urllib2.Request(self.url, query)
        retry = 0
        while True:
            try:
                response = urllib2.urlopen(request)
                break
            except urllib2.HTTPError, e:
                raise TransmissionError('Server responded with: %s.' % (e), e)
            except urllib2.URLError, e:
                raise TransmissionError('Failed to connect to daemon.', e)
            except httplib.BadStatusLine, e:
                retry = retry + 1
                if (retry > 1):
                    raise TransmissionError('Server responded with: "%s" when requesting %s "%s".' % (e.args, self.url, query), e)
        result = response.read()
        return result
    
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
        
        query = json.dumps({'tag': self._sequence, 'method': method, 'arguments': arguments})
        if self.verbose:
            logging.info(query)
        self._sequence += 1
        start = time.time()
        http_data = self._http_query(query)
        elapsed = time.time() - start
        if self.verbose:
            logging.info('http request took %.3f s' % (elapsed))
        
        try:
            data = json.loads(http_data)
        except ValueError, e:
            logging.error('Error: ' + str(e))
            logging.error('Request: \"%s\"' % (query))
            logging.error('HTTP data: \"%s\"' % (http_data))
            raise
        
        if self.verbose:
            logging.info(json.dumps(data, indent=2))
        
        if data['result'] != 'success':
            raise TransmissionError('Query failed with result \"%s\"' % data['result'])
        
        results = {}
        if method == 'torrent-get':
            for item in data['arguments']['torrents']:
                results[item['id']] = Torrent(item)
        elif method == 'torrent-add':
            item = data['arguments']['torrent-added']
            results[item['id']] = Torrent(item)
        elif method == 'session-get':
            self._update_session(data['arguments'])
        elif method == 'session-stats':
            # older versions of T has the return data in "session-stats"
            if 'session-stats' in data['arguments']:
                self._update_session(data['arguments']['session-stats'])
            else:
                self._update_session(data['arguments'])
        else:
            return None
        
        return results
    
    def _format_ids(self, args):
        """Take things and make them valid torrent identifiers"""
        ids = []
        
        if isinstance(args, (int, long)):
            ids.append(args)
        elif isinstance(args, (str, unicode)):
            for item in re.split(u'[ ,]+', args):
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
                    match = re.match(u'^(\d+):(\d+)$', item)
                    if match:
                        try:
                            idx_from = int(match.group(1))
                            idx_to = int(match.group(2))
                            addition = range(idx_from, idx_to + 1)
                        except:
                            pass
                if not addition:
                    raise ValueError(u'Invalid torrent id, \"%s\"' % item)
                ids.extend(addition)
        elif isinstance(args, (list)):
            for item in args:
                ids.extend(self._format_ids(item))
        else:
            raise ValueError(u'Invalid torrent id')
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
            args['download-dir'] = kwargs['download_dir']
        if 'peer_limit' in kwargs:
            args['peer-limit'] = int(kwargs['peer_limit'])
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
    
    def remove(self, ids, delete_data=False):
        """remove torrent(s) with provided id(s). Local data is removed if delete_data is True, otherwise not."""
        self._request('torrent-remove', {'delete-local-data': rpc_bool(delete_data)}, ids, True)
    
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
        Get list of files for provided torrent id(s).
        This function returns a dictonary for each requested torrent id holding the information about the files.
        """
        fields = ['id', 'name', 'hashString', 'files', 'priorities', 'wanted']
        request_result = self._request('torrent-get', {'fields': fields}, ids)
        result = {}
        for id, torrent in request_result.iteritems():
            result[id] = torrent.files()
        return result
    
    def set_files(self, items):
        """
        Set file properties. Takes a dictonary with similar contents as the result of get_files.
        """
        if not isinstance(items, dict):
            raise ValueError('Invalid file description')
        for tid, files in items.iteritems():
            if not isinstance(files, dict):
                continue
            wanted = []
            unwanted = []
            priority_high = []
            priority_normal = []
            priority_low = []
            for fid, file in files.iteritems():
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
            self.change([tid], files_wanted = wanted, files_unwanted = unwanted, priority_high = priority_high, priority_normal = priority_normal, priority_low = priority_low)
    
    def list(self):
        """list all torrents"""
        fields = ['id', 'hashString', 'name', 'sizeWhenDone', 'leftUntilDone', 'eta', 'status', 'rateUpload', 'rateDownload', 'uploadedEver', 'downloadedEver']
        return self._request('torrent-get', {'fields': fields})
    
    def change(self, ids, **kwargs):
        """
        Change torrent parameters. This is the list of parameters that.
        """
        args = {}

        try:
            files = kwargs['files_wanted']
            if not isinstance(files, list):
                files = [int(file) for file in re.split('[ ,]+', files)]
            args['files-wanted'] = files
        except KeyError:
            pass
        try:
            files = kwargs['files_unwanted']
            if not isinstance(files, list):
                files = [int(file) for file in re.split('[ ,]+', files)]
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
            args['speed-limit-down-enabled'] = rpc_bool(kwargs['speed_limit_down_enabled'])
        except KeyError:
            pass
        
        if len(args) > 1:
            self._request('torrent-set', args, ids, True)
    
    def get_session(self):
        """Get session parameters"""
        self._request('session-get')
        return self.session
    
    def set_session(self, **kwargs):
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
        
        if len(args) > 0:
            self._request('session-set', args)
    
    def session_stats(self):
        """Get session statistics"""
        self._request('session-stats')
        return self.session
