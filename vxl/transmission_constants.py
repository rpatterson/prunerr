#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik@coldstar.net>

def mirror_dict(d):
    d.update(dict((v, k) for k, v in d.iteritems()))
    return d

def flag_list(flag, flags):
    result = []
    for k, v in flags.iteritems():
        if isinstance(k, int):
            if flag & k == k:
                result.append(v)
    return result

TR_STATUS_CHECK_WAIT   = (1<<0)
TR_STATUS_CHECK        = (1<<1)
TR_STATUS_DOWNLOAD     = (1<<2)
TR_STATUS_SEED         = (1<<3)
TR_STATUS_STOPPED      = (1<<4)

STATUS = mirror_dict({
    'check_wait' : TR_STATUS_CHECK_WAIT,
    'check'      : TR_STATUS_CHECK,
    'download'   : TR_STATUS_DOWNLOAD,
    'seed'       : TR_STATUS_SEED,
    'stopped'    : TR_STATUS_STOPPED,
})


TR_RPC_TORRENT_ACTIVITY        = (1<<0)
TR_RPC_TORRENT_ANNOUNCE        = (1<<1)
TR_RPC_TORRENT_ERROR           = (1<<2)
TR_RPC_TORRENT_FILES           = (1<<3)
TR_RPC_TORRENT_HISTORY         = (1<<4)
TR_RPC_TORRENT_ID              = (1<<5)
TR_RPC_TORRENT_INFO            = (1<<6)
TR_RPC_TORRENT_LIMITS          = (1<<7)
TR_RPC_TORRENT_PEERS           = (1<<8)
TR_RPC_TORRENT_PRIORITIES      = (1<<9)
TR_RPC_TORRENT_SCRAPE          = (1<<10)
TR_RPC_TORRENT_SIZE            = (1<<11)
TR_RPC_TORRENT_TRACKER_STATS   = (1<<12)
TR_RPC_TORRENT_TRACKERS        = (1<<13)
TR_RPC_TORRENT_WEBSEEDS        = (1<<14)

FIELDS = mirror_dict({
    'activity'      : TR_RPC_TORRENT_ACTIVITY,
    'announce'      : TR_RPC_TORRENT_ANNOUNCE,
    'error'         : TR_RPC_TORRENT_ERROR,
    'files'         : TR_RPC_TORRENT_FILES,
    'history'       : TR_RPC_TORRENT_HISTORY,
    'id'            : TR_RPC_TORRENT_ID,
    'info'          : TR_RPC_TORRENT_INFO,
    'limits'        : TR_RPC_TORRENT_LIMITS,
    'peers'         : TR_RPC_TORRENT_PEERS,
    'prioreties'    : TR_RPC_TORRENT_PRIORITIES,
    'scrape'        : TR_RPC_TORRENT_SCRAPE,
    'size'          : TR_RPC_TORRENT_SIZE,
    'tracker-stats' : TR_RPC_TORRENT_TRACKER_STATS,
    'trackers'      : TR_RPC_TORRENT_TRACKERS,
    'webseeds'      : TR_RPC_TORRENT_WEBSEEDS,
})