#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 2008-07, Erik Svensson <erik.public@gmail.com>

import socket

UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB']

def format_size(size):
    s = float(size)
    i = 0
    while size > 1024.0 and i < len(UNITS):
        i += 1
        size /= 1024.0
    return (size, UNITS[i])

def format_timedelta(delta):
    minutes, seconds = divmod(delta.seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return '%d %02d:%02d:%02d' % (delta.days, hours, minutes, seconds)

class INetAddressError(Exception):
    pass

def inet_address(address, default_port, default_address='localhost'):
    addr = address.split(':')
    if len(addr) == 1:
        try:
            port = int(addr[0])
            addr = default_address
        except:
            addr = addr[0]
            port = default_port
    elif len(addr) == 2:
        port = int(addr[1])
        addr = addr[0]
    else:
        addr = default_address
        port = default_port
    try:
        socket.getaddrinfo(addr, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror, e:
        raise INetAddressError('Cannot look up address "%s".' % address)
    return (addr, port)

def rpc_bool(arg):
    if isinstance(arg, (str, unicode)):
        try:
            arg = bool(int(str))
        except:
            arg = arg.lower() in [u'true', u'yes']
    return 1 if bool(arg) else 0
