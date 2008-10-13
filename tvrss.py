import os.path, codecs

import sqlalchemy as sa
import sqlalchemy.orm as orm
import transmission
import yaml

import system

from model import metadata, Show, Episode, Quality
from feed import tvrss_parser, QUALITIES

_CONFIGURATION = '~/.config/tvrss/tvrss.conf'

def load_conf(path=None):
    config = {
        'database': '~/.config/tvrss/database.db',
    }
    if not path:
        path = _CONFIGURATION
    path = os.path.expanduser(path)
    try:
        conf = codecs.open(path, 'r', 'utf-8')
        config.update(yaml.safe_load(conf))
    except IOError:
        pass
    return config

def save_conf(config, path=None):
    if not path:
        path = _CONFIGURATION
    path = os.path.expanduser(path)
    system.ensure_path('/', path)
    conf = codecs.open(path, 'w', 'utf-8')
    yaml.safe_dump(config, conf, default_flow_style=False)

def initialize_database(session):
    metadata.create_all(session.get_bind())
    # fill quality table
    for name, score in QUALITIES.iteritems():
        session.add(Quality(unicode(name), score))
    session.commit()

def main():
    config = load_conf()
    
    path = os.path.expanduser(config['database'])
    engine = sa.create_engine('sqlite:///%s' % (path), echo=False)
    session = orm.sessionmaker(bind=engine)()
    if not os.path.exists(path):
        initialize_database(session)
    
    entries = tvrss_parser('http://tvrss.net/feed/unique/')
    
    tc = transmission.Client()
    
    for entry in entries:
        if 'Show Name' in entry:
            show = session.query(Show).get(entry['Show Name'])
            if not show:
                show = Show(entry['Show Name'])
                session.add(show)
            if not show.download:
                print('Ignore %s' % (show.name))
                continue
            quality = []
            group = u''
            season = None
            episode = None
            date = None
            if 'Season' and 'Episode' in entry:
                season = entry['Season']
                episode = entry['Episode']
            date = entry['Episode Date'] if 'Episode Date' in entry else None
            group = unicode(entry['Group']) if 'Group' in entry else None
            if 'Quality' in entry:
                quality = [session.query(Quality).get(q) for q in entry['Quality']]
            score = Quality.total_score(quality)
            if date:
                episodes = session.query(Episode).filter(Episode.show==show).filter(Episode.date==date)
            else:
                episodes = session.query(Episode).filter(Episode.show==show).filter(Episode.season==season).filter(Episode.episode==episode)        
            do_add = False
            for item in episodes:
                if item.torrent_hash and score <= item.total_score():
                    break
            else:
                torrent = tc.add_url(entry['Link']).itervalues().next()
                item = Episode(show, season=season, episode=episode, date=date, quality=quality, group=group, torrent_hash=torrent.hashString)
                session.add(item)
                print('Add: %s' % (item))
    session.commit()
    save_conf(config)

if __name__ == '__main__':
    main()