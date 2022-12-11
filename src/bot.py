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
            self.send_error(400, "Bad Request", "Expected a JSON request")
            return

        data = self.rfile.read(content_len)
        #if sys.version_info < (3, 6):
        #    data = data.decode()
        data = data.decode()

        if irc.widelands['webhook']['secret'] and self.headers['x-hub-signature']:
            elements = self.headers['x-hub-signature'].split('=')
            github_hash_algo = elements[0]
            github_signature = elements[1]
            verify_signature = _generate_signature(data, github_hash_algo)
            if github_signature not in verify_signature:
                return

        self.send_response(200)
        self.send_header('content-type', 'text/html')
        self.end_headers()
        self.wfile.write(bytes('OK', 'utf-8'))

        events.handle_event(irc, event_type, json.loads(data))
        return

def worker():
    irc.loop()

irc = IrcConnection('src/config.ini')

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
        print("Exiting")
        server.socket.close()
        irc.stop_loop()

