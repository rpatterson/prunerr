# -*- coding: utf-8 -*-
# Copyright (c) 2008-2010 Erik Svensson <erik.public@gmail.com>
# Licensed under the MIT license.

import sys, os, re, time, datetime
import warnings
import httplib, urllib2, urlparse, base64

try:
    import json
except ImportError:
    import simplejson as json

from transmissionrpc.constants import DEFAULT_PORT, DEFAULT_TIMEOUT, STATUS, PRIORITY
from transmissionrpc.utils import logger, format_timedelta, get_arguments, make_rpc_name, argument_value_convert, rpc_bool
from transmissionrpc.httphandler import HTTPHandlerError, HTTPHandler

class TransmissionError(Exception):
    def __init__(self, message='', original=None):
        Exception.__init__(self)
        self.message = message
        self.original = original

    def __str__(self):
        if self.original:
            original_name = type(self.original).__name__
            return '%s Original exception: %s, "%s"' % (self.message, original_name, str(self.original))
        else:
            return self.message

class Torrent(object):
    """
    Torrent is a class holding the data raceived from Transmission regarding a bittorrent transfer.
    All fetched torrent fields are accessable through this class using attributes.
    This class has a few convenience properties using the torrent data.
    """

    def __init__(self, fields):
        if 'id' not in fields:
            raise ValueError('Torrent requires an id')
        self.fields = {}
        self.update(fields)

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
        for k, v in fields.iteritems():
            self.fields[k.replace('-', '_')] = v

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
        except KeyError:
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
    
    @property
    def priority(self):
        """Get the priority as string."""
        return PRIORITY[self.fields['bandwidthPriority']]

class Session(object):
    """
    Session is a class holding the session data for a Transmission daemon.

    Access the session field can be done through attributes.
    The attributes available are the same as the session arguments in the
    Transmission RPC specification, but with underscore instead of hypen.
    ``download-dir`` -> ``download_dir``.
    """

    def __init__(self, fields=None):
        self.fields = {}
        if fields != None:
            self.update(fields)

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
        except KeyError:
            raise AttributeError('No attribute %s' % name)

    def __str__(self):
        text = ''
        for k in sorted(self.fields.keys()):
            text += "% 32s: %s\n" % (k[-32:], self.fields[k])
        return text

class DefaultHTTPHandler(HTTPHandler):
    def __init__(self):
        HTTPHandler.__init__(self)
    
    def set_authentication(self, uri, login, password):    
        password_manager = urllib2.HTTPPasswordMgrWithDefaultRealm()
        password_manager.add_password(realm=None, uri=uri, user=login, passwd=password)
        opener = urllib2.build_opener(
            urllib2.HTTPBasicAuthHandler(password_manager)
            , urllib2.HTTPDigestAuthHandler(password_manager)
            )
        urllib2.install_opener(opener)
    
    def request(self, url, query, headers, timeout):        
        request = urllib2.Request(url, query, headers)
        try:
            if (sys.version_info[0] == 2 and sys.version_info[1] > 5) or sys.version_info[0] > 2:
                logger.debug('Using timeout %f s' % (timeout))
                response = urllib2.urlopen(request, timeout=timeout)
            else:
                response = urllib2.urlopen(request)
        except urllib2.HTTPError, error:
            raise HTTPHandlerError(error.filename, error.code, error.msg, dict(error.headers), error.read())
        except urllib2.URLError, error:
            if hasattr(error.reason, 'args') and isinstance(error.reason.args, tuple):
                raise HTTPHandlerError(httpcode=error.reason.args[0], httpmsg=error.reason.args[1])
            else:
                raise HTTPHandlerError(httpmsg='urllib2.URLError: %s' % (error.reason))
        except httplib.BadStatusLine, error:
            raise HTTPHandlerError(httpmsg='httplib.BadStatusLine: %s' % (error.line))
        return response.read()

class Client(object):
    """
    This is it. This class implements the JSON-RPC protocol to communicate with Transmission.

    Torrent ids
    -----------

    Many functions in Client takes torrent id. A torrent id can either be id or
    hashString. When suppling multiple id's it is possible to use a list mixed
    with both id and hashString.

    Timeouts
    --------

    Since most methods results in HTTP requests against Transmission, it is
    possible to provide a argument called ``timeout``. Timeout is only effective
    when using Python 2.6 or later and the default timeout is 30 seconds.
    """

    def __init__(self, address='localhost', port=DEFAULT_PORT, user=None, password=None, http_handler=None, timeout=None):
        if isinstance(timeout, (int, long, float)):
            self._query_timeout = float(timeout)
        else:
            self._query_timeout = DEFAULT_TIMEOUT
        urlo = urlparse.urlparse(address)
        if urlo.scheme == '':
            base_url = 'http://' + address + ':' + str(port)
            self.url = base_url + '/transmission/rpc'
        else:
            if urlo.port:
                self.url = urlo.scheme + '://' + urlo.hostname + ':' + str(urlo.port) + urlo.path
            else:
                self.url = urlo.scheme + '://' + urlo.hostname + urlo.path
            logger.info('Using custom URL "' + self.url + '".')
            if urlo.username and urlo.password:
                user = urlo.username
                password = urlo.password
            elif urlo.username or urlo.password:
                logger.warning('Either user or password missing, not using authentication.')
        if http_handler == None:
            self.http_handler = DefaultHTTPHandler()
        else:
            if hasattr(http_handler, 'set_authentication') and hasattr(http_handler, 'request'):
                self.http_handler = http_handler
            else:
                raise ValueError('Invalid HTTP handler.')
        if user and password:
            self.http_handler.set_authentication(self.url, user, password)
        elif user or password:
            logger.warning('Either user or password missing, not using authentication.')
        self._sequence = 0
        self.session = Session()
        self.session_id = 0
        self.protocol_version = None
        self.get_session()
        self.torrent_get_arguments = get_arguments('torrent-get'
                                                   , self.rpc_version)

    def get_timeout(self):
        return self._query_timeout
    
    def set_timeout(self, value):
        self._query_timeout = float(value)
    
    def del_timeout(self):
        self._query_timeout = DEFAULT_TIMEOUT
    
    timeout = property(get_timeout, set_timeout, del_timeout, doc="Query timeout.")

    def _debug_httperror(self, error):
        try:
            data = json.loads(error.data)
        except ValueError:
            data = error.data
        logger.debug(
            json.dumps(
                {
                    'response': {
                        'url': error.url,
                        'code': error.code,
                        'msg': error.message,
                        'headers': error.headers,
                        'data': data,
                    }
                },
                indent=2
            )
        )

    def _http_query(self, query, timeout=None):
        headers = {'x-transmission-session-id': self.session_id}
        request_count = 0
        if timeout == None:
            timeout = self._query_timeout
        while True:
            logger.debug(json.dumps({'url': self.url, 'headers': headers, 'query': query, 'timeout': timeout}, indent=2))
            try:
                result = self.http_handler.request(self.url, query, headers, timeout)
                break
            except HTTPHandlerError, error:
                if error.code == 409:
                    logger.info('Server responded with 409, trying to set session-id.')
                    if request_count > 1:
                        raise TransmissionError('Session ID negotiation failed.', error)
                    if 'x-transmission-session-id' in error.headers:
                        self.session_id = error.headers['x-transmission-session-id']
                        headers = {'x-transmission-session-id': self.session_id}
                    else:
                        raise TransmissionError('Unknown conflict.', error)
                else:
                    raise TransmissionError('Request failed.', error)
                self._debug_httperror(error)
            request_count = request_count + 1
        return result

    def _request(self, method, arguments={}, ids=[], require_ids=False, timeout=None):
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

        query = json.dumps({'tag': self._sequence, 'method': method
                            , 'arguments': arguments})
        self._sequence += 1
        start = time.time()
        http_data = self._http_query(query, timeout)
        elapsed = time.time() - start
        logger.info('http request took %.3f s' % (elapsed))

        try:
            data = json.loads(http_data)
        except ValueError, e:
            logger.error('Error: ' + str(e))
            logger.error('Request: \"%s\"' % (query))
            logger.error('HTTP data: \"%s\"' % (http_data))
            raise

        logger.debug(json.dumps(data, indent=2))
        if 'result' in data:
            if data['result'] != 'success':
                raise TransmissionError('Query failed with result \"%s\".' % (data['result']))
        else:
            raise TransmissionError('Query failed without result.')

        results = {}
        if method == 'torrent-get':
            for item in data['arguments']['torrents']:
                results[item['id']] = Torrent(item)
                if self.protocol_version == 2 and 'peers' not in item:
                    self.protocol_version = 1
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
        elif method in ('port-test', 'blocklist-update'):
            results = data['arguments']
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
                    except ValueError:
                        pass
                if not addition:
                    # handle index ranges i.e. 5:10
                    match = re.match(u'^(\d+):(\d+)$', item)
                    if match:
                        try:
                            idx_from = int(match.group(1))
                            idx_to = int(match.group(2))
                            addition = range(idx_from, idx_to + 1)
                        except ValueError:
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

    @property
    def rpc_version(self):
        if self.protocol_version == None:
            if hasattr(self.session, 'rpc_version'):
                self.protocol_version = self.session.rpc_version
            elif hasattr(self.session, 'version'):
                self.protocol_version = 3
            else:
                self.protocol_version = 2
        return self.protocol_version

    def _rpc_version_warning(self, version):
        if self.rpc_version < version:
            logger.warning('Using feature not supported by server. RPC version for server %d, feature introduced in %d.' % (self.rpc_version, version))

    def add(self, data, timeout=None, **kwargs):
        """
        Add torrent to transfers list. Takes a base64 encoded .torrent file in data.
        Additional arguments are:

        ===================== ==== =============================================================
        Argument              RPC  Description                                                  
        ===================== ==== =============================================================
        ``bandwidthPriority`` 8 -  Priority for this transfer.                                  
        ``download_dir``      1 -  The directory where the downloaded contents will be saved in.
        ``filename``          1 -  A filepath or URL to a torrent file or a magnet link.        
        ``files_unwanted``    1 -  A list of file id's that shouldn't be downloaded.            
        ``files_wanted``      1 -  A list of file id's that should be downloaded.               
        ``metainfo``          1 -  The content of a torrent file, base64 encoded.               
        ``paused``            1 -  If True, does not start the transfer when added.             
        ``peer_limit``        1 -  Maximum number of peers allowed.                             
        ``priority_high``     1 -  A list of file id's that should have high priority.          
        ``priority_low``      1 -  A list of file id's that should have low priority.           
        ``priority_normal``   1 -  A list of file id's that should have normal priority.        
        ===================== ==== =============================================================
        """
        args = {}
        if data:
            args = {'metainfo': data}
        elif 'metainfo' not in kwargs and 'filename' not in kwargs:
            raise ValueError('No torrent data or torrent uri.')
        for key, value in kwargs.iteritems():
            argument = make_rpc_name(key)
            (arg, val) = argument_value_convert('torrent-add',
                                        argument, value, self.rpc_version)
            args[arg] = val
        return self._request('torrent-add', args, timeout=timeout)

    def add_url(self, torrent_url, **kwargs):
        """
        Add torrent to transfers list. Takes a url to a .torrent file.
        Additional arguments are:

        ===================== ==== =============================================================
        Argument              RPC  Description                                                  
        ===================== ==== =============================================================
        ``bandwidthPriority`` 8 -  Priority for this transfer.                                  
        ``download_dir``      1 -  The directory where the downloaded contents will be saved in.
        ``files_unwanted``    1 -  A list of file id's that shouldn't be downloaded.            
        ``files_wanted``      1 -  A list of file id's that should be downloaded.               
        ``paused``            1 -  If True, does not start the transfer when added.             
        ``peer_limit``        1 -  Maximum number of peers allowed.                             
        ``priority_high``     1 -  A list of file id's that should have high priority.          
        ``priority_low``      1 -  A list of file id's that should have low priority.           
        ``priority_normal``   1 -  A list of file id's that should have normal priority.        
        ===================== ==== =============================================================
        """
        torrent_file = None
        if os.path.exists(torrent_url):
            torrent_file = open(torrent_url, 'r')
        else:
            try:
                torrent_file = urllib2.urlopen(torrent_url)
            except urllib2.HTTPError:
                pass
            except urllib2.URLError:
                pass
            except httplib.BadStatusLine:
                pass
            except ValueError:
                pass

        if not torrent_file:
            raise TransmissionError('File does not exist.')
        warnings.warn('add_url has been deprecated, please use add or add_uri instead.', DeprecationWarning)
        torrent_data = base64.b64encode(torrent_file.read())
        return self.add(torrent_data, **kwargs)
    
    def add_uri(self, uri, **kwargs):
        """
        Add torrent to transfers list. Takes a uri to a torrent, supporting
        all uri's supported by Transmissions torrent-add 'filename'
        argument. Additional arguments are:

        ===================== ==== =============================================================
        Argument              RPC  Description                                                  
        ===================== ==== =============================================================
        ``bandwidthPriority`` 8 -  Priority for this transfer.                                  
        ``download_dir``      1 -  The directory where the downloaded contents will be saved in.
        ``files_unwanted``    1 -  A list of file id's that shouldn't be downloaded.            
        ``files_wanted``      1 -  A list of file id's that should be downloaded.               
        ``paused``            1 -  If True, does not start the transfer when added.             
        ``peer_limit``        1 -  Maximum number of peers allowed.                             
        ``priority_high``     1 -  A list of file id's that should have high priority.          
        ``priority_low``      1 -  A list of file id's that should have low priority.           
        ``priority_normal``   1 -  A list of file id's that should have normal priority.        
        ===================== ==== =============================================================
        """
        if uri == None:
            raise ValueError('add_uri requires a URI.')
        # there has been some problem with T's built in torrent fetcher,
        # use a python one instead
        parseduri = urlparse.urlparse(uri)
        torrent_data = None
        if parseduri.scheme in ['file', 'ftp', 'ftps', 'http', 'https']:
            torrent_file = urllib2.urlopen(uri)
            torrent_data = base64.b64encode(torrent_file.read())
        if torrent_data:
            return self.add(torrent_data, **kwargs)
        else:
            return self.add(None, filename=uri, **kwargs)
    
    def remove(self, ids, delete_data=False, timeout=None):
        """
        remove torrent(s) with provided id(s). Local data is removed if
        delete_data is True, otherwise not.
        """
        self._rpc_version_warning(3)
        self._request('torrent-remove',
                    {'delete-local-data':rpc_bool(delete_data)}, ids, True, timeout=timeout)

    def start(self, ids, timeout=None):
        """start torrent(s) with provided id(s)"""
        self._request('torrent-start', {}, ids, True, timeout=timeout)

    def stop(self, ids, timeout=None):
        """stop torrent(s) with provided id(s)"""
        self._request('torrent-stop', {}, ids, True, timeout=timeout)

    def verify(self, ids, timeout=None):
        """verify torrent(s) with provided id(s)"""
        self._request('torrent-verify', {}, ids, True, timeout=timeout)

    def reannounce(self, ids, timeout=None):
        """Reannounce torrent(s) with provided id(s)"""
        self._rpc_version_warning(5)
        self._request('torrent-reannounce', {}, ids, True, timeout=timeout)

    def info(self, ids=[], arguments={}, timeout=None):
        """Get detailed information for torrent(s) with provided id(s)."""
        if not arguments:
            arguments = self.torrent_get_arguments
        return self._request('torrent-get', {'fields': arguments}, ids, timeout=timeout)

    def get_files(self, ids=[], timeout=None):
        """
        Get list of files for provided torrent id(s).
        This function returns a dictonary for each requested torrent id holding
        the information about the files.
        """
        fields = ['id', 'name', 'hashString', 'files', 'priorities', 'wanted']
        request_result = self._request('torrent-get', {'fields': fields}, ids, timeout=timeout)
        result = {}
        for tid, torrent in request_result.iteritems():
            result[tid] = torrent.files()
        return result

    def set_files(self, items, timeout=None):
        """
        Set file properties. Takes a dictonary with similar contents as the
        result of get_files.
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
            for fid, file_desc in files.iteritems():
                if not isinstance(file_desc, dict):
                    continue
                if 'selected' in file_desc and file_desc['selected']:
                    wanted.append(fid)
                else:
                    unwanted.append(fid)
                if 'priority' in file_desc:
                    if file_desc['priority'] == 'high':
                        priority_high.append(fid)
                    elif file_desc['priority'] == 'normal':
                        priority_normal.append(fid)
                    elif file_desc['priority'] == 'low':
                        priority_low.append(fid)
            self.change([tid], files_wanted = wanted
                        , files_unwanted = unwanted
                        , priority_high = priority_high
                        , priority_normal = priority_normal
                        , priority_low = priority_low, timeout=timeout)

    def list(self, timeout=None):
        """list all torrents"""
        fields = ['id', 'hashString', 'name', 'sizeWhenDone', 'leftUntilDone'
            , 'eta', 'status', 'rateUpload', 'rateDownload', 'uploadedEver'
            , 'downloadedEver']
        return self._request('torrent-get', {'fields': fields}, timeout=timeout)

    def change(self, ids, timeout=None, **kwargs):
        """
        Change torrent parameters. This is the list of parameters that.
        """
        args = {}
        for key, value in kwargs.iteritems():
            argument = make_rpc_name(key)
            (arg, val) = argument_value_convert('torrent-set'
                                    , argument, value, self.rpc_version)
            args[arg] = val

        if len(args) > 0:
            self._request('torrent-set', args, ids, True, timeout=timeout)
        else:
            ValueError("No arguments to set")
    
    def move(self, ids, location, timeout=None):
        """Move torrent data to the new location."""
        self._rpc_version_warning(6)
        args = {'location': location, 'move': True}
        self._request('torrent-set-location', args, ids, True, timeout=timeout)
    
    def locate(self, ids, location, timeout=None):
        """Locate torrent data at the location."""
        self._rpc_version_warning(6)
        args = {'location': location, 'move': False}
        self._request('torrent-set-location', args, ids, True, timeout=timeout)
    
    def get_session(self, timeout=None):
        """Get session parameters"""
        self._request('session-get', timeout=timeout)
        return self.session

    def set_session(self, timeout=None, **kwargs):
        """Set session parameters"""
        args = {}
        for key, value in kwargs.iteritems():
            if key == 'encryption' and value not in ['required', 'preferred', 'tolerated']:
                raise ValueError('Invalid encryption value')
            argument = make_rpc_name(key)
            (arg, val) = argument_value_convert('session-set'
                                , argument, value, self.rpc_version)
            args[arg] = val
        if len(args) > 0:
            self._request('session-set', args, timeout=timeout)

    def blocklist_update(self, timeout=None):
        """Update block list. Returns the size of the block list."""
        self._rpc_version_warning(5)
        result = self._request('blocklist-update', timeout=timeout)
        if 'blocklist-size' in result:
            return result['blocklist-size']
        return None

    def port_test(self, timeout=None):
        """
        Tests to see if your incoming peer port is accessible from the
        outside world.
        """
        self._rpc_version_warning(5)
        result = self._request('port-test', timeout=timeout)
        if 'port-is-open' in result:
            return result['port-is-open']
        return None

    def session_stats(self, timeout=None):
        """Get session statistics"""
        self._request('session-stats', timeout=timeout)
        return self.session
