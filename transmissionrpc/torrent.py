# -*- coding: utf-8 -*-
# Copyright (c) 2008-2010 Erik Svensson <erik.public@gmail.com>
# Licensed under the MIT license.

import datetime

from transmissionrpc.constants import STATUS, PRIORITY
from transmissionrpc.utils import format_timedelta

class Torrent(object):
    """
    Torrent is a class holding the data raceived from Transmission regarding a bittorrent transfer.
    All fetched torrent fields are accessable through this class using attributes.
    This class has a few convenience properties using the torrent data.
    """

    def __init__(self, client, fields):
        if 'id' not in fields:
            raise ValueError('Torrent requires an id')
        self.fields = {}
        self.update(fields)
        self.client = client

    def __repr__(self):
        return '<Torrent %d \"%s\">' % (self.fields['id'], self.fields['name'])

    def __str__(self):
        return 'torrent %s' % self.fields['name']
    
    def __copy__(self):
        return Torrent(self.client, self.fields)

    def update(self, other):
        """Update the torrent data from a Transmission arguments dictinary"""
        fields = None
        if isinstance(other, dict):
            fields = other
        elif isinstance(other, Torrent):
            fields = other.fields
        else:
            raise ValueError('Cannot update with supplied data')
        for key, value in fields.iteritems():
            self.fields[key.replace('-', '_')] = value

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
