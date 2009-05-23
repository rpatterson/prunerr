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

TR_RATIOLIMIT_GLOBAL    = 0 # follow the global settings
TR_RATIOLIMIT_SINGLE    = 1 # override the global settings, seeding until a certain ratio
TR_RATIOLIMIT_UNLIMITED = 2 # override the global settings, seeding regardless of ratio

RATIO_LIMIT = mirror_dict({
    'global'    : TR_RATIOLIMIT_GLOBAL,
    'single'    : TR_RATIOLIMIT_SINGLE,
    'unlimeted' : TR_RATIOLIMIT_UNLIMITED
})

TORRENT_ARGS = {
    'get' : {
        'activityDate':             ('number', 1, None),
        'addedDate':                ('number', 1, None),
        'announceResponse':         ('string', 1, None),
        'announceURL':              ('string', 1, None),
        'bandwidthPriority':        ('number', 5, None),
        'comment':                  ('string', 1, None),
        'corruptEver':              ('number', 1, None),
        'creator':                  ('string', 1, None),
        'dateCreated':              ('number', 1, None),
        'desiredAvailable':         ('number', 1, None),
        'doneDate':                 ('number', 1, None),
        'downloadDir':              ('string', 4, None),
        'downloadedEver':           ('number', 1, None),
        'downloaders':              ('number', 4, None),
        'downloadLimit':            ('number', 1, None),
        'downloadLimited':          ('boolean', 5, None),
        'downloadLimitMode':        ('number', 1, 5),
        'error':                    ('number', 1, None),
        'errorString':              ('number', 1, None),
        'eta':                      ('number', 1, None),
        'files':                    ('array', 1, None),
        'fileStats':                ('array', 5, None),
        'hashString':               ('string', 1, None),
        'haveUnchecked':            ('number', 1, None),
        'haveValid':                ('number', 1, None),
        'honorsSessionLimits':      ('boolean', 5, None),
        'id':                       ('number', 1, None),
        'isPrivate':                ('boolean', 1, None),
        'lastAnnounceTime':         ('number', 1, None),
        'lastScrapeTime':           ('number', 1, None),
        'leechers':                 ('number', 1, None),
        'leftUntilDone':            ('number', 1, None),
        'manualAnnounceTime':       ('number', 1, None),
        'maxConnectedPeers':        ('number', 1, None),
        'name':                     ('string', 1, None),
        'nextAnnounceTime':         ('number', 1, None),
        'nextScrapeTime':           ('number', 1, None),
        'peer-limit':               ('number', 5, None),
        'peers':                    ('array', 2, None),
        'peersConnected':           ('number', 1, None),
        'peersFrom':                ('object', 1, None),
        'peersGettingFromUs':       ('number', 1, None),
        'peersKnown':               ('number', 1, None),
        'peersSendingToUs':         ('number', 1, None),
        'percentDone':              ('double', 5, None),
        'pieces':                   ('string', 5, None),
        'pieceCount':               ('number', 1, None),
        'pieceSize':                ('number', 1, None),
        'priorities':               ('array', 1, None),
        'rateDownload':             ('number', 1, None),
        'rateUpload':               ('number', 1, None),
        'recheckProgress':          ('double', 1, None),
        'scrapeResponse':           ('string', 1, None),
        'scrapeURL':                ('string', 1, None),
        'seeders':                  ('number', 1, None),
        'seedRatioLimit':           ('double', 5, None),
        'seedRatioMode':            ('number', 5, None),
        'sizeWhenDone':             ('number', 1, None),
        'startDate':                ('number', 1, None),
        'status':                   ('number', 1, None),
        'swarmSpeed':               ('number', 1, None),
        'timesCompleted':           ('number', 1, None),
        'trackers':                 ('array', 1, None),
        'totalSize':                ('number', 1, None),
        'torrentFile':              ('string', 5, None),
        'uploadedEver':             ('number', 1, None),
        'uploadLimit':              ('number', 1, None),
        'uploadLimitMode':          ('number', 1, 5),
        'uploadLimited':            ('boolean', 5, None),
        'uploadRatio':              ('double', 1, None),
        'wanted':                   ('array', 1, None),
        'webseeds':                 ('array', 1, None),
        'webseedsSendingToUs':      ('number', 1, None),
    },
    'set': {
        'bandwidthPriority':        ('number', 5, None),
        'downloadLimit':            ('number', 5, None),
        'downloadLimited':          ('boolean', 5, None),
        'files-wanted':             ('array', 1, None),
        'files-unwanted':           ('array', 1, None),
        'honorsSessionLimits':      ('boolean', 5, None),
        'ids':                      ('array', 1, None),
        'peer-limit':               ('number', 1, None),
        'priority-high':            ('array', 1, None),
        'priority-low':             ('array', 1, None),
        'priority-normal':          ('array', 1, None),
        'seedRatioLimit':           ('double', 5, None),
        'seedRatioMode':            ('number', 5, None),
        'speed-limit-down':         ('number', 1, 5,),
        'speed-limit-down-enabled': ('boolean', 1, 5,),
        'speed-limit-up':           ('number', 1, 5,),
        'speed-limit-up-enabled':   ('boolean', 1, 5,),
        'uploadLimit':              ('number', 5, None),
        'uploadLimited':            ('boolean', 5, None),
    },
    'add': {
        'download-dir':             ('string', 1, None),
        'filename':                 ('string', 1, None),
        'files-wanted':             ('array', 1, None),
        'files-unwanted':           ('array', 1, None),
        'metainfo':                 ('string', 1, None),
        'paused':                   ('boolean', 1, None),
        'peer-limit':               ('number', 1, None),
        'priority-high':            ('array', 1, None),
        'priority-low':             ('array', 1, None),
        'priority-normal':          ('array', 1, None),
    }
}

# Arguments for session-set
# The set describes:
#   (<type>, <rpc version introduced>, <rpc version removed>, <read/write>)
SESSION_ARGS = {
    'get': {
        "alt-speed-down":            ('number', 5, None),
        "alt-speed-enabled":         ('boolean', 5, None),
        "alt-speed-time-begin":      ('number', 5, None),
        "alt-speed-time-enabled":    ('boolean', 5, None),
        "alt-speed-time-end":        ('number', 5, None),
        "alt-speed-time-day":        ('number', 5, None),
        "alt-speed-up":              ('number', 5, None),
        "blocklist-enabled":         ('boolean', 5, None),
        "blocklist-size":            ('number', 5, None),
        "encryption":                ('string', 1, None),
        "download-dir":              ('string', 1, None),
        "peer-limit":                ('number', 1, 5),
        "peer-limit-global":         ('number', 5, None),
        "peer-limit-per-torrent":    ('number', 5, None),
        "pex-allowed":               ('boolean', 1, 5),
        "pex-enabled":               ('boolean', 5, None),
        "port":                      ('number', 1, 5),
        "peer-port":                 ('number', 5, None),
        "peer-port-random-on-start": ('boolean', 5, None),
        "port-forwarding-enabled":   ('boolean', 1, None),
        "rpc-version":               ('number', 4, None),
        "rpc-version-minimum":       ('number', 4, None),
        "seedRatioLimit":            ('double', 5, None),
        "seedRatioLimited":          ('boolean', 5, None),
        "speed-limit-down":          ('number', 1, None),
        "speed-limit-down-enabled":  ('boolean', 1, None),
        "speed-limit-up":            ('number', 1, None),
        "speed-limit-up-enabled":    ('boolean', 1, None),
        "version":                   ('string', 3, None),
    },
    'set': {
        "alt-speed-down":            ('number', 5, None),
        "alt-speed-enabled":         ('boolean', 5, None),
        "alt-speed-time-begin":      ('number', 5, None),
        "alt-speed-time-enabled":    ('boolean', 5, None),
        "alt-speed-time-end":        ('number', 5, None),
        "alt-speed-time-day":        ('number', 5, None),
        "alt-speed-up":              ('number', 5, None),
        "blocklist-enabled":         ('boolean', 5, None),
        "blocklist-size":            ('number', 5, None),
        "encryption":                ('string', 1, None),
        "download-dir":              ('string', 1, None),
        "peer-limit":                ('number', 1, 5),
        "peer-limit-global":         ('number', 5, None),
        "peer-limit-per-torrent":    ('number', 5, None),
        "pex-allowed":               ('boolean', 1, 5),
        "pex-enabled":               ('boolean', 5, None),
        "port":                      ('number', 1, 5),
        "peer-port":                 ('number', 5, None),
        "peer-port-random-on-start": ('boolean', 5, None),
        "port-forwarding-enabled":   ('boolean', 1, None),
        "seedRatioLimit":            ('double', 5, None),
        "seedRatioLimited":          ('boolean', 5, None),
        "speed-limit-down":          ('number', 1, None),
        "speed-limit-down-enabled":  ('boolean', 1, None),
        "speed-limit-up":            ('number', 1, None),
        "speed-limit-up-enabled":    ('boolean', 1, None),
    },
}
