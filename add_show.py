#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import sys, os.path, urllib

import feedparser
import sqlalchemy as sa
import sqlalchemy.orm as orm

from feed import tvrss_parser
import model

if __name__ == '__main__':
    exact = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'exactly':
            exact = True
            show_name = ' '.join(sys.argv[2:])
        else:
            show_name = ' '.join(sys.argv[1:])
    else:
        sys.exit(0)
    query = {'distribution_group': 'combined', 'show_name': show_name, 'mode': 'rss', 'show_name_exact': 'true' if exact else 'false'}
    url = 'http://tvrss.net/search/index.php?%s' % (urllib.urlencode(query))
    entries = tvrss_parser(url)
    shows = []
    for entry in entries:
        if 'Show Name' in entry and entry['Show Name'] not in shows:
            shows.append(entry['Show Name'])
    if len(shows) == 1:
        show_name = shows[0]
        path = os.path.expanduser('~/tvshows.db')
        session = orm.sessionmaker(bind=sa.create_engine('sqlite:///%s' % (path), echo=False))()
        show = session.query(model.Show).get(show_name)
        if show:
            show.download = True
        else:
            show = model.Show(show_name)
            show.download = True
            session.add(show)
        session.commit()
    else:
        print('Found no or multiple shows: %s' % (', '.join(shows)))
