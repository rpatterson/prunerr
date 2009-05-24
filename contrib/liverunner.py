#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# 2009-05, Erik Svensson

import sys, os, subprocess, shutil, time, signal, re
import unittest
import tests.live

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
    (<process id>, <parent process id>, <command>, <arguments>). <command> may include the path to the command.
    """
    procs = []
    re_procs = re.compile('^\s*(\d+)\s+(\d+)\s+(\S+)\s*(.*)')
    out = execute('ps -A -o pid= -o ppid= -o command=')
    for line in out.splitlines():
        match = re_procs.match(line)
        if match:
            fields = match.groups()
            # add process as a tuple of pid, ppid, command, arguments
            procs.append((int(fields[0]), int(fields[1]), fields[2], fields[3]))
        else:
            raise ValueError('BAD: \"' + line + '\"')
    return procs

def rmerror(f, p, e):
    print('Failed to delete %s' % (p))

def runonce(app, settings_dir, downloads_dir):
    if os.path.exists(app):
        print('running %s' % app)
        if os.path.exists(settings_dir):
            shutil.rmtree(settings_dir, True, rmerror)
            os.mkdir(settings_dir)
        if os.path.exists(downloads_dir):
            shutil.rmtree(downloads_dir, True, rmerror)
            os.mkdir(downloads_dir)
        args = '-f -u admin -v admin -g %s -w %s' % (settings_dir, downloads_dir)
        command = app + ' ' + args
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # wait for the daemon to start
        time.sleep(2)
        if not process.poll():
            result = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromModule(tests.live).run(result)
            if not result.wasSuccessful():
                print('Test failed.')
                for item in result.errors:
                    print(item[1])
                for item in result.failures:
                    print(item[1])
            else:
                print('Test succeded.')
            wait_pid = None
            # apperantly you should kill children
            for p in process_list():
                if p[1] == process.pid:
                    wait_pid = p[0]
                    os.kill(p[0], signal.SIGTERM)
                    break
            if wait_pid:
                process.wait()
            else:
                print('Process not found')
                time.sleep(5)
        else:
            print(process.stderr.read())

def findthem(root):
    apps = {}
    dirs = os.listdir(root)
    for dir in dirs:
        thedir = os.path.join(root, dir)
        version = 0
        try:
            version = float(dir)
        except ValueError:
            version = 0
        if version > 1.3:
            app = os.path.join(thedir, 'daemon', 'transmission-daemon')
            if os.path.exists(app):
                apps[dir] = app
    return apps

def main():
    me = os.path.abspath(sys.argv[0])
    app = os.path.abspath(sys.argv[1])
    mdir, mname = os.path.split(me)
    settings_dir = os.path.join(mdir, 'settings')
    downloads_dir = os.path.join(mdir, 'downloads')
    if os.path.exists(app):
        if os.path.isdir(app):
            apps = findthem(app)
            for version, app in sorted(apps.iteritems()):
                runonce(app, settings_dir, downloads_dir)
        else:
            runonce(app, settings_dir, downloads_dir)
    shutil.rmtree(settings_dir, True, rmerror)
    shutil.rmtree(downloads_dir, True, rmerror)

if __name__ == '__main__':
    main()
