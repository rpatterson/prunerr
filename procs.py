import os, os.path, subprocess, re, signal

def process_list():
    """List active processes the UNIX way. Tested with Ubuntu 8.04, FreeBSD 7.0 and Mac OS X 10.5."""
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
            print('BAD: \"' + line + '\"')
    return procs

def execute(command):
    """Execute a shell command"""
    try:
        p = subprocess.Popen(command, shell=True, bufsize=-1, stdout=subprocess.PIPE, env = {'LC_ALL' : 'C'})
        r = p.wait()
    except (OSError, ValueError):
        return None
    if r == 0:
        return p.stdout.read()
    else:
        return None

def kill(pid):
    """Send SIGKILL to a process id"""
    os.kill(pid, signal.SIGKILL)

if __name__ == '__main__':
    procs = process_list()
    for proc in procs:
        print('%d: %s' % (proc[0], proc[1]))
