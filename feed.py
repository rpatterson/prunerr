#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import feedparser

# http://feedparser.org/docs/

# feeds:
# http://www.mininova.org/rss.xml?user=EZTV
# http://tvrss.net/
# http://www.torrentleech.org/ <- invite only

#feed = feedparser.parse('http://tvrss.net/search/index.php?show_name=NCIS&show_name_exact=true&mode=rss')
feed = feedparser.parse('http://www.mininova.org/rss.xml?user=EZTV')

print(feed.feed.title)
print(feed.feed.subtitle)

for entry in feed.entries:
    for k, v in entry.iteritems():
        print('% 16s: %s' % (k, v))

