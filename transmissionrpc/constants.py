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

FIELDS = [
'activityDate',
'addedDate',
'announceResponse',
'announceURL',
'comment',
'corruptEver',
'creator',
'dateCreated',
'desiredAvailable',
'doneDate',
'downloaders',
'downloadLimit',
'downloadLimitMode',
'downloadedEver',
'error',
'errorString',
'eta',
'files',
'hashString',
'haveUnchecked',
'haveValid',
'id',
'isPrivate',
'lastAnnounceTime',
'lastScrapeTime',
'leechers',
'leftUntilDone',
'manualAnnounceTime',
'maxConnectedPeers',
'name',
'nextAnnounceTime',
'nextScrapeTime',
'peers',
'peersConnected',
'peersFrom',
'peersGettingFromUs',
'peersKnown',
'peersSendingToUs',
'pieceCount',
'pieceSize',
'priorities',
'rateDownload',
'rateUpload',
'recheckProgress',
'scrapeResponse',
'scrapeURL',
'seeders',
'sizeWhenDone',
'startDate',
'status',
'swarmSpeed',
'timesCompleted',
'totalSize',
'trackers',
'uploadLimit',
'uploadLimitMode',
'uploadRatio',
'uploadedEver',
'wanted',
'webseeds',
'webseedsSendingToUs',
]

TR_PRI_LOW    = -1
TR_PRI_NORMAL =  0
TR_PRI_HIGH   =  1

PRIORITY = mirror_dict({
        'low'    : TR_PRI_LOW,
        'normal' : TR_PRI_NORMAL,
        'high'   : TR_PRI_HIGH
})
