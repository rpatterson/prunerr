#!/usr/bin/env python

import os, signal, procs

# kill all instances of transmission-daemon
for process in procs.process_list():
    if process[1][-19:] == 'transmission-daemon':
        print('Kill %d: %s' % (process[0], process[1]))
        os.kill(process[0], signal.SIGKILL)
