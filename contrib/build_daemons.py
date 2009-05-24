#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2009-05, Erik Svensson <erik.public@gmail.com>

import os, sys, os.path, subprocess

def execute(command):
    """Execute a shell command"""
    try:
        p = subprocess.Popen(command, shell=True, bufsize=-1, stdout=subprocess.PIPE)
        r = p.wait()
    except (OSError, ValueError):
        return None
    if r == 0:
        return p.stdout.read()
    else:
        return None

if __name__ == '__main__':
    root = os.path.abspath(sys.argv[1])
    dirs = os.listdir(root)
    for dir in dirs:
        thedir = os.path.join(root, dir)
        version = 0
        try:
            version = float(dir)
        except ValueError:
            version = 0
        if version > 1.3:
            print('check %s' % thedir)
            app = os.path.join(thedir, 'daemon', 'transmission-daemon')
            if not os.path.exists(app):
                print('make %s' % app)
                os.chdir(thedir)
                execute('./autogen.sh && make -s')

