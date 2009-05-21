# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

def mirror_dict(d):
    d.update(dict((v, k) for k, v in d.iteritems()))
    return d

DEFAULT_PORT = 9091

TR_STATUS_CHECK_WAIT   = (1<<0)
TR_STATUS_CHECK        = (1<<1)
TR_STATUS_DOWNLOAD     = (1<<2)
TR_STATUS_SEED         = (1<<3)
TR_STATUS_STOPPED      = (1<<4)

STATUS = mirror_dict({
    'check pending' : TR_STATUS_CHECK_WAIT,
    'checking'      : TR_STATUS_CHECK,
    'downloading'   : TR_STATUS_DOWNLOAD,
    'seeding'       : TR_STATUS_SEED,
    'stopped'       : TR_STATUS_STOPPED,
})

TR_PRI_LOW    = -1
TR_PRI_NORMAL =  0
TR_PRI_HIGH   =  1

PRIORITY = mirror_dict({
        'low'    : TR_PRI_LOW,
        'normal' : TR_PRI_NORMAL,
        'high'   : TR_PRI_HIGH
})

torrent_args = {
    'activityDate':             ('number', 1, None, 'r'),
    'addedDate':                ('number', 1, None, 'r'),
    'announceResponse':         ('string', 1, None, 'r'),
    'announceURL':              ('string', 1, None, 'r'),
    'bandwidthPriority':        ('number', 5, None, 'rw'),
    'comment':                  ('string', 1, None, 'r'),
    'corruptEver':              ('number', 1, None, 'r'),
    'creator':                  ('string', 1, None, 'r'),
    'dateCreated':              ('number', 1, None, 'r'),
    'desiredAvailable':         ('number', 1, None, 'r'),
    'doneDate':                 ('number', 1, None, 'r'),
    'download-dir':             ('string', 0, None, 'a'),
    'downloadDir':              ('string', 4, None, 'r'),
    'downloadedEver':           ('number', 1, None, 'r'),
    'downloaders':              ('number', 3, None, 'r'),
    'downloadLimit':            ('number', 1, None, 'rw'),
    'downloadLimited':          ('boolean', 5, None, 'rw'),
    'downloadLimitMode':        ('number', 1, 5, 'rw'),
    'error':                    ('number', 1, None, 'r'),
    'errorString':              ('number', 1, None, 'r'),
    'eta':                      ('number', 1, None, 'r'),
    'filename':                 ('string', 1, None, 'a'),
    'files':                    ('array', 1, None, 'r'),
    'files-wanted':             ('array', 1, None, 'rwa'),
    'files-unwanted':           ('array', 1, None, 'rwa'),
    'fileStats':                ('array', 5, None, 'r'),
    'hashString':               ('string', 1, None, 'r'),
    'haveUnchecked':            ('number', 1, None, 'r'),
    'haveValid':                ('number', 1, None, 'r'),
    'honorsSessionLimits':      ('boolean', 5, None, 'rw'),
    'id':                       ('number', 1, None, 'r'),
    'ids':                      ('array', 1, None, 'w'),
    'isPrivate':                ('boolean', 1, None, 'r'),
    'lastAnnounceTime':         ('number', 1, None, 'r'),
    'lastScrapeTime':           ('number', 1, None, 'r'),
    'leechers':                 ('number', 1, None, 'r'),
    'leftUntilDone':            ('number', 1, None, 'r'),
    'manualAnnounceTime':       ('number', 1, None, 'r'),
    'maxConnectedPeers':        ('number', 1, None, 'r'),
    'metainfo':                 ('string', 1, None, 'a'),
    'name':                     ('string', 1, None, 'r'),
    'nextAnnounceTime':         ('number', 1, None, 'r'),
    'nextScrapeTime':           ('number', 1, None, 'r'),
    'paused':                   ('boolean', 1, None, 'a'),
    'peer-limit':               ('number', 1, None, 'rwa'),
    'peers':                    ('array', 2, None, 'r'),
    'peersConnected':           ('number', 1, None, 'r'),
    'peersFrom':                ('object', 1, None, 'r'),
    'peersGettingFromUs':       ('number', 1, None, 'r'),
    'peersKnown':               ('number', 1, None, 'r'),
    'peersSendingToUs':         ('number', 1, None, 'r'),
    'percentDone':              ('double', 5, None, 'r'),
    'pieces':                   ('string', 5, None, 'r'),
    'pieceCount':               ('number', 1, None, 'r'),
    'pieceSize':                ('number', 1, None, 'r'),
    'priorities':               ('array', 1, None, 'r'),
    'priority-high':            ('array', 1, None, 'wa'),
    'priority-low':             ('array', 1, None, 'wa'),
    'priority-normal':          ('array', 1, None, 'wa'),
    'rateDownload':             ('number', 1, None, 'r'),
    'rateUpload':               ('number', 1, None, 'r'),
    'recheckProgress':          ('double', 1, None, 'r'),
    'scrapeResponse':           ('string', 1, None, 'r'),
    'scrapeURL':                ('string', 1, None, 'r'),
    'seeders':                  ('number', 1, None, 'r'),
    'seedRatioLimit':           ('double', 5, None, 'rw'),
    'seedRatioMode':            ('number', 5, None, 'rw'),
    'sizeWhenDone':             ('number', 1, None, 'r'),
    'speed-limit-down':         ('number', 1, 5, 'w', 'downloadLimit'),
    'speed-limit-down-enabled': ('boolean', 1, 5, 'w', 'downloadLimited'),
    'speed-limit-up':           ('number', 1, 5, 'w', 'uploadLimit'),
    'speed-limit-up-enabled':   ('boolean', 1, 5, 'w', 'uploadLimited'),
    'startDate':                ('number', 1, None, 'r'),
    'status':                   ('number', 1, None, 'r'),
    'swarmSpeed':               ('number', 1, None, 'r'),
    'timesCompleted':           ('number', 1, None, 'r'),
    'trackers':                 ('array', 1, None, 'r'),
    'totalSize':                ('number', 1, None, 'r'),
    'torrentFile':              ('string', 5, None, 'r'),
    'uploadedEver':             ('number', 1, None, 'r'),
    'uploadLimit':              ('number', 1, None, 'rw'),
    'uploadLimitMode':          ('number', 1, 5, 'rw'),
    'uploadLimited':            ('boolean', 5, None, 'rw'),
    'uploadRatio':              ('double', 1, None, 'r'),
    'wanted':                   ('array', 1, None, 'r'),
    'webseeds':                 ('array', 1, None, 'r'),
    'webseedsSendingToUs':      ('number', 1, None, 'r'),
}

# Arguments for session-set
# The set describes:
#   (<type>, <rpc version introduced>, <rpc version removed>, <read/write>)
session_args = {
    "alt-speed-down":            ('number', 5, None, 'rw'),
    "alt-speed-enabled":         ('boolean', 5, None, 'rw'),
    "alt-speed-time-begin":      ('number', 5, None, 'rw'),
    "alt-speed-time-enabled":    ('boolean', 5, None, 'rw'),
    "alt-speed-time-end":        ('number', 5, None, 'rw'),
    "alt-speed-time-day":        ('number', 5, None, 'rw'),
    "alt-speed-up":              ('number', 5, None, 'rw'),
    "blocklist-enabled":         ('boolean', 5, None, 'rw'),
    "blocklist-size":            ('number', 5, None, 'r'),
    "encryption":                ('string', 1, None, 'rw'),
    "download-dir":              ('string', 1, None, 'rw'),
    "peer-limit":                ('number', 1, 5, 'rw'),
    "peer-limit-global":         ('number', 5, None, 'rw'),
    "peer-limit-per-torrent":    ('number', 5, None, 'rw'),
    "pex-allowed":               ('boolean', 1, 5, 'rw'),
    "pex-enabled":               ('boolean', 5, None, 'rw'),
    "port":                      ('number', 1, 5, 'rw'),
    "peer-port":                 ('number', 5, None, 'rw'),
    "peer-port-random-on-start": ('boolean', 5, None, 'rw'),
    "port-forwarding-enabled":   ('boolean', 1, None, 'rw'),
    "rpc-version":               ('number', 4, None, 'r'),
    "rpc-version-minimum":       ('number', 4, None, 'r'),
    "seedRatioLimit":            ('double', 5, None, 'rw'),
    "seedRatioLimited":          ('boolean', 5, None, 'rw'),
    "speed-limit-down":          ('number', 1, None, 'rw'),
    "speed-limit-down-enabled":  ('boolean', 1, None, 'rw'),
    "speed-limit-up":            ('number', 1, None, 'rw'),
    "speed-limit-up-enabled":    ('boolean', 1, None, 'rw'),
    "version":                   ('string', 3, None, 'r'),
}
