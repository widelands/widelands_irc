from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import events
import sys
import threading
import config
import hmac
from irc import IrcConnection

irc = None

# handle POST events from github server
# We should also make sure to ignore requests from the IRC, which can clutter
# the output with errors
CONTENT_TYPE = 'content-type'
CONTENT_LEN = 'content-length'
EVENT_TYPE = 'x-github-event'

class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pass
    def do_CONNECT(self):
        pass
    def do_POST(self):
        if not all(x in self.headers for x in [CONTENT_TYPE, CONTENT_LEN, EVENT_TYPE]):
            return

        content_type = self.headers['content-type']
        content_len = int(self.headers['content-length'])
        event_type = self.headers['x-github-event']

        if content_type != "application/json":
            irc.log_to_file('CRITICAL', 'ERROR: not JSON\nData: {}'.format(self.headers))
            self.send_error(400, "Bad Request", "Expected a JSON request")
            return

        irc.log_to_file('DEBUG', 'INFO: valid JSON\nData: {}'.format(self.headers))

        data = self.rfile.read(content_len)
        data = data.decode()

        if irc.widelands['webhook']['secret']:
            if not ('X-Hub-Signature' and 'X-Hub-Signature-256' in self.headers.keys()):
                irc.log_to_file('CRITICAL', 'ERROR: Signature Header Missing\nSHA1: {}\nSHA256: {}'.format(
                    self.headers['X-Hub-Signature'] if 'X-Hub-Signature' in self.headers.keys() else 'not set'
                    , self.headers['X-Hub-Signature-256'] if 'H-Hub-Signature-256' in self.headers.keys() else 'not set'
                    ))
                self.send_error(403, "Forbidden", "Signature header is missing!")
                return
            else:
                if 'X-Hub-Signature' in self.headers.keys():
                    irc.log_to_file('DEBUG', 'INFO: Check Signature: {}'.format(self.headers['X-Hub-Signature']))
                    _check_signature(self.headers['X-Hub-Signature'], data)
                if 'X-Hub-Signature-256' in self.headers.keys():
                    irc.log_to_file('DEBUG', 'INFO: Check Signature: {}'.format(self.headers['X-Hub-Signature-256']))
                    _check_signature(self.headers['X-Hub-Signature-256'], data)

        self.send_response(200)
        self.send_header('content-type', 'text/html')
        self.end_headers()
        self.wfile.write(bytes('OK', 'utf-8'))

        events.handle_event(irc, event_type, json.loads(data))
        return

def worker():
    irc.loop()

irc = IrcConnection('config.ini')

def _check_signature(signature_header, data):
    hash_algo, header_signature = signature_header.split('=')
    generated_signature = _generate_signature(data, hash_algo)
    if not hmac.compare_digest(header_signature, generated_signature):
        irc.log_to_file('CRITICAL', 'ERROR: Check Signature: FAILED\nTO CHECKS: {}\nTO VERIFY: {}'.format(header_signature, generated_signature))
        self.send_error(403, "Forbidden", "Request signatures didn't match!")
        return
    irc.log_to_file('DEBUG', 'INFO: Check Signature: OK\nTO CHECKS: {}\nTO VERIFY: {}'.format(header_signature, generated_signature))

def _generate_signature(data, hash_algo):
    key = irc.widelands['webhook']['secret']
    key_bytes= bytes(key, 'utf-8')
    data_bytes = bytes(data, 'utf-8')
    return hmac.new(key_bytes, data_bytes, digestmod=hash_algo).hexdigest()

t = threading.Thread(target=worker)
t.start()

if irc.widelands['webhook']['start']:
    # Run Github webhook handling server
    try:
        server = HTTPServer((irc.widelands['webhook']['host'], irc.widelands['webhook']['port']), MyHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        irc.log_to_file('INFO', "Exiting")
        server.socket.close()
        irc.stop_loop()

