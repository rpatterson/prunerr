import os, os.path, subprocess, re, signal

def process_list():
    procs = []
    re_procs = re.compile('^\s+(\d+)\s+(\S+)\s*(.*)')
    out = execute('ps -A -o pid= -o command=')
    for line in out.splitlines():
        match = re_procs.match(line)
        if match:
            fields = match.groups()
            procs.append((int(fields[0]), fields[1], fields[2]))
    return procs

def execute(command):
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
    os.kill(pid, signal.SIGKILL)

if __name__ == '__main__':
    procs = process_list()
    for proc in procs:
        print('%d: %s' % (proc[0], proc[1]))
