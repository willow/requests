# urllib3/connection.py
# Copyright 2008-2013 Andrey Petrov and contributors (see CONTRIBUTORS.txt)
#
# This module is part of urllib3 and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

import sys
import socket
from socket import timeout as SocketTimeout
import logging
log = logging.getLogger(__name__)

try: # Python 3
    from http.client import HTTPConnection as _HTTPConnection, HTTPException
except ImportError:
    from httplib import HTTPConnection as _HTTPConnection, HTTPException

class DummyConnection(object):
    "Used to detect a failed ConnectionCls import."
    pass

try: # Compiled with SSL?
    ssl = None
    HTTPSConnection = DummyConnection

    class BaseSSLError(BaseException):
        pass

    try: # Python 3
        from http.client import HTTPSConnection as _HTTPSConnection
    except ImportError:
        from httplib import HTTPSConnection as _HTTPSConnection

    import ssl
    BaseSSLError = ssl.SSLError

except (ImportError, AttributeError): # Platform-specific: No SSL.
    pass

from .exceptions import (
    ConnectTimeoutError,
)
from .packages.ssl_match_hostname import match_hostname
from .packages import six
from .util import (
    assert_fingerprint,
    resolve_cert_reqs,
    resolve_ssl_version,
    ssl_wrap_socket,
)


port_by_scheme = {
    'http': 80,
    'https': 443,
}


class HTTPConnection(_HTTPConnection, object):
    """
    Based on httplib.HTTPConnection but provides an extra constructor
    backwards-compatibility layer between older and newer Pythons.
    """

    default_port = port_by_scheme['http']

    # By default, disable Nagle's Algorithm.
    tcp_nodelay = 1

    def __init__(self, *args, **kw):
        if six.PY3:  # Python 3
            kw.pop('strict', None)
        if sys.version_info < (2, 7):  # Python 2.6 and older
            kw.pop('source_address', None)

        # Pre-set source_address in case we have an older Python like 2.6.
        self.source_address = kw.get('source_address')

        # Superclass also sets self.source_address in Python 2.7+.
        _HTTPConnection.__init__(self, *args, **kw)  
        
    def _send_request(self, method, url, body, headers):
        log.info("begin: httpconection: send req")
        super()._send_request(method, url, body, headers)
        log.info("completed: httpconection: send req")
    
    def putrequest(self, method, url, skip_host=0, skip_accept_encoding=0):
        log.info("begin: httpconection: put req")
        super().putrequest(method, url, skip_host, skip_accept_encoding)
        log.info("completed: httpconection: put req")
        
    def _send_output(self, message_body=None):
        log.info("begin: httpconection: _send_output")
        super()._send_output(message_body)
        log.info("completed: httpconection: _send_output")
        
    def send(self, data):
        log.info("begin: httpconection: send")
        
            
        super().send(data)
        log.info("completed: httpconection: send")

    def _new_conn(self):
        """ Establish a socket connection and set nodelay settings on it.

        :return: a new socket connection
        """
        log.info("begin: httpconection: _new_conn")
        extra_args = []
        if self.source_address:  # Python 2.7+
            extra_args.append(self.source_address)

        conn = socket.create_connection(
            (self.host, self.port), self.timeout, *extra_args)
        conn.setsockopt(
            socket.IPPROTO_TCP, socket.TCP_NODELAY, self.tcp_nodelay)
        log.info("completed: httpconection: _new_conn")
        return conn

    def _prepare_conn(self, conn):
        log.info("begin: httpconection: _prepare_conn")
        self.sock = conn
        # the _tunnel_host attribute was added in python 2.6.3 (via
        # http://hg.python.org/cpython/rev/0f57b30a152f) so pythons 2.6(0-2) do
        # not have them.
        if getattr(self, '_tunnel_host', None):
            # TODO: Fix tunnel so it doesn't depend on self.sock state.
            self._tunnel()
        log.info("completed: httpconection: _new_conn")

    def connect(self):
        log.info("begin: httpconection: http connect")
        conn = self._new_conn()
        self._prepare_conn(conn)
        log.info("completed: httpconection: http connect")


class HTTPSConnection(HTTPConnection):
    default_port = port_by_scheme['https']

    def __init__(self, host, port=None, key_file=None, cert_file=None,
                 strict=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kw):

        HTTPConnection.__init__(self, host, port, strict=strict,
                                timeout=timeout, **kw)

        self.key_file = key_file
        self.cert_file = cert_file

        # Required property for Google AppEngine 1.9.0 which otherwise causes
        # HTTPS requests to go out as HTTP. (See Issue #356)
        self._protocol = 'https'

    def connect(self):
        log.info("begin: https conection: connect")
        conn = self._new_conn()
        self._prepare_conn(conn)
        self.sock = ssl.wrap_socket(conn, self.key_file, self.cert_file)
        log.info("begin: https conection: connect")

class VerifiedHTTPSConnection(HTTPSConnection):
    """
    Based on httplib.HTTPSConnection but wraps the socket with
    SSL certification.
    """
    cert_reqs = None
    ca_certs = None
    ssl_version = None
    conn_kw = {}

    def set_cert(self, key_file=None, cert_file=None,
                 cert_reqs=None, ca_certs=None,
                 assert_hostname=None, assert_fingerprint=None):

        self.key_file = key_file
        self.cert_file = cert_file
        self.cert_reqs = cert_reqs
        self.ca_certs = ca_certs
        self.assert_hostname = assert_hostname
        self.assert_fingerprint = assert_fingerprint

    def connect(self):
        # Add certificate verification

        log.info("begin: https verified conection: connect")
        try:
            sock = socket.create_connection(
                address=(self.host, self.port), timeout=self.timeout,
                **self.conn_kw)
        except SocketTimeout:
            raise ConnectTimeoutError(
                self, "Connection to %s timed out. (connect timeout=%s)" %
                (self.host, self.timeout))
        log.info("begin: https verified : connect: set socket")
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY,
                        self.tcp_nodelay)
        log.info("completed: https verified : connect: set socket")
        log.info("begin: https verified : connect: resolve cert reqs")
        resolved_cert_reqs = resolve_cert_reqs(self.cert_reqs)
        log.info("completed: https verified : connect: resolve cert reqs")
        log.info("begin: https verified : connect: resolve ssl ver")
        resolved_ssl_version = resolve_ssl_version(self.ssl_version)
        log.info("complete: https verified : connect: resolve ssl ver")

        hostname = self.host
        if getattr(self, '_tunnel_host', None):
            # _tunnel_host was added in Python 2.6.3
            # (See: http://hg.python.org/cpython/rev/0f57b30a152f)

            self.sock = sock
            # Calls self._set_hostport(), so self.host is
            # self._tunnel_host below.
            log.info("begin: https verified : connect: _tunnel outer call")
            self._tunnel()
            log.info("complete: https verified : connect: _tunnel outer call")

            # Override the host with the one we're requesting data from.
            hostname = self._tunnel_host

        # Wrap socket using verification with the root certs in
        # trusted_root_certs
        log.info("begin: https verified : connect: ssl_wrap_socket")
        self.sock = ssl_wrap_socket(sock, self.key_file, self.cert_file,
                                    cert_reqs=resolved_cert_reqs,
                                    ca_certs=self.ca_certs,
                                    server_hostname=hostname,
                                    ssl_version=resolved_ssl_version)
        log.info("complete: https verified : connect: ssl_wrap_socket")
        
        if resolved_cert_reqs != ssl.CERT_NONE:
            if self.assert_fingerprint:
                log.info("begin: https verified : connect: assert fingerprint")
                assert_fingerprint(self.sock.getpeercert(binary_form=True),
                                   self.assert_fingerprint)
                log.info("complete: https verified : connect: assert fingerprint")
            elif self.assert_hostname is not False:
                log.info("begin: https verified : connect: match hostname")
                match_hostname(self.sock.getpeercert(),
                               self.assert_hostname or hostname)
                log.info("complete: https verified : connect: match host name")
        if self.sock:
            old_method = self.sock.sendall
            def sock_wrap(sendalldata):
                log.info("begin: httpconection: send: before sock.sendall")
                old_method(sendalldata)
                log.info("completed: httpconection: send: before sock.sendall")
            self.sock.sendall = sock_wrap
            
        log.info("completed: https verified conection: connect")
if ssl:
    # Make a copy for testing.
    UnverifiedHTTPSConnection = HTTPSConnection
    HTTPSConnection = VerifiedHTTPSConnection
