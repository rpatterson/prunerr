#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import os, os.path, subprocess, re, signal

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

def process_list():
    """
    List active processes the UNIX way. Returns a list of tuples with:
    (<process id>, <command>, <arguments>). <command> may include the path to the command.
    """
    procs = []
    re_procs = re.compile('^\s*(\d+)\s+(\S+)\s*(.*)')
    out = execute('ps -A -o pid= -o command=')
    for line in out.splitlines():
        match = re_procs.match(line)
        if match:
            fields = match.groups()
            # add process as a tuple of pid, command, arguments
            procs.append((int(fields[0]), fields[1], fields[2]))
        else:
            raise ValueError('BAD: \"' + line + '\"')
    return procs

def ensure_dir(base, path):
    """Tries to create the missing directories on the joined path base + path where base must exists."""
    if not os.path.exists(base):
        raise ValueError()
    if os.path.exists(os.path.join(base, path)):
        return
    dirs = []
    while not os.path.exists(os.path.join(base, path)):
        (path, name) = os.path.split(path)
        dirs.append(name)
    dirs.reverse()
    for name in dirs:
        path = os.path.join(path, name)
        os.mkdir(path)

def ensure_path(base, path):
    """Tries to create the missing directories on the joined path base + path where base must exists."""
    ensure_dir(base, os.path.dirname(path))
