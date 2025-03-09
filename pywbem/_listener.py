#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

"""
*New in pywbem 0.9 as experimental and finalized in 0.10.*

The :class:`~pywbem.WBEMListener` class provides a thread-based WBEM listener
service that can receive CIM indications from multiple WBEM servers and that
calls registered callback functions to deliver the received indications.

The listener receives indications from an indication sender, validates the
formtting of the indication and queues each received indication into an
interprocess queue. A seperate thread monitors this queue and calls the
callback functions for each indication in the queue.

This insures that timing in the callback functions does not interfere with the
reception of indications from the indication sender.

Examples
--------

The following example creates and runs a listener::

    import logging
    from pywbem import WBEMListener

    def process_indication(indication, host):
        '''This function gets called when an indication is received.'''

        print(f"Received CIM indication from {host}: {indication!r}")

    def main():

        # Configure logging of the listener via the Python root logger
        logging.basicConfig(
            filename='listener.log', level=logging.WARNING,
            format='%(asctime)s - %(levelname)s - %(message)s')

        certkeyfile = 'listener.pem'

        # Set host name to wildcard host address to recieve indications on
        # any network address defined for this system.
        listener = WBEMListener(host="",
                                http_port=5990,
                                https_port=5991,
                                certfile=certkeyfile,
                                keyfile=certkeyfile)
        listener.add_callback(process_indication)

        try:
            listener.start()

            # process_indication() will be called for each received indication

            . . .  # wait for some condition to end listening

        finally:
            listener.stop()

Alternative code using the class as a context manager::

    with WBEMListener(...) as listener:
        listener.add_callback(process_indication)
        listener.start()

        # process_indication() will be called for each received indication

        ... # wait for some condition to end listening

    # listener.stop() has been called automatically

See the example in section :ref:`WBEMSubscriptionManager` for an example of
using a listener in combination with a subscription manager.

Another listener example is in the script ``examples/listen.py`` (when you
clone the GitHub pywbem/pywbem project). It is an interactive Python shell that
creates a listener and displays any indications it receives, in MOF format.


.. _`Logging in the listener`:

Logging in the listener
-----------------------

Each :class:`~pywbem.WBEMListener` object has its own separate Python logger
object with the name:

  `'pywbem.listener.{id}'`

where `{id}` is a string that is unique for each :class:`~pywbem.WBEMListener`
object within the Python process.

The :attr:`~pywbem.WBEMListener.logger` property of a
:class:`~pywbem.WBEMListener` object provides access to that Python logger
object, if needed.

The listener will log any indications it receives and any responses it sends
back to the indication sender, at the ``INFO`` logging level
(see :ref:`py:levels`).

In addition, it will log errors at the ``ERROR`` logging level.

The Python root logger will by default (i.e. when not being configured) print
log records of logging level ``WARNING`` or greater to `sys.stderr`. So the
indication and response interactions will not be printed by default, but any
errors logged at the ``ERROR`` logging level will be printed by default.

Listener indication flood
-------------------------

A listener processes indications through an interprocess queue so a flood of
indications from the indication sender where the callback processing was taking
longer than indication reception could over time result in indications piling
up in the received indication queue. While this is not normally an issue a
flood of indications from the sender could result in more indications in the
queue than the memory of the client can support. Effective with version 1.8.0,
an optional argument was added to the listener initialization
(max_ind_queue_size) that causes generation of an exception
(ListenerQueueFullError) and stopping of sending indication reception. Since
this effectively stops the listener, it should only be used if the number of
indications in the queue is a threat to the memory in the client, not for
temporary slowdown of the flow of indications from the indication sender.

It closes the listener connections and  either discards indications in the queue
or .

The following example creates and runs a listener::

    import logging
    from pywbem import WBEMListener

    def process_indication(indication, host):
        '''This function gets called when an indication is received.'''

        print(f"Received CIM indication from {host}: {indication!r}")

    def main():

        # Configure logging of the listener via the Python root logger
        logging.basicConfig(
            filename='listener.log', level=logging.WARNING,
            format='%(asctime)s - %(levelname)s - %(message)s')

        certkeyfile = 'listener.pem'

        # Set host name to wildcard host address to recieve indications on
        # any network address defined for this system.
        listener = WBEMListener(host="",
                                http_port=5990,
                                https_port=5991,
                                certfile=certkeyfile,
                                keyfile=certkeyfile,
                                max_ind_queue_size=5000,
                                )
        listener.add_callback(process_indication)

        try:
            listener.start()

            # process_indication() will be called for each received indication

            . . .  # wait for some condition to end listening

        except ListenerQueueFullError:
            print("Indication listener failed. Indication queue full.")
            listener.stop()


        finally:
            listener.stop()



.. _`WBEMListener class`:

WBEMListener class
------------------
"""

import sys
import os
import errno
from contextlib import contextmanager
import re
import logging
import ssl
import threading
import atexit
import getpass
import queue
try:
    import termios
except ImportError:
    # termios is only supported on some operating systems
    termios = None
import socketserver
import http.client
from http.server import HTTPStatus, HTTPServer, BaseHTTPRequestHandler

from time import sleep

from . import _cim_xml
from ._version import __version__
from ._cim_obj import CIMInstance
from ._cim_constants import CIM_ERR_NOT_SUPPORTED, CIM_ERR_INVALID_PARAMETER, \
    _statuscode2name
from ._tupleparse import TupleParser
from ._tupletree import xml_to_tupletree_sax
from ._exceptions import CIMXMLParseError, XMLParseError, CIMVersionError, \
    DTDVersionError, ProtocolVersionError, ListenerCertificateError, \
    ListenerPortError, ListenerPromptError, ListenerQueueFullError
from ._utils import _format

# CIM-XML protocol related versions implemented by the WBEM listener.
# These are returned in export message responses.
IMPLEMENTED_CIM_VERSION = '2.0'
IMPLEMENTED_DTD_VERSION = '2.4'
IMPLEMENTED_PROTOCOL_VERSION = '1.4'

# CIM-XML protocol related versions supported by the WBEM listener
# These are checked in export message requests.
SUPPORTED_DTD_VERSION_PATTERN = r'2\.\d+'
SUPPORTED_DTD_VERSION_STR = '2.x'
SUPPORTED_PROTOCOL_VERSION_PATTERN = r'1\.\d+'
SUPPORTED_PROTOCOL_VERSION_STR = '1.x'

# Pattern for findall() for header values that are a list of tokens with
# quality values (see RFC2616). The pattern does not verify conformance
# to the valid characters for tokens, but does its job in parsing tokens
# and q values.
TOKEN_QUALITY_FINDALL_PATTERN = re.compile(
    r'([^;, ]+)'
    r'(?:; *q=([01](?:\.[0-9]*)?))?'
    r'(?:, *)?')
TOKEN_CHARSET_FINDALL_PATTERN = re.compile(
    r'([^;, ]+)'
    r'(?:; *charset="?([^";, ]*)"?)?'
    r'(?:, *)?')

__all__ = ['WBEMListener', 'callback_interface']


@contextmanager
def saved_term_attrs():
    """
    Context manager that saves and restores the attributes of the terminal that
    is used by getpass().

    getpass() on Linux and macOS modifies the terminal attributes to disable
    the echoing of the typed password, and restores the terminal attributes
    before it returns. However, when the process calling getpass() gets
    terminated with a SIGTERM signal while it waits for getpass() to return,
    then getpass() itself will not restore the terminal settings.

    This context manager improves that behavior by restoring the settings in
    its exit part, and by additionally registering an Python atexit handler
    that restores the settings. There is a check so that the settings are
    restored only once. This performs the restore in some more cases compared
    to the standard getpass() behavior, particularly when the process calling
    getpass() is terminated with a SIGTERM signal.
    For details on cases where the finally block and thus also the exit part
    of a context manager do *not* get control, see
    https://stackoverflow.com/a/49262664/1424462.

    The logic to obtain the file descriptor of the terminal must be kept
    consistent with how it is done in getpass(), see
    https://github.com/python/cpython/blob/main/Lib/getpass.py#L46
    """
    if termios:
        try:
            # On Windows, os.O_NOCTTY does not exist.
            # pylint: disable=no-member
            term_fd = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY)
        except (OSError, AttributeError):
            try:
                term_fd = sys.stdin.fileno()
            except (AttributeError, ValueError):
                term_fd = None
    else:
        term_fd = None

    if term_fd is not None:
        count_dict = {'count': 0}  # must be mutable
        saved_attrs = termios.tcgetattr(term_fd)
        atexit.register(restore_term_attrs, term_fd, saved_attrs, count_dict)

    yield

    if term_fd is not None:
        restore_term_attrs(term_fd, saved_attrs, count_dict)


def restore_term_attrs(term_fd, saved_attrs, count_dict):
    """
    Restore the attributes of the terminal that is used by getpass().

    count_dict is used to ensure the restoration is performed only once. This
    is necessary because the function is called once directly after the
    password prompt, and once at exit.
    """
    if count_dict['count'] == 0:
        termios.tcsetattr(term_fd, termios.TCSAFLUSH, saved_attrs)
        count_dict['count'] += 1


def keyfile_password_prompt(keyfile):
    """
    Prompt for the password of a private key file.

    This method is only called if the key file has a password set.

    Parameters:
      keyfile (string): Path name of private key file.

    Returns:
      string: The password

    Raises:
      ListenerPromptError: Password prompt was interrupted or ended
    """
    prompt = f"Enter password for key file {keyfile}: "
    with saved_term_attrs():
        try:
            pw = getpass.getpass(prompt=prompt)
        except KeyboardInterrupt:
            new_exc = ListenerPromptError("Password prompt was interrupted")
            new_exc.__cause__ = None
            raise new_exc  # ListenerPromptError
        except EOFError:
            new_exc = ListenerPromptError("Password prompt was ended")
            new_exc.__cause__ = None
            raise new_exc  # ListenerPromptError
    return pw


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Defines an HTTPServer class for indication reception"""
    pass


class ListenerRequestHandler(BaseHTTPRequestHandler):
    """
    A request handler for the standard Python HTTP server, with a handler
    method for the HTTP POST method, that acts as a WBEM listener.
    """

    @property
    def logger(self):
        """
        :class:`py:logging.Logger`: Logger object for the listener using this
        request handler.

        Each listener object has its own separate logger object with the name:

          `'pywbem.listener.{id}'`

        where `{id}` is a unique string for each listener object.

        Users of the listener should not look up the logger object by name, but
        should use this property to get to it.
        """
        return self.server.listener.logger

    def invalid_method(self):
        """
        Handle invalid HTTP methods by sending HTTP status 405 "Method Not
        Allowed" back to the server. See DSP0200 for details on this.
        """
        self.send_http_error(405, headers=[('Allow', 'POST')])

    # pylint: disable=invalid-name
    def do_OPTIONS(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_HEAD(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_GET(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_PUT(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_PATCH(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_DELETE(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_TRACE(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_CONNECT(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_M_POST(self):
        """Invalid method for listener"""
        self.invalid_method()

    # pylint: disable=invalid-name
    def do_POST(self):
        """
        This method will be called for each POST request to one of the
        listener ports.

        It parses the CIM-XML export message and delivers the contained
        CIM indication to the stored listener object.
        """

        self.logger.debug("Received POST request")

        # Accept header check described in DSP0200
        accept = self.headers.get('Accept', 'text/xml')
        if accept not in ('text/xml', 'application/xml', '*/*'):
            self.send_http_error(
                406, 'header-mismatch',
                _format("Invalid Accept header value: {0} (need text/xml, "
                        "application/xml or */*)", accept))
            return

        # Accept-Charset header check described in DSP0200
        accept_charset = self.headers.get('Accept-Charset', 'UTF-8')
        tq_list = re.findall(TOKEN_QUALITY_FINDALL_PATTERN, accept_charset)
        found = False
        if tq_list is not None:
            for token, _ in tq_list:
                if token.lower() in ('utf-8', '*'):
                    found = True
                    break
        if not found:
            self.send_http_error(
                406, 'header-mismatch',
                _format("Invalid Accept-Charset header value: {0} "
                        "(need UTF-8 or *)", accept_charset))
            return

        # Accept-Encoding header check described in DSP0200.
        # The WBEM listener needs to support any Accept-Encoding header, so
        # no check is performed.
        # Note that the requests package adds the Accept-Encoding header with
        # values such as "gzip, deflate" if not provided by the requester.

        # Accept-Language header check described in DSP0200.
        # Ignored, because this WBEM listener does not support multiple
        # languages, and hence any language is allowed to be returned.

        # Accept-Range header check described in DSP0200
        accept_range = self.headers.get('Accept-Range', None)
        if accept_range is not None:
            self.send_http_error(
                406, 'header-mismatch',
                _format("Accept-Range header is not permitted {0}",
                        accept_range))
            return

        # Content-Type header check described in DSP0200
        content_type = self.headers.get('Content-Type', None)
        if content_type is None:
            self.send_http_error(
                406, 'header-mismatch',
                "Content-Type header is required")
            return
        tc_list = re.findall(TOKEN_CHARSET_FINDALL_PATTERN, content_type)
        found = False
        if tc_list is not None:
            for token, charset in tc_list:
                if token.lower() in ('text/xml', 'application/xml') and \
                   (charset == '' or charset.lower() == 'utf-8'):
                    found = True
                    break
        if not found:
            self.send_http_error(
                406, 'header-mismatch',
                _format("Invalid Content-Type header value: {0} "
                        "(need text/xml or application/xml with "
                        "charset=utf-8 or empty)",
                        content_type))
            return

        # Content-Encoding header check described in DSP0200
        content_encoding = self.headers.get('Content-Encoding', 'identity')
        if content_encoding.lower() != 'identity':
            self.send_http_error(
                406, 'header-mismatch',
                _format("Invalid Content-Encoding header value: {0}"
                        "(listener supports only identity)",
                        content_encoding))
            return

        # Content-Language header check described in DSP0200.
        # Ignored, because this WBEM listener does not support multiple
        # languages, and hence any language is allowed in the request.

        # The following headers are ignored. They are not allowed to be used
        # by servers, but listeners are not required to reject them:
        # Content-Range, Expires, If-Range, Range.

        # Start processing the request
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len)

        try:
            msgid, methodname, params = self.parse_export_request(body)
        except (CIMXMLParseError, XMLParseError) as exc:
            self.send_http_error(400, "request-not-well-formed", str(exc))
            return
        except DTDVersionError as exc:
            self.send_http_error(400, "unsupported-dtd-version", str(exc))
            return
        except ProtocolVersionError as exc:
            self.send_http_error(400, "unsupported-protocol-version", str(exc))
            return
        except CIMVersionError as exc:
            self.send_http_error(400, "unsupported-version", str(exc))
            return

        if methodname == 'ExportIndication':

            if len(params) != 1 or 'NewIndication' not in params:
                self.send_error_response(
                    msgid, methodname, CIM_ERR_INVALID_PARAMETER,
                    _format("Expecting one parameter NewIndication, got {0!A}",
                            params.keys()))
                return

            indication_inst = params['NewIndication']

            if not isinstance(indication_inst, CIMInstance):
                self.send_error_response(
                    msgid, methodname, CIM_ERR_INVALID_PARAMETER,
                    _format("NewIndication parameter is not a CIM instance, "
                            "but {0!A}", indication_inst))
                return
            # server.listener created in WBEMListener.start function
            # This function may generate queue full exception.
            self.server.listener.handle_indication(indication_inst,
                                                   self.client_address[0])

            self.send_success_response(msgid, methodname)

        else:
            self.send_error_response(
                msgid, methodname, CIM_ERR_NOT_SUPPORTED,
                _format("Unknown export method: {0!A}", methodname))

    def send_http_error(self, http_code, cim_error=None,
                        cim_error_details=None, headers=None):
        """
        Send an HTTP response back to the WBEM server that indicates
        an error at the HTTP level.
        """

        self.logger.warning(
            "Sending HTTP error response with HTTP status %s and headers: "
            "CIMError: %r, CIMErrorDetails: %r",
            http_code, cim_error, cim_error_details)

        self.send_response(http_code, http.client.responses.get(http_code, ''))
        self.send_header("CIMExport", "MethodResponse")
        if cim_error is not None:
            self.send_header("CIMError", cim_error)
        if cim_error_details is not None:
            self.send_header("CIMErrorDetails", cim_error_details)
        if headers is not None:
            for header, value in headers:
                self.send_header(header, value)
        self.end_headers()

        self.logger.warning(
            "Sent HTTP error response with HTTP status %s", http_code)

    def send_error_response(self, msgid, methodname, status_code, status_desc,
                            error_insts=None):
        """Send a CIM-XML response message back to the WBEM server that
        indicates error."""

        self.logger.warning(
            "Sending CIM-XML error response with CIM status %s: %s",
            _statuscode2name(status_code), status_desc)

        resp_xml = _cim_xml.CIM(
            _cim_xml.MESSAGE(
                _cim_xml.SIMPLEEXPRSP(
                    _cim_xml.EXPMETHODRESPONSE(
                        methodname,
                        _cim_xml.ERROR(
                            str(status_code),
                            status_desc,
                            error_insts),
                        ),  # noqa: E123
                    ),  # noqa: E123
                msgid, IMPLEMENTED_PROTOCOL_VERSION),
            IMPLEMENTED_CIM_VERSION, IMPLEMENTED_DTD_VERSION)

        resp_body = '<?xml version="1.0" encoding="utf-8" ?>\n' + \
                    resp_xml.toxml()

        if isinstance(resp_body, str):
            resp_body = resp_body.encode("utf-8")

        http_code = 200
        self.send_response(http_code, http.client.responses.get(http_code, ''))
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(resp_body)))
        self.send_header("CIMExport", "MethodResponse")
        self.end_headers()
        self.wfile.write(resp_body)

        self.logger.warning(
            "Sent CIM-XML error response with CIM status %s",
            _statuscode2name(status_code))

    def send_success_response(self, msgid, methodname):
        """Send a CIM-XML response message back to the WBEM server that
        indicates success."""

        self.logger.debug(
            "Sending CIM-XML successful response with msgid=%s", msgid)

        resp_xml = _cim_xml.CIM(
            _cim_xml.MESSAGE(
                _cim_xml.SIMPLEEXPRSP(
                    _cim_xml.EXPMETHODRESPONSE(
                        methodname),
                    ),  # noqa: E123
                msgid, IMPLEMENTED_PROTOCOL_VERSION),
            IMPLEMENTED_CIM_VERSION, IMPLEMENTED_DTD_VERSION)
        resp_body = '<?xml version="1.0" encoding="utf-8" ?>\n' + \
                    resp_xml.toxml()

        if isinstance(resp_body, str):
            resp_body = resp_body.encode("utf-8")

        http_code = 200
        self.send_response(http_code, http.client.responses.get(http_code, ''))
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(resp_body)))
        self.send_header("CIMExport", "MethodResponse")
        self.end_headers()
        self.wfile.write(resp_body)

        self.logger.debug(
            "Sent CIM-XML successful response with msgid=%s", msgid)

    @staticmethod
    def parse_export_request(request_str):
        """Parse a CIM-XML export request message, and return
        a tuple(msgid, methodname, params).
        """

        # Parse the XML into a tuple tree (may raise CIMXMLParseError or
        # XMLParseError):

        tt_ = xml_to_tupletree_sax(request_str, "CIM-XML export request")
        tp = TupleParser()
        tup_tree = tp.parse_cim(tt_)

        # Check the tuple tree

        if tup_tree[0] != 'CIM':
            raise CIMXMLParseError(
                _format("Expecting CIM element, got {0}", tup_tree[0]))
        tup_tree = tup_tree[2]

        if tup_tree[0] != 'MESSAGE':
            raise CIMXMLParseError(
                _format("Expecting MESSAGE element, got {0}", tup_tree[0]))
        msgid = tup_tree[1]['ID']
        tup_tree = tup_tree[2]

        if tup_tree[0] != 'SIMPLEEXPREQ':
            raise CIMXMLParseError(
                _format("Expecting SIMPLEEXPREQ element, got {0}",
                        tup_tree[0]))
        tup_tree = tup_tree[2]

        if tup_tree[0] != 'EXPMETHODCALL':
            raise CIMXMLParseError(
                _format("Expecting EXPMETHODCALL element, got {0}",
                        tup_tree[0]))

        methodname = tup_tree[1]['NAME']
        params = {}
        for name, obj in tup_tree[2]:
            params[name] = obj

        return (msgid, methodname, params)

    def log_request(self, code='-', size='-'):
        # pylint: disable=unused-argument
        """
        This function is called in
        :meth:`~py:http.server.BaseHTTPRequestHandler.send_response`.

        We override it to get a little more information logged in a somewhat
        better format at the INFO level.
        """
        if isinstance(code, HTTPStatus):
            # On Python 3, it can be an HTTPStatus object
            code = code.value
        self.log_message("Sending %s response with HTTP status %s",
                         self.command, code)

    def log_error(self, format, *args):
        # pylint: disable=redefined-builtin
        """
        The :class:`~py:http.server.BaseHTTPRequestHandler` methods call this
        method for anything that needs to get logged as an error.

        We override it in order to direct that to our own logger at the ERROR
        level.
        """
        self.logger.error(format, *args)

    def log_message(self, format, *args):
        # pylint: disable=redefined-builtin
        """
        The :class:`~py:http.server.BaseHTTPRequestHandler` methods call this
        method for anything that needs to get logged.

        We override it in order to direct that to our own logger at the INFO
        level.
        """
        self.logger.info(format, *args)

    def version_string(self):
        """
        Overrides the inherited method to add the pywbem listener version.
        """
        return _format("pywbem-listener/{0} {1} {2} ",
                       __version__, self.server_version, self.sys_version)


class CallbackThread(threading.Thread):
    """
    Thread subclass with a stop() method.

    The thread itself must check regularly for the stopped() event ( i.e. if
    stop_event.is_set()) exit the thread code.

    This subclass does not pass exceptions to the parent.
    """

    def __init__(self, *args, **kwargs):
        """
        Init with arguments for the thread
        """
        super().__init__(*args, **kwargs)
        self.stop_event = threading.Event()

    def stop(self):
        """Set the thread stop_event. To tell thread to stop"""
        self.stop_event.set()

    def stopped(self):
        """Test for thread stop event set"""
        return self.stop_event.is_set()


class ServerThread(threading.Thread):
    """
    Thread subclass that passes exceptions from the thread back to the
    calling thread when join executed.
    """

    def __init__(self, *args, **kwargs):
        """
        Init with arguments for the thread
        """
        super().__init__(*args, **kwargs)
        # Placeholder for possible exception.
        self.exec = None

    def run(self):
        """
        Add try block to Thread run function
        """
        try:
            super().run()
        except ListenerQueueFullError as e:
            self.exec = e

    def join(self, *args, **kwargs):
        """
        Pass exception in self.exec to the calling thread.
        """
        super().join(*args, **kwargs)
        if self.exec:
            raise self.exec


# pylint: disable=too-many-instance-attributes
class WBEMListener:
    """
    *New in pywbem 0.9 as experimental and finalized in 0.10.*

    A WBEM listener.

    The listener supports starting and stopping threads that listen for
    CIM-XML ExportIndication messages using HTTP and/or HTTPS, and that pass
    any received indications on to registered callback functions.

    The listener must be stopped in order to free the TCP/IP port it listens
    on. Using this class as a context manager ensures that the listener is
    stopped when leaving the context manager scope.

    The listener validates the syntax of the received CIM instance but does not
    validate the values of received the MESSAGE_ID or SEQUENCE_NUMBER of
    incoming indications. Therefore, it does not know if any indications are
    missing from a sequence. The callback function must do any such
    processing., etc. that confirms if indications are in the proper sequence
    and none were lost.
    """

    def __init__(self, host, http_port=None, https_port=None,
                 certfile=None, keyfile=None, max_ind_queue_size=0):
        """
        Parameters:

          host (:term:`string`):
            IP address or host name to which this listener is bound (i.e. at
            which this listener can be reached).  If a listener is bound to a
            particular IP address it will only receive indications addressed to
            that IP address (or to any IP address on the network interface
            containing that address) depending on the OS.

            Network wildcard addressing enables receiving indications from
            all IP addresses on the system by binding the listener to certain
            special addresses. The IPV4 wildcard IP address is "0.0.0.0"
            and the IPV6 wild card IP address is "::".

            Setting the host parameter to an empty string (i.e. "") is
            equivalent to using at least the IPV4 wildcard address.

          http_port (:term:`string` or :term:`integer`):
            HTTP port at which this listener can be reached. At
            least one port (HTTP or HTTPS) must be set. Both the http and
            https ports can be set.

            `None` means not to set up a port for HTTP.

          https_port (:term:`string` or :term:`integer`):
            HTTPS port at which this listener can be reached.

            `None` means not to set up a port for HTTPS.

          certfile (:term:`string`):
            File path of certificate file to be used as server certificate
            during SSL/TLS handshake when creating the secure HTTPS connection.

            It is valid for the certificate file to contain a private key; the
            server certificate sent during SSL/TLS handshake is sent without
            the private key.

            `None` means not to use a server certificate file. Setting up a port
            for HTTPS requires specifying a certificate file.

          keyfile (:term:`string`):
            File path of private key file to be used by the server during
            SSL/TLS handshake when creating the secure HTTPS connection.

            It is valid to specify a certificate file that contains a private
            key.

            `None` means not to use a private key file. Setting up a port
            for HTTPS requires specifying a private key file.

          max_ind_queue_size (:term:`integer`):
            A positive integer which defines the maximum number of the received
            indications that can be in the received indication queue.  If the
            queue of received indications reaches this size, the queue is
            blocked and the :exc:`~pywbem.ConnectionError` is raised.

            The default is 0 which disables the test for queue full.

            If set, this should be a large number since the goal is to stop
            receiving indications on the connection and may result in an
            indication receive failure on the WBEM server indication export
            function.

        Raises:

          :exc:`pywbem.ListenerQueueFullError`: if number of
            indications in the listener queue exceeds max_ind_queue_size.

          TypeError: port, max_ind_queue_size arguments invalid type.

          ValueError: No connection port specified, max_ind_queue_size
            invalid integer.
        """

        self._host = host

        if isinstance(http_port, int):
            self._http_port = int(http_port)  # Convert Python 2 long to int
        elif isinstance(http_port, str):
            self._http_port = int(http_port)
        elif http_port is None:
            self._http_port = http_port
        else:
            raise TypeError(
                _format("Invalid type for http_port: {0}", type(http_port)))

        if isinstance(https_port, int):
            self._https_port = int(https_port)  # Convert Python 2 long to int
        elif isinstance(https_port, str):
            self._https_port = int(https_port)
        elif https_port is None:
            self._https_port = https_port
        else:
            raise TypeError(
                _format("Invalid type for https_port: {0}", type(https_port)))

        if self._https_port is not None:
            if certfile is None:
                raise ValueError("https_port requires certfile")
            self._certfile = certfile
            if keyfile is None:
                raise ValueError("https_port requires keyfile")
            self._keyfile = keyfile
        else:
            self._certfile = None
            self._keyfile = None

        if self._http_port is None and self._https_port is None:
            raise ValueError("Listener requires at least one active port")

        self._http_server = None  # ThreadedHTTPServer for HTTP
        self._http_thread = None  # Thread for HTTP
        self._https_server = None  # ThreadedHTTPServer for HTTPS
        self._https_thread = None  # Thread for HTTPS

        self._logger = logging.getLogger(
            _format("pywbem.listener.{0}", id(self)))

        self._callbacks = []  # Registered callback functions

        if not isinstance(max_ind_queue_size, int):
            raise TypeError("max_ind_queue_size argument must be integer.")
        if max_ind_queue_size < 0:
            raise ValueError(
                "max__ind_queue_size argument must be positive integer.")
        self._max_ind_queue_size = max_ind_queue_size

        # Define timeout in seconds for gets on ind_delivery_queue object.
        # Causes wait after indication queue get if queue is empty.
        # Choice of 2 seconds was arbitrary.
        #
        self.queue_get_timeout = 2

        self.ind_delivery_queue = None
        self.callback_thread = None

    def __str__(self):
        """
        Return a representation of the :class:`~pywbem.WBEMListener` object
        with a subset of its attributes.
        """
        return _format(
            "WBEMListener("
            "_host={s._host!A}, "
            "_http_port={s._http_port!A}, "
            "_https_port={s._https_port!A}, "
            "...)",
            s=self)

    def __repr__(self):
        """
        Return a representation of the :class:`~pywbem.WBEMListener` object
        with all attributes, that is suitable for debugging.
        """
        return _format(
            "WBEMListener("
            "_host={s._host!A}, "
            "_http_port={s._http_port!A}, "
            "_https_port={s._https_port!A}, "
            "_certfile={s._certfile!A}, "
            "_keyfile={s._keyfile!A}, "
            "_logger={s._logger!A}, "
            "_callbacks={s._callbacks!A})",
            "_max_ind_queue_size={s._max_ind_queue_size!A})",
            s=self)

    def __enter__(self):
        """
        *New in pywbem 0.12.*

        Enter method when the class is used as a context manager.

        Returns the listener object.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        *New in pywbem 0.12.*

        Exit method when the class is used as a context manager.

        Stops the listener by calling :meth:`~pywbem.WBEMListener.stop`.
        """
        self.stop()
        return False  # re-raise any exceptions

    @property
    def host(self):
        """
        :term:`string`: IP address or host name to which this listener is
        bound. If IP adress 0.0.0.0, this listener is not bound to a particular
        IP address and accepts requests from any host on any network.
        """
        return self._host

    @property
    def http_port(self):
        """
        :term:`integer`: HTTP port at which this listener can be reached.

        `None` means there is no port set up for HTTP.
        """
        return self._http_port

    @property
    def https_port(self):
        """
        :term:`integer`: HTTPS port at which this listener can be reached.

        `None` means there is no port set up for HTTPS.
        """
        return self._https_port

    @property
    def http_started(self):
        """
        :class:`py:bool`: Boolean indicating whether the listener is started
        for the HTTP port.

        If no port is set up for HTTP, `False` is returned.

        *New in pywbem 0.12.*
        """
        return self._http_server is not None

    @property
    def https_started(self):
        """
        :class:`py:bool`: Boolean indicating whether the listener is started
        for the HTTPS port.

        If no port is set up for HTTPS, `False` is returned.

        *New in pywbem 0.12.*
        """
        return self._https_server is not None

    @property
    def certfile(self):
        """
        :term:`string`: File path of the certificate file used as server
        certificate during SSL/TLS handshake when creating the secure HTTPS
        connection.

        `None` means there is no certificate file being used (that is, no port
        is set up for HTTPS).
        """
        return self._certfile

    @property
    def keyfile(self):
        """
        :term:`string`: File path of the private key file used by the server
        during SSL/TLS handshake when creating the secure HTTPS connection.

        `None` means there is no certificate file being used (that is, no port
        is set up for HTTPS).
        """
        return self._keyfile

    @property
    def logger(self):
        """
        :class:`py:logging.Logger`: Logger object for this listener.

        Each listener object has its own separate logger object with the name:

          `'pywbem.listener.{id}'`

        where `{id}` is a unique string for each listener object.

        Users of the listener should not look up the logger object by name, but
        should use this property to get to it.
        """
        return self._logger

    @property
    def max_ind_queue_size(self):
        """
        Return a positive integer the maximum queue size. If this value is not
        0, an exception will be generated when this queue size is reached. If
        it is zero the exception is disabled.
        """
        return self._max_ind_queue_size

    def ind_delivery_queue_empty(self):
        """
        Return boolean True if the indication queue is empty. Otherwise return
        False. This is available becasue the queue_size attribute only returns
        an approximation.
        """
        return self.ind_delivery_queue.empty()

    def queue_size(self):
        """
        Return an integer with the approximate count of the number of
        indications currently in the received indication queue for this
        listener. """
        return self.ind_delivery_queue.qsize()

    def start(self):
        """
        Start the WBEM listener and callback threads, if they are not yet
        running.

        A interthread queue for holding indications recieved from a server
        thread and a thread for delivering indications from the queue to the
        callback functions are defined and the callback thread is started.

        A thread serving CIM-XML over HTTP is started if an HTTP port was
        specified for the listener. A thread serving CIM-XML over HTTPS is
        started if an HTTPS port was specified for the listener.

        These server threads will handle the ExportIndication export message
        described in :term:`DSP0200` and they will pass each indication
        received to the callback queue.  A separate thread handles passing
        received messages from this queue to the callback functions defined.

        The listener must be stopped again in order to free the TCP/IP port it
        listens on. The listener can be stopped explicitly using the
        :meth:`~pywbem.WBEMListener.stop` method. The listener will be
        automatically stopped when the main thread terminates (i.e. when the
        Python process terminates), or when :class:`~pywbem.WBEMListener`
        is used as a context manager when leaving its scope.

        In case of HTTPS, the private key file and certificate file are used.
        If the private key file is protected with a password, the password
        will be prompted for using :func:`py:getpass.getpass`. If the password
        is invalid, or if the private key file or certificate file are invalid,
        :exc:`pywbem.ListenerCertificateError` is raised.

        Raises:

          :exc:`pywbem.ListenerCertificateError`: Error with the certificate
            file or its private key file when using HTTPS.
          :exc:`pywbem.ListenerPortError`: WBEM listener port is already
            in use.
          :exc:`pywbem.ListenerPromptError`: Error when prompting for the
            password of the private key file when using HTTPS.
          :exc:`py:OSError`: Other error
          :exc:`py:IOError`: Other error (Python 2.7 only)
        """

        assert not self.callback_thread
        assert not self.ind_delivery_queue

        # Create received indication inter_thread queue and set queue max size
        # Note: value 0 disables the test for queue full
        # Uses Queue and not SimpleQueue because SimpleQueue does not support
        # queue.qsize() and queue.Full() exception.
        self.ind_delivery_queue = queue.Queue(
            maxsize=self._max_ind_queue_size)

        # Start callback thread
        self.callback_thread = CallbackThread(
            target=self.deliver_indications_forever,
            args=(self.ind_delivery_queue,),
            name='Callback',
            daemon=False)

        self.callback_thread.start()
        self.logger.info("Callback thread started max_queue=%s",
                         self._max_ind_queue_size)

        if self._http_port:
            if not self._http_server:
                self.logger.info("Starting threaded HTTP server on port %s",
                                 self._http_port)
                try:
                    server = ThreadedHTTPServer((self._host, self._http_port),
                                                ListenerRequestHandler)
                except OSError as exc:
                    self.stop_indication_delivery()
                    # Linux/macOS on py2: socket.error (derived from IOError);
                    # Linux/macOS on py3: OSError;
                    # Windows does not raise any exception if port is used
                    if getattr(exc, 'errno', None) == errno.EADDRINUSE:
                        new_exc = ListenerPortError(
                            f"WBEM listener port {self._http_port} is already "
                            "in use")
                        new_exc.__cause__ = None
                        raise new_exc  # ListenerPortError
                    raise

                # pylint: disable=attribute-defined-outside-init
                server.listener = self
                thread = ServerThread(target=server.serve_forever,
                                      name='http',
                                      daemon=False)
                # Insure thread is stopped on main thread exit
                self._http_server = server
                self._http_thread = thread
                thread.start()

                self.logger.info("Started threaded HTTP server on port %s",
                                 self._http_port)

        else:
            # Just in case someone changed self._http_port after init...
            self._http_server = None
            self._http_thread = None

        if self._https_port:
            if not self._https_server:

                self.logger.info("Starting threaded HTTPS server on port %s",
                                 self._https_port)

                try:
                    server = ThreadedHTTPServer((self._host, self._https_port),
                                                ListenerRequestHandler)
                except OSError as exc:
                    self.stop_indication_delivery()
                    # Linux/macOS on py2: socket.error (derived from IOError);
                    # Linux/macOS on py3: OSError;
                    # Windows does not raise any exception if port is used
                    if getattr(exc, 'errno', None) == errno.EADDRINUSE:
                        new_exc = ListenerPortError(
                            f"WBEM listener port {self._https_port} is "
                            "already in use")
                        new_exc.__cause__ = None
                        raise new_exc  # ListenerPortError
                    raise

                # pylint: disable=attribute-defined-outside-init
                server.listener = self

                try:
                    try:
                        # PROTOCOL_TLS was introduced in Py 2.7.13
                        ssl_protocol = ssl.PROTOCOL_TLS
                    except AttributeError:
                        # Alias for PROTOCOL_TLS and deprecated in Py 2.7.13
                        ssl_protocol = ssl.PROTOCOL_SSLv23
                    # SSLContext was introduced in Python 2.7.9
                    ctx = ssl.SSLContext(ssl_protocol)
                    ctx.options |= ssl.OP_NO_SSLv2
                    ctx.options |= ssl.OP_NO_SSLv3

                    def password_prompt():
                        return keyfile_password_prompt(self._keyfile)

                    try:
                        ctx.load_cert_chain(
                            certfile=self._certfile,
                            keyfile=self._keyfile,
                            password=password_prompt)
                    except ssl.SSLError as exc:
                        # On Python 3, exc.errno is EBADF, but on Python 2 it
                        # is a number 336265225 that seems to occur for other
                        # people too but is not understood. Therefore, we do
                        # not check for errno here.
                        if exc.library == 'SSL' and 'PEM lib' in str(exc):
                            new_exc = ListenerCertificateError(
                                "Invalid password for key file, bad key file, "
                                "or bad certificate file. Original error: "
                                f"{exc}")
                            new_exc.__cause__ = None
                            raise new_exc  # ListenerCertificateError
                        new_exc = ListenerCertificateError(
                            "SSL error when loading the certificate chain: "
                            f"errno={exc.errno}, library={exc.library}: {exc}")
                        new_exc.__cause__ = None
                        raise new_exc  # ListenerCertificateError
                    except OSError as exc:
                        fn = _cert_key_file(self._certfile, self._keyfile)
                        new_exc = ListenerCertificateError(
                            f"Issue opening {fn}: {exc}")
                        new_exc.__cause__ = None
                        raise new_exc  # ListenerCertificateError
                    server.socket = ctx.wrap_socket(
                        server.socket,
                        server_side=True)
                except AttributeError:
                    # Fall back to deprecated ssl.wrap_socket() before Py 2.7.9
                    # pylint: disable=deprecated-method
                    server.socket = ssl.wrap_socket(
                        server.socket,
                        certfile=self._certfile,
                        keyfile=self._keyfile,
                        server_side=True)

                thread = ServerThread(target=server.serve_forever,
                                      name="https",
                                      daemon=False)

                self._https_server = server
                self._https_thread = thread
                thread.start()

                self.logger.info("Started threaded HTTPS server on port %s",
                                 self._https_port)

        else:
            # Just in case someone changed self._https_port after init...
            self._https_server = None
            self._https_thread = None

    def stop(self):
        """
        Stop the WBEM listeners, the WBEM listener threads and callback thread,
        if they are running.
        """
        self.stop_servers()
        self.stop_indication_delivery()

    def stop_indication_delivery(self, immediate=False):
        """
        Stop the indication delivery thread and the queue and handle indications
        in the queue.

        If immediate is True, indications are cleared from the queue without
        calling the callbacks.

        If immdeiate is False, (default) indications are forwarded to the
        callback until the queue is empty before stopping delivery.
        """
        # Callback thread could already be stopped by FullQueue exception.
        if not self.callback_thread:
            return
        assert self.ind_delivery_queue
        if not immediate:
            # Wait for queue to empty through callbacks
            while not self.ind_delivery_queue.empty():
                self.logger.debug("Wait for delivery queue to empty")
                sleep(0.1)
        else:
            # clear the queue immediately
            clr_count = 0
            while not self.ind_delivery_queue.empty():
                self.ind_delivery_queue.get(block=False, timeout=0)
                clr_count += 1
                self.ind_delivery_queue.task_done()

            self.logger.debug(
                "%s indications discarded from queue", clr_count)

        self.logger.info("Stopping callback thread and queue")
        self.callback_thread.stop()
        self.callback_thread.join()
        self.callback_thread = None
        self.ind_delivery_queue = None
        self.logger.info("Joined callback thread")

    def stop_servers(self):
        """
        Stop the WBEM listener threads.
        """
        # Stopping the server will cause its `serve_forever()` method
        # to return, which will cause the server thread to terminate.

        if self._http_server:
            self.logger.info("Stopping threaded HTTP server")
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
            self._http_thread = None
            self.logger.info("Stopped threaded HTTP server")

        if self._https_server:
            self.logger.info("Stopping threaded HTTPS server")
            self._https_server.shutdown()
            self._https_server.server_close()
            self._https_server = None
            self._https_thread = None
            self.logger.info("Stopped threaded HTTPS server")

    def deliver_indications_forever(self, ind_queue):
        """
        Deliver indications from delivery_queue to the defined consumer.

        This function runs a loop in its own thread and only returns when the
        stop_event is set.

        It delivers indications as fast as the callbacks complete while
        indications exist in the queue and waits for time defined by
        self.queue_get_timeout for indications to arrive if
        ind_delivery_queue is empty.

        If stop_event.is_set() and the queue is emtpy it returns. This should
        only happen if the listener is stopped.
        """
        # Deliver queued indications until queue empty and stop_event set.
        self.logger.debug("Started callback thread.")
        while True:
            try:
                self.logger.debug(
                    "Get from queue. queue_size=%d", self.queue_size())

                indication_tuple = ind_queue.get(
                    block=True,
                    timeout=self.queue_get_timeout)

                self.deliver_indication_to_callbacks(indication_tuple[0],
                                                     indication_tuple[1])
                # Marks this item done in queue.
                # Really for delivering to multiple workers rather than
                # this simple case of a single worker. However this
                # keeps the queue clean.
                ind_queue.task_done()

            # If queue empty and stop event set break out of loop
            except queue.Empty:
                self.logger.debug("Queue empty exception received")

                if self.callback_thread.stopped():
                    self.logger.debug("Queue empty exception. stop callback")
                    break

        return

    def handle_indication(self, indication, host):
        """
        Entry point from the listener server threads with a single indication.
        Puts the indication in the received indication queue.

        If the self.queue_full parameter is not 0, an exception will be
        executed if the queue contains the number of indication defined by the
        listener max_ind_queue_size parameter. This completely stops the
        indication receive thread because this function does not return.

        """
        try:
            self.logger.debug("handle_indication rcvd indication queue put.")

            # Do not block put to queue. It puts or raises the Full exception
            self.ind_delivery_queue.put((indication, host), block=False)
            self.logger.debug(
                "Rcvd indication queue put done. queue_size %s",
                self.queue_size())

        except queue.Full:
            self.logger.debug(
                "Rcvd indication queue full. ListenerQueueFullError Exception, "
                "queue_size = %s", self.queue_size)
            new_exc = ListenerQueueFullError(
                "Listener indication delivery queue full, "
                f"queue_size = {self.queue_size}. Closing listener.")
            new_exc.__cause__ = None
            raise new_exc  # ListenerQueueFullError

    def deliver_indication_to_callbacks(self, indication, host):
        """
        This function is called to deliver a single indication to all
        registered callback functions. It is not supposed to be called
        by the user.

        It delivers the indication to all callback functions that have been
        added to the listener.

        If a callback function raises any exception this is logged as an error
        using the listener logger and the next registered callback function is
        called.

        Parameters:

          indication (:class:`~pywbem.CIMInstance`):
            Representation of the CIM indication to be delivered.

          host (:term:`string`):
            Host name or IP address of WBEM server sending the indication.
        """
        for callback in self._callbacks:

            self.logger.debug("Calling indication delivery callback function "
                              "%r to deliver %r indication",
                              callback.__name__, indication.classname)

            try:
                callback(indication, host)
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.error("Indication delivery callback function "
                                  "raised %s: %s", exc.__class__.__name__, exc)

            self.logger.debug("Returned from indication delivery callback "
                              "function %r", callback.__name__)

    def add_callback(self, callback):
        """
        Add a callback function to the listener.

        The callback function will be called for each indication this listener
        receives from any WBEM server.

        If the callback function is already known to the listener, it will not
        be added.

        Multiple callback functions may be defined by repeating this function
        with each callback function required.

        All of the defined callbacks will be executed for each indication.
        They will be executed serially in the order that they were added and
        on the same thread.

        The callback interface is defined in the callback_interface function.

        Parameters:

          callback (:func:`~pywbem.callback_interface`):
            Callable that is being called for each CIM indication that is
            received while the listener threads are running.
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)


def callback_interface(indication, host):
    # pylint: disable=unused-argument
    """
    *New in pywbem 0.9 as experimental and finalized in 0.10.*

    Interface of a callback function that is provided by the user of the API
    and that will be called by the listener for each received CIM indication.

    Parameters:

      indication (:class:`~pywbem.CIMInstance`):
        Representation of the CIM indication that has been received.
        Its `path` attribute is `None`.

      host (:term:`string`):
        Host name or IP address of WBEM server sending the indication.

    Raises:

        Exception: If a callback function raises any exception this is logged
          as an error using the listener logger and the next registered
          callback function is called. The exception is not passed back from
          the callback thread.
    """
    raise NotImplementedError


def _cert_key_file(certfile, keyfile):
    "Return a string for use in messages for the certificate or key files"
    if certfile == keyfile or keyfile is None:
        return f"certificate/key file {certfile}"
    return f"certificate file {certfile} or key file {keyfile}"
