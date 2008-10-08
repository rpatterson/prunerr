#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import sys, os, os.path, time, codecs, logging
from optparse import OptionParser
import yaml
import transmission, system

__author__    = u'Erik Svensson <erik.public@gmail.com>'
__version__   = u'0.1'
__copyright__ = u'Copyright (c) 2008 Erik Svensson'
__license__   = u'MIT'

SUPERVISOR_CONFIGURATION_DIR = '~/.config/supervisor/supervisor.conf'

class Supervisor(object):
    def __init__(self, config, user=None, password=None, verbose=False):
        self.config = config
        self.client = transmission.Client(port=self.config['transmission-port'], user=user, password=password, verbose=verbose)
        try:
            session = self.client.get_session()
        except transmission.TransmissionError, exception:
            logging.error('Session query failed: %s port: %r.' % (exception, self.config['transmission-port']))
            raise
        self.download_dir = os.path.abspath(os.path.expanduser(session.download_dir))
        self.finished_dir = os.path.abspath(os.path.expanduser(self.config['finished-dir']))
    
    def run(self):
        while(True):
            timer = time.clock()
            try:
                torrents = self.client.info()
            except transmission.TransmissionError, exception:
                logging.error('Info query failed: %s port %r' % (exception, self.config['transmission-port']))
                raise
            for torrent in torrents.itervalues():
                if torrent.status == 'seeding' and torrent.ratio >= self.config['ratio-limit']:
                    action = getattr(self, 'action_' + self.config['ratio-action'])
                    try:
                        action(torrent)
                    except:
                        logging.warning('Action \"%s\" failed with torrent %s' % (self.config['ratio-action'], torrent.name))
            time.sleep(self.config['query-interval'] - (time.clock() - timer)) # sleep some
    
    def action_move(self, torrent):
        files = torrent.files()
        self.client.remove(torrent.id)
        for torrent_file in files.itervalues():
            path_from = os.path.join(self.download_dir, torrent_file['name'])
            path_to = os.path.join(self.finished_dir, torrent_file['name'])
            os.renames(path_from, path_to)
    
    def action_stop(self, torrent):
        self.client.stop(torrent.id)

def load_config(path):
    config = {
        'transmission-port': transmission.DEFAULT_PORT,
        'query-interval': 30.0,
        'finished-dir': '~/downloads/',
        'ratio-limit': 1.0,
        'ratio-action': 'stop',
        'log-dir': '/tmp'}
    if not path:
        path = SUPERVISOR_CONFIGURATION_DIR
    path = os.path.expanduser(path)
    try:
        config_file = codecs.open(path, 'r', 'utf-8')
    except IOError:
        pass
    else:
        config.update(yaml.safe_load(config_file))
        config_file.close()
    return config

def save_config(config, path = None):
    if not path:
        path = SUPERVISOR_CONFIGURATION_DIR
    path = os.path.expanduser(path)
    system.ensure_path('/', path)
    config_file = codecs.open(path, 'w', 'utf-8')
    yaml.dump(config, config_file, default_flow_style=False)
    config_file.close()

def find_transmission_daemon():
    daemons = []
    for process in system.process_list():
        if process[1][-19:] == 'transmission-daemon':
            daemons.append(process[0])
    return daemons

def main():
    #enumerate actions
    actions = []
    for attr in dir(Supervisor):
        if attr[:7] == 'action_':
            actions.append(attr[7:])
    actions_string = ', '.join([a for a in actions])
    
    # parse args
    parser = OptionParser(version='Supervisor %s' % (__version__), usage='%prog [options]')
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose', help='Enable verbose output.')
    parser.add_option('-c', '--config', type='string', dest='config', help='Configuration file.', metavar='<file>')
    parser.add_option('-p', '--port', type='int', dest='port', help='Transmission service port.', metavar="<port>")
    parser.add_option('-i', '--interval', type='float', dest='interval', help='Transmission query interval.', metavar="<interval>")
    parser.add_option('-r', '--ratio', type='float', dest='ratio', help='At which ration to stop seeding and take action.', metavar="<ratio>")
    parser.add_option('-a', '--action', type='string', dest='action', help='The action to take when seeding is done. Available actions: %s' % (actions_string), metavar="<action>")
    parser.add_option('-f', '--finished', type='string', dest='finished', help='Directory to move finished files to.', metavar="<dir>")
    parser.add_option('-u', '--user', type='string', dest='user', help='Username used when connecting to transmission.', metavar="<user>")
    parser.add_option('-w', '--password', type='string', dest='password', help='Password used when connecting to transmission.', metavar="<password>")
    parser.add_option('-l', '--logdir', type='string', dest='logdir', help='Directory to save logs in.', metavar="<dir>")
    opts = parser.parse_args()[0]
    
    config = load_config(opts.config)
    
    verbose = False
    if opts.verbose:
        verbose = opts.verbose
    if opts.logdir:
        config['log-dir'] = opts.logdir
    
    format = '%(asctime)s %(levelname)s %(message)s'
    log_path = os.path.join(os.path.expanduser(config['log-dir']), 'supervisor.log')
    if verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.WARNING
    logging.basicConfig(level=log_level, filename=log_path, format=format)
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(format))
    logging.getLogger('').addHandler(console)
    
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
    
    transmission_pid = find_transmission_daemon()
    if len(transmission_pid) == 0:
        logging.warning('No transmission-daemon. Trying to start one.')
        command = 'transmission-daemon'
        if opts.user and opts.password:
            command += ' --auth --username ' + opts.user + ' --password ' + opts.password
        else:
            command += ' --no-auth'
        if system.execute(command) == None:
            logging.error('Failed to start daemon.')
            sys.exit(0)
        time.sleep(0.5)
    
    supervisor = Supervisor(config, user=opts.user, password=opts.password, verbose=verbose)
    try:
        supervisor.run()
    except KeyboardInterrupt:
        try:
            save_config(supervisor.config, opts.config)
        except IOError, exception:
            logging.warning('Failed to save configuration: %s' % exception)

if __name__ == '__main__':
    main()
