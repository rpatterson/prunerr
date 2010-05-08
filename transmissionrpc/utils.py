# -*- coding: utf-8 -*-
# Copyright (c) 2008-2010 Erik Svensson <erik.public@gmail.com>
# Licensed under the MIT license.

import socket, datetime, logging
import transmissionrpc.constants as constants
from transmissionrpc.constants import logger

UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB']

def format_size(size):
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(UNITS):
        i += 1
        size /= 1024.0
    return (size, UNITS[i])

def format_speed(size):
    (size, unit) = format_size(size)
    return (size, unit + '/s')

def format_timedelta(delta):
    minutes, seconds = divmod(delta.seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return '%d %02d:%02d:%02d' % (delta.days, hours, minutes, seconds)

def format_timestamp(timestamp):
    if timestamp > 0:
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.isoformat(' ')
    else:
        return '-'

class INetAddressError(Exception):
    pass

def inet_address(address, default_port, default_address='localhost'):
    addr = address.split(':')
    if len(addr) == 1:
        try:
            port = int(addr[0])
            addr = default_address
        except ValueError:
            addr = addr[0]
            port = default_port
    elif len(addr) == 2:
        try:
            port = int(addr[1])
        except ValueError:
            raise INetAddressError('Invalid address "%s".' % address)
        if len(addr[0]) == 0:
            addr = default_address
        else:
            addr = addr[0]
    else:
        raise INetAddressError('Invalid address "%s".' % address)
    try:
        socket.getaddrinfo(addr, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        raise INetAddressError('Cannot look up address "%s".' % address)
    return (addr, port)

def rpc_bool(arg):
    if isinstance(arg, (str, unicode)):
        try:
            arg = bool(int(arg))
        except ValueError:
            arg = arg.lower() in [u'true', u'yes']
    return 1 if bool(arg) else 0

TR_TYPE_MAP = {
    'number' : int,
    'string' : str,
    'double': float,
    'boolean' : rpc_bool,
    'array': list,
    'object': dict
}

def make_python_name(name):
    return name.replace('-', '_')

def make_rpc_name(name):
    return name.replace('_', '-')

def argument_value_convert(method, argument, value, rpc_version):
    if method in ('torrent-add', 'torrent-get', 'torrent-set'):
        args = constants.TORRENT_ARGS[method[-3:]]
    elif method in ('session-get', 'session-set'):
        args = constants.SESSION_ARGS[method[-3:]]
    else:
        return ValueError('Method "%s" not supported' % (method))
    if argument in args:
        info = args[argument]
        invalid_version = True
        while invalid_version:
            invalid_version = False
            replacement = None
            if rpc_version < info[1]:
                invalid_version = True
                replacement = info[3]
            if info[2] and info[2] <= rpc_version:
                invalid_version = True
                replacement = info[4]
            if invalid_version:
                if replacement:
                    logger.warning(
                        'Replacing requested argument "%s" with "%s".'
                        % (argument, replacement))
                    argument = replacement
                    info = args[argument]
                else:
                    raise ValueError(
                        'Method "%s" Argument "%s" does not exist in version %d.'
                        % (method, argument, rpc_version))
        return (argument, TR_TYPE_MAP[info[0]](value))
    else:
        raise ValueError('Argument "%s" does not exists for method "%s".',
                         (argument, method))

def get_arguments(method, rpc_version):
    if method in ('torrent-add', 'torrent-get', 'torrent-set'):
        args = constants.TORRENT_ARGS[method[-3:]]
    elif method in ('session-get', 'session-set'):
        args = constants.SESSION_ARGS[method[-3:]]
    else:
        return ValueError('Method "%s" not supported' % (method))
    accessible = []
    for argument, info in args.iteritems():
        valid_version = True
        if rpc_version < info[1]:
            valid_version = False
        if info[2] and info[2] <= rpc_version:
            valid_version = False
        if valid_version:
            accessible.append(argument)
    return accessible

def add_stdout_logger(level='debug'):
    levels = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARNING, 'error': logging.ERROR}
    
    trpc_logger = logging.getLogger('transmissionrpc')
    loghandler = logging.StreamHandler()
    if level in levels.keys():
        l = levels[level]
        trpc_logger.setLevel(l)
        loghandler.setLevel(l)
    trpc_logger.addHandler(loghandler)
