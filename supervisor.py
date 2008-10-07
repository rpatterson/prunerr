#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import sys, os, os.path, time, codecs, logging
from optparse import OptionParser
import yaml
import transmission
import procs

__author__    = u'Erik Svensson <erik.public@gmail.com>'
__version__   = u'0.1'
__copyright__ = u'Copyright (c) 2008 Erik Svensson'
__license__   = u'MIT'

DEFAULT_CONFIGURATION_DIR = '~/.config/supervisor.conf'

class Supervisor(object):
    def __init__(self, config):
        self.config = config
        self.tc = transmission.Client(port=self.config['transmission-port'])
        try:
            session = self.tc.get_session()
        except transmission.TransmissionError, e:
            logging.error('Session query failed: %s port: %r.' % (e, self.config['transmission-port']))
            raise
        self.download_dir = os.path.abspath(os.path.expanduser(session.download_dir))
        self.finished_dir = os.path.abspath(os.path.expanduser(self.config['finished-dir']))
    
    def run(self):
        while(True):
            t = time.clock()
            try:
                torrents = self.tc.info()
            except transmission.TransmissionError, e:
                logging.error('Info query failed: %s port %r' % (e, self.config['transmission-port']))
                raise
            for tid, torrent in torrents.iteritems():
                if torrent.status == 'seeding' and torrent.ratio >= self.config['ratio-limit']:
                    action = getattr(self, 'action_' + self.config['ratio-action'])
                    try:
                        action(torrent)
                    except:
                        logging.error('Action \"%s\" failed with torrent %s' % (self.config['ratio-action'], torrent.name))
            elapsed = time.clock() - t;
            time.sleep(self.config['query-interval'] - elapsed) # sleep some
    
    def action_move(self, torrent):
        files = torrent.files()
        self.tc.remove(torrent.id)
        for fid, file in files.iteritems():
            path_from = os.path.join(self.download_dir, file['name'])
            path_to = os.path.join(self.finished_dir, file['name'])
            os.renames(path_from, path_to)
    
    def action_stop(self, torrent):
        self.tc.stop(torrent.id)

def load_config(path):
    config = {
        'transmission-port': transmission.DEFAULT_PORT,
        'transmission-download-dir': '~/downloads/unfinished/',
        'transmission-user': '',
        'transmission-password': '',
        'transmission-acl': '+127.0.0.1',
        'transmission-use-blocklist': False,
        'query-interval': 30.0,
        'finished-dir': '~/downloads/',
        'ratio-limit': 1.0,
        'ratio-action': 'stop',
        'log-dir': '/tmp'}
    if not path:
        path = DEFAULT_CONFIGURATION_DIR
    path = os.path.expanduser(path)
    try:
        f = codecs.open(path, 'r', 'utf-8')
    except IOError:
        pass
    else:
        config.update(yaml.safe_load(f))
        f.close()
    return (path, config)

def save_config(config, path = None):
    if not path:
        path = DEFAULT_CONFIGURATION_DIR
    path = os.path.expanduser(path)
    try:
        f = codecs.open(path, 'w', 'utf-8')
    except IOError:
        raise ValueError('Invalid path')
    else:
        yaml.dump(config, f, default_flow_style=False)
        f.close()

def ensure_dir(base, path):
    if not os.path.exists(base):
        raise ValueError()
    dirs = []
    while not os.path.exists(os.path.join(base, path)):
        (path, name) = os.path.split(path)
        dirs.append(name)
    
    path = base
    for name in dirs.reverse():
        path = os.path.join(path, name)
        os.mkdir(path)

def ensure_path(base, path):
    ensure_dir(base, os.path.dirname(path))

def main():
    #enumerate actions
    actions = []
    for attr in dir(Supervisor):
        if attr[:7] == 'action_':
            actions.append(attr[7:])
    actions_string = ', '.join([a for a in actions])
    
    # parse args
    parser = OptionParser(version='Supervisor %s' % (__version__), usage='%prog [options]')
    parser.add_option('-c', '--config', type='string', dest='config', help='Configuration file.', metavar='<file>')
    parser.add_option('-p', '--port', type='int', dest='port', help='Transmission service port.', metavar="<port>")
    parser.add_option('-i', '--interval', type='float', dest='interval', help='Transmission query interval.', metavar="<interval>")
    parser.add_option('-r', '--ratio', type='float', dest='ratio', help='At which ration to stop seeding and take action.', metavar="<ratio>")
    parser.add_option('-a', '--action', type='string', dest='action', help='The action to take when seeding is done. Available actions: %s' % (actions_string), metavar="<action>")
    parser.add_option('-f', '--finished', type='string', dest='finished', help='Directory to move finished files to.', metavar="<dir>")
    parser.add_option('-l', '--logdir', type='string', dest='logdir', help='Directory to save logs in.', metavar="<dir>")
    parser.add_option('-u', '--user', type='string', dest='username', help='Username used when connecting to transmission..', metavar="<user>")
    parser.add_option('-v', '--password', type='string', dest='password', help='Password used when connecting to transmission..', metavar="<password>")
    (opts, args) = parser.parse_args()
    
    (config_path, config) = load_config(opts.config)
    
    if opts.logdir:
        config['log-dir'] = opts.logdir
    log_path = os.path.join(os.path.expanduser(config['log-dir']), 'supervisor.log')
    logging.basicConfig(level=logging.INFO, filename=log_path, format='%(asctime)s %(levelname)s %(message)s')
    
    if opts.port:
        config['transmission-port'] = opts.port
    if opts.interval:
        config['query-interval'] = opts.interval
    if opts.ratio:
        config['ratio-limit'] = opts.ratio
    if opts.action:
        config['ratio-action'] = opts.action
    if opts.finished:
        config['finished-dir'] = opts.finished
    if opts.user:
        config['transmission-user'] = opts.user
    if opts.password:
        config['transmission-password'] = opts.password
    
    transmission_pid = 0
    for process in procs.process_list():
        if process[1][-19:] == 'transmission-daemon':
            transmission_pid = process[0]
    if transmission_pid != 0:
        print('transmission-daemon at %d' % (transmission_pid))
    else:
        print('No transmission-daemon?')
        logging.warning('No transmission-daemon?')
        sys.exit()
    
    s = Supervisor(config)
    try:
        s.run()
    except KeyboardInterrupt:
        save_config(s.config, opts.config)

if __name__ == '__main__':
    main()
