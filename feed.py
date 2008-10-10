#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import re, datetime
import feedparser
import transmission

tvrss_field_parse = re.compile('\s*([^:]+)\s*:\s*(.+)\s*')
quality_identifiers = ['DSR', 'DSRIP', 'PDTV', 'HDTV', 'WS', '720P']

def tvrss_parser(entries):
    items = []
    for entry in entries:
        #print(entry)
        item = {}
        if 'title' in entry:
            start = entry.title.rfind('[')
            end = entry.title.rfind(']')
            if start and end >= 0:
                fields = entry.title[start+1:end].split('-')
                if len(fields) == 0:
                    print(fields)
                else:
                    item['Group'] = fields[-1].strip()
                    item['Quality'] = [field.strip() for field in fields[:-1]]
                    for field in item['Quality']:
                        if field not in quality_identifiers:
                            print('Unknown quality: ' + field)
            #item['Title'] = entry.title
        if 'summary' and 'link' in entry:
            fields = entry.summary.split(';')
            item['Link'] = entry.link
            for field in fields:
                match = tvrss_field_parse.match(field)
                if match:
                    (key, value) = match.groups()
                    if key == 'Episode Date':
                        item[key] = datetime.datetime.strptime(value, '%Y-%m-%d')
                    elif value != 'n/a':
                        item[key] = value
                else:
                    print('no match: %s' % (field))
            items.append(item)
    return items

# http://feedparser.org/docs/

# feeds:
# http://www.mininova.org/rss.xml?user=EZTV
# http://tvrss.net/

feed = feedparser.parse('http://tvrss.net/feed/unique/')

print(feed.feed.title)
print(feed.feed.subtitle)
print('')

items = tvrss_parser(feed.entries)

tr_client = transmission.Client()

for item in items:
    show = ''
    if 'Show Name' and 'Show Title' in item:
        show = item['Show Name'] + ' - ' + item['Show Title']
    elif 'Show Name' in item:
        show = item['Show Name']
    elif 'Show Title' in item:
        show = item['Show Title']
    show += ' : '
    if 'Season' and 'Episode' in item:
        show += item['Season'] + ' - ' + item['Episode']
    elif 'Episode Date' in item:
        show += item['Episode Date'].strftime('%Y-%m-%d')
    if 'Quality' in item:
        show += ' : ' + '|'.join(item['Quality'])
    if 'Group' in item:
        show += ' : ' + item['Group']
    print(show)
    
    
    if 'Show Name' and 'Link' in item:
        if item['Show Name'] == 'Pushing Daisies':
            tr_client.add_url(item['Link'])
