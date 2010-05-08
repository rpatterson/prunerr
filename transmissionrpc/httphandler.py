# -*- coding: utf-8 -*-
# Copyright (c) 2010 Erik Svensson <erik.public@gmail.com>
# Licensed under the MIT license.

class HTTPHandlerError(Exception):
    def __init__(self, httpurl=None, httpcode=None, httpmsg=None, httpheaders=None, httpdata=None):
        Exception.__init__(self)
        self.url = ''
        self.code = 600
        self.message = ''
        self.headers = {}
        self.data = ''
        if isinstance(httpurl, (str, unicode)):
            self.url = httpurl
        if isinstance(httpcode, (int, long)):
            self.code = httpcode
        if isinstance(httpmsg, (str, unicode)):
            self.message = httpmsg
        if isinstance(httpheaders, (dict)):
            self.headers = httpheaders
        if isinstance(httpdata, (str, unicode)):
            self.data = httpdata
    
    def __repr__(self):
        return '<HTTPHandlerError %d, %s>' % (self.code, self.message)
    
    def __str__(self):
        return '<HTTPHandlerError %d, %s>' % (self.code, self.message)

    def __unicode__(self):
        return u'<HTTPHandlerError %d, %s>' % (self.code, self.message)

class HTTPHandler(object):
    """
    Prototype for HTTP handling.
    """
    def set_authentication(self, uri, login, password):
        """
        Transmission use basic authentication in earlier versions and digest
        authentication in later versions.
        
         * uri, the authentication realm URI.
         * login, the authentication login.
         * password, the authentication password.
        """
        raise NotImplementedError("Bad HTTPHandler, failed to implement set_authentication.")
    
    def request(self, url, query, headers, timeout):
        """
        Implement a HTTP POST request here.
        
         * url, The URL to request.
         * query, The query data to send. This is a JSON data string.
         * headers, a dictionary of headers to send.
         * timeout, requested request timeout in seconds.
        """
        raise NotImplementedError("Bad HTTPHandler, failed to implement request.")
