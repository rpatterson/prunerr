#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik@coldstar.net>

import time, datetime
import httplib
import simplejson
from transmission_constants import *

class TransmissionError(Exception):
    pass

def format_timedelta(delta):
    minutes, seconds = divmod(delta.seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return '%d %02d:%02d:%02d' % (delta.days, hours, minutes, seconds)

class Torrent(object):
    def __init__(self, fields):
        if 'id' not in fields:
            raise ValueError('Torrent requires an id')
        self.fields = fields
    
    def update(self, other):
        fields = None
        if isinstance(other, dict):
            fields = other
        elif isinstance(other, Torrent):
            fields = other.fields
        else:
            raise ValueError('Cannot update with supplied data')
        self.fields.update(fields)
    
    def __str__(self):
        s = '    id: %d\n    hash: %s\n    name: %s\n' % (self.fields['id'], self.fields['hashString'], self.fields['name'])
        try: # activity
            act = ''
            act += '\n  status: ' + str(self.status)
            act += '\ndownload: %.2f Kib/s' % self.rateDownload
            act += '\n  upload: %.2f Kib/s' % self.rateUpload
            act += '\n   ratio: %.2f' % self.ratio
            s += act + '\n'
        except KeyError:
            pass
        try: # history
            dates = ''
            dates += '\n  active: ' + str(self.date_active)
            dates += '\n   added: ' + str(self.date_added)
            dates += '\n started: ' + str(self.date_started)
            dates += '\n    done: ' + str(self.date_done)
            s += dates + '\n'
        except KeyError:
            pass
        return s
    
    def __getattr__(self, name):
        try:
            return self.fields[name]
        except KeyError, e:
            raise AttributeError('Not attribute %s' % name)
    
    @property
    def status(self):
        return flag_list(self.fields['status'], STATUS)[0]
    
    @property
    def progress(self):
        return 100.0 * (self.fields['sizeWhenDone'] - self.fields['leftUntilDone']) / float(self.fields['sizeWhenDone'])
    
    @property
    def ratio(self):
        return self.fields['uploadedEver'] / float(self.fields['downloadedEver'])
    
    @property
    def eta(self):
        eta = self.fields['eta']
        if eta >= 0:
            return datetime.timedelta(seconds=eta)
        else:
            ValueError('eta not valid')

    @property
    def date_active(self):
        return datetime.datetime.fromtimestamp(self.fields['activityDate'])

    @property
    def date_added(self):
        return datetime.datetime.fromtimestamp(self.fields['addedDate'])

    @property
    def date_started(self):
        return datetime.datetime.fromtimestamp(self.fields['startDate'])

    @property
    def date_done(self):
        return datetime.datetime.fromtimestamp(self.fields['doneDate'])
    
    def format_eta(self):
        eta = self.fields['eta']
        if eta == -1:
            return 'not available'
        elif eta == -2:
            return 'unknown'
        else:
            return format_timedelta(self.eta)

class TransmissionClient(object):
    def __init__(self, address=None, port=None, verbose=False):
        self._http_connection = httplib.HTTPConnection(address, port)
        self._sequence = 0
        self.verbose = verbose
        self.torrents = {}
    
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
        self._http_connection.request('POST', '/transmission/rpc', simplejson.dumps(query))
        response = self._http_connection.getresponse()
        if response.status != 200:
            raise httplib.HTTPException('Server responded with %d: \"%s\"' % (response.status, response.reason))
        http_data = response.read()
        elapsed = time.time() - start
        if self.verbose:
            print('http request took %.3f s' % (elapsed))
        
        data = simplejson.loads(http_data)

        if data['result'] != 'success':
            raise TransmissionError('Query failed with result \"%s\"' % data['result'])
        
        if 'arguments' in data:
            if 'torrents' in data['arguments']:
                for torrent in data['arguments']['torrents']:
                    if 'id' in torrent:
                        if torrent['id'] in self.torrents:
                            self.torrents.update(torrent)
                        else:
                            self.torrents[torrent['id']] = Torrent(torrent)
            elif 'torrent-added' in data['arguments']:
                torrent = data['arguments']['torrent-added']
                if torrent['id'] in self.torrents:
                    self.torrents.update(torrent)
                else:
                    self.torrents[torrent['id']] = Torrent(torrent)
        
        if self.verbose:
            print(simplejson.dumps(data, indent=2))
        
        return data
    
    def _format_ids(self, ids):
        """Take a list of things and make them valid torrent identifiers"""
        
        id_list = []
        for id in ids:
            # check if the id is either int or hex and convert int id
            try:
                id_list.append(int(id))
            except ValueError:
                try:
                    hash = int(id, 16)
                    id_list.append(str(id))
                except ValueError:
                    raise ValueError('Invalid torrent id, \"%s\"' % id)
        if len(id_list) == 0:
            raise ValueError('No valid ids')
        return id_list
    
    
    def add(self, data, target=None, start=False, peerlimit=None):
        """add torrent with provided base64 encoded .torrent"""
        
        args = {'metainfo': data, 'paused': 'false' if start else 'true'}
        if target:
            args['download-dir'] = target
        if peerlimit:
            args['peer-limit'] = peerlimit
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
    
    def list(self, fields=[], ids=None):
        """list torrent(s) with provided id(s)"""
        
        field_flag = 0
        for field in fields:
            if field in FIELDS:
                field_flag += FIELDS[field]
        if field_flag == 0:
            field_flag = TR_RPC_TORRENT_ACTIVITY | TR_RPC_TORRENT_ID | TR_RPC_TORRENT_HISTORY | TR_RPC_TORRENT_SIZE
        self._request('torrent-get', {'fields': field_flag})b

if __name__ == '__main__':
    tc = TransmissionClient('localhost', 9090)
    tc._request('torrent-get', {'fields': TR_RPC_TORRENT_ID | TR_RPC_TORRENT_ACTIVITY})
