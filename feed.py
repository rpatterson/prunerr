#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import re, time, datetime, codecs, os.path
import feedparser, yaml
import transmission

tvrss_field_parse = re.compile('\s*([^:]+)\s*:\s*(.+)\s*')
QUALITIES = {
    'DSR'    : 1, # Digital Stream/Satellite Rip
    'DSRIP'  : 1, # same?
    'PDTV'   : 1, # Pure Digital Television
    'WS'     : 1, # Widescreen
    'PROPER' : 1, # Proper
    'HDTV'   : 2, # High Definition Television
    '720P'   : 3, # HDTV, 720 Progressive Lines
}

def tvrss_parser(url):
    entries = feedparser.parse(url).entries
    items = []
    for entry in entries:
        entry_date = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
        item = {'Entry Date': entry_date}
        if 'title' in entry:
            score = 0
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
                        if field not in QUALITIES:
                            print('Unknown quality: %s in %s' % (field, entry.title))
                        else:
                            score += QUALITIES[field]
            item['Quality Score'] = score
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
                    elif key in ['Episode', 'Season']:
                        item[key] = int(value)
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

if __name__ == '__main__':
    config = {'last-check': None}
    
    try:
        config_file = codecs.open(os.path.expanduser('~/.config/transmission-feed.conf'), 'r', 'utf-8')
        config.update(yaml.safe_load(config_file))
        config_file.close()
    except IOError:
        pass
    
    items = tvrss_parser('http://tvrss.net/feed/unique/')
    
    tr_client = transmission.Client()
    if config['last-check']:
        last_check = datetime.datetime.strptime(config['last-check'], '%Y-%m-%d %H:%M:%S')
    else:
        last_check = None
    
    for item in items:
        if not last_check or item['Entry Date'] > last_check:
            show = item['Entry Date'].strftime('%Y-%m-%d %H:%M:%S :')
            if 'Show Name' and 'Show Title' in item:
                show += item['Show Name'] + ' - ' + item['Show Title']
            elif 'Show Name' in item:
                show += item['Show Name']
            elif 'Show Title' in item:
                show += item['Show Title']
            show += ' : '
            if 'Season' and 'Episode' in item:
                show += str(item['Season']) + ' - ' + str(item['Episode'])
            elif 'Episode Date' in item:
                show += item['Episode Date'].strftime('%Y-%m-%d')    
            if 'Quality' in item:
                show += ' : ' + '|'.join(item['Quality'])
            if 'Quality Score' in item:
                show += ' : ' + str(item['Quality Score'])
            if 'Group' in item:
                show += ' : ' + item['Group']
            
            if 'Show Name' and 'Link' in item:
                shows = ['Numb3rs', 'Sanctuary', 'The Ex List', 'Life', 'Everybody Hates Chris', 'The Sarah Jane Adventures', 'Greys Anatomy', 'The Sarah Silverman Program', 'Pushing Daisies', 'Ugly Betty', 'My Name Is Earl', 'Sophie', 'Secret Diary Of A Call Girl', 'Eleventh Hour', 'Life on Mars US', 'Kath and Kim US', 'The Life and Times of Tim']
                if item['Show Name'] in shows:
                    try:
                        tr_client.add_url(item['Link'])
                        print('++ ' + show)
                    except transmission.TransmissionError:
                        pass
                else:
                    print('-- ' + show)
    
    config['last-check'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    config_file = codecs.open(os.path.expanduser('~/.config/transmission-feed.conf'), 'w', 'utf-8')
    yaml.safe_dump(config, config_file, default_flow_style=False)
    config_file.close()