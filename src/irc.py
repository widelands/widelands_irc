import select
import time
import sys
import socket
import threading
import re
import locale
import ssl
import base64
import queue
import logging

from colors import colorize
from trigger import trigger
from config import config


class IrcConnection(trigger, config):
    def __init__(self, configfile):
        self.configfile = configfile
        self.read()
        self.command_list = ['001', '002', '003', '004', '005', '250', '251', '252', '253', '254', '255', '265', '266', '372', '375', '376', '404']
        self.version = "v0.7.1"
        self.connection = None
        self.buffer = ""
        self.last_ping = 0
        self.last_pong = 0
        self.start_time = 0
        self.kick_rejoin = 0
        self.rejoin_chan = None
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        self.is_debug = False
        self.quit_loop = False
        self.time_format = "%d.%m.%Y %H:%M:%S"
        locale.setlocale(locale.LC_TIME, self.widelands['locale']['lang'])
        # create logger
        self.logger = logging.getLogger('widelands_bot')
        self.logger.setLevel(logging.INFO)
        # create file handler and set level to debug
        fh = logging.FileHandler(
                filename = self.widelands['logging']['filename']
                , encoding = 'utf-8'
                )
        # create formatter
        formatter = logging.Formatter(
                fmt = '%(asctime)s - %(levelname)s:%(message)s'
                , datefmt='%d.%m.%Y %H:%M:%S'
                )
        # add formatter to fh
        fh.setFormatter(formatter)
        # add fh to logger
        self.logger.addHandler(fh)
        self.logLevel = {
            'DEBUG': 10
            , 'INFO': 20
            , 'WARN': 30
            , 'ERROR': 40
            , 'CRITICAL': 50
            }

    def log_to_file(self, level, message):
        if level == 'DEBUG':
            self.logger.debug(message)
        elif level == 'INFO':
            self.logger.info(message)
        elif level == 'WARN':
            self.logger.warning(message)
        elif level == 'ERROR':
            self.logger.error(message)
        elif level == 'CRITICAL':
            self.logger.critical(message)
        else:
            self.logger.critical('Da ging was schief.\n{} gehört hier nicht hin'.format(level))

    def connect_server(self):
        print(colorize("Connecting to {}:{}".format(self.widelands['server']['address'],
            self.widelands['server']['port']), 'brown', 'shell'))

        while not self.connection:
            try:
                self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if self.widelands['server']['ssl']:
                    self.connection = ssl.wrap_socket(self.connection,
                            do_handshake_on_connect=True,
                            suppress_ragged_eofs=True)
                self.connection.connect((self.widelands['server']['address'],
                    self.widelands['server']['port']))
            except socket.gaierror:
                print(colorize("Couldn't resolve server, check your internet connection." \
                       " Re-attempting in 60 seconds.", 'red', 'shell'))
                self.connection = None
                time.sleep(self.widelands['server']['retry'])
            except ConnectionRefusedError:
                print(colorize("Couldn't connect to server, check your internet connection." \
                       " Re-attempting in 60 seconds.", 'red', 'shell'))
                self.connection = None
                time.sleep(self.widelands['server']['retry'])
            except ConnectionResetError:
                print(colorize("Couldn't connect to server, check your internet connection." \
                       " Re-attempting in 60 seconds.", 'red', 'shell'))
                self.connection = None
                time.sleep(self.widelands['server']['retry'])

        self.last_ping = time.time()
        self.start_time = time.time()

        if self.widelands['admin']['debug']:
            self.is_debug = True
            self.update('admin', 'debug', False)

        if self.widelands['server']['sasl'] and self.widelands['server']['ssl']:
            self.post_string('CAP LS 302')

        if not self.widelands['server']['sasl'] and self.widelands['server']['ssl']:
            self.post_string('PASS {}:{}'.format(self.widelands['nickserv']['username'],
                self.widelands['nickserv']['password']))

        self.post_string('NICK {}'.format(self.widelands['nickserv']['username']))
        self.post_string('USER {} {} {} :{}'.format(self.widelands['nickserv']['username'],
            '0', '*', self.widelands['server']['realname']))

    def reconnect(self):
        self.connection.shutdown(2)
        self.connection.close()
        self.connection = None
        self.connect_server()

    def try_ping(self):
        if self.widelands['admin']['debug']:
            self.log_to_file('DEBUG', 'try_ping: {}'.format(time.time()))
        if self.widelands['ping']['use']:
            self.post_string('PING {}'.format(self.widelands['server']['address']))
            self.update('ping', 'pending', True)
        else:
            self.last_pong = time.time()
            self.update('ping', 'pending', False)

    def schedule_message(self, message):
        with self.lock:
            self.queue.put(message)

    def format_content(self, line):
        if self.widelands['admin']['debug']:
            self.log_to_file('DEBUG', "format_content_1: {}".format(line))
        if line.startswith(':'):
            source, line = line[1:].split(' ', 1)
        else:
            source = None
        self.hostname = source

        match = re.match(r'([^!]*)!?([^@]*)@?(.*)', source or '')
        self.name, self.user, self.host = match.groups()
        if not ( self.host or self.user ) and '.' in self.name:
            self.host = self.name
            self.name = ''

        if ' :' in line:
            arguments, text = line.split(' :', 1)
        else:
            arguments, text = line, ''
        arguments = arguments.split(' ', 1)

        if len(arguments) == 1:
            self.command = arguments[0]
            self.target = None
        else:
            self.command = arguments[0]
            self.target = arguments[1]

        self.content = text
        if self.widelands['admin']['debug']:
            self.log_to_file('DEBUG', """format_content_2: hostname: {}
                  name:     {}
                  user:     {}
                  host:     {}
                  command:  {}
                  target:   {}
                  content:  {}""".format(self.hostname
                            , self.name
                            , self.user
                            , self.host
                            , self.command
                            , self.target
                            , self.content))

    def process_line(self, line):
        if len(line) > 0:
            line = line.rstrip('\r\n')
            print('{}: {}'.format(colorize("{} {}".format(time.strftime(self.time_format),
                self.widelands['server']['address']), 'green', 'shell'), line))
            self.format_content(line)

            if self.start_time + 10 < time.time() \
                    and self.widelands['admin']['debug'] \
                    and self.command not in self.command_list:
                self.send_message(line)

            if self.widelands['server']['sasl'] and self.widelands['server']['ssl']:
                if self.command == 'CAP' and 'LS' in self.target and not 'sasl' in self.content:
                    self.update('server', 'sasl', False)
                    self.reconnect()
                    return

                if self.command == 'CAP' and 'sasl' in self.content and 'LS' in self.target:
                    self.post_string('CAP REQ :sasl')

                if self.command == 'CAP' and self.target == '{} ACK'.format(self.widelands['nickserv']['username']):
                    self.post_string('AUTHENTICATE PLAIN')

                if self.command == 'AUTHENTICATE' and self.target == '+':
                    auth = '{benutzer}\0{benutzer}\0{passwort}'.format(
                                    benutzer=self.widelands['nickserv']['username'],
                                    passwort=self.widelands['nickserv']['password'])
                    self.post_string('AUTHENTICATE {}'.format(
                                    base64.b64encode(auth.encode('utf8')).decode('utf8')))

                if self.command == '903' and self.target == self.widelands['nickserv']['username']:
                    self.post_string('CAP END')

                if self.command == '908':
                    self.update('server', 'sasl', False)
                    self.reconnect()

            if self.command == '376':
                if self.is_debug:
                    self.is_debug = False
                    self.update('admin', 'debug', True)
                if len(self.channels) > 0:
                    for channel in self.channels:
                        self.post_string('JOIN {}'.format(channel))
                self.post_string('MODE {} +iw'.format(self.widelands['nickserv']['username']))
                self.send_notice(colorize('IRC bot initialized successfully', 'green', 'irc'))

            if self.command == 'PING':
                self.post_string('PONG {}'.format(self.content))
                self.last_ping = time.time()

            if self.command == 'PONG':
                self.last_ping = time.time()
                self.last_pong = time.time()
                self.update('ping', 'pending', False)

            if self.command == 'KICK' and self.target.split()[1] == self.widelands['nickserv']['username']:
                self.kick_rejoin = time.time()
                self.rejoin_chan = self.target.split()[0]

            if self.kick_rejoin > 0 and self.kick_rejoin + 5 < time.time():
                self.kick_rejoin = 0
                self.post_string('JOIN {}'.format(self.rejoin_chan))
                self.rejoin_chan = None

            if self.command == 'PRIVMSG' and '\x01' not in self.content:
                self.trigger_privmsg()

            if self.command == 'NOTICE' and '\x01' not in self.content:
                self.trigger_notice()

            if self.content.startswith('\x01') and self.content.endswith('\x01'):
                self.content = self.content.strip('\x01')
                self.trigger_ctcp()

    def process_input(self):
        data = self.connection.recv(4096)
        if not data:
            return

        self.buffer += data.decode('utf-8')

        lines = self.buffer.split('\n')
        if self.buffer[-1] == '\n':
            lines.append('')

        for line in lines[:-1]:
            if line:
                self.process_line(line)

        self.buffer = lines[-1]

    def post_string(self, message):
        message = "{}\n".format(message)
        print(colorize('{} {}> {}'.format(time.strftime(self.time_format),
            self.widelands['nickserv']['username'], message[:-1]), 'blue', 'shell'))
        self.last_ping = time.time()
        self.connection.send(message.encode('utf-8'))

    def send_notice(self, message, target=None):
        targets = target if target else self.widelands['channel']['admin']
        self.post_string('NOTICE {} :{}'.format(targets, message))

    def send_message(self, message, target=None):
        targets = target if target else self.widelands['channel']['admin']
        if isinstance(targets, list):
            for target in targets:
                self.post_string('PRIVMSG {} :{}'.format(target, message))
        else:
            self.post_string('PRIVMSG {} :{}'.format(targets, message))

    def stop_loop(self):
        self.quit_loop = True

    def loop(self):
        self.connect_server()
        while not self.quit_loop:
            try:
                to_read, _, _ = select.select([self.connection], [], [], 1)
            except select.error as err:
                print(colorize("Select Error: {}\n\tReconnect...".format(err), 'red', 'shell'))
                self.reconnect()
                continue

            if self.last_pong + self.widelands['ping']['interval'] < time.time() and not self.widelands['ping']['pending']:
                self.try_ping()

            if self.last_ping + self.widelands['ping']['timeout'] < time.time():
                print(colorize("Ping timeout after {} seconds. Reconnect...".format(
                    self.widelands['ping']['timeout']), 'red', 'shell'))
                self.reconnect()
                continue

            if to_read:
                self.process_input()

            with self.lock:
                while not self.queue.empty():
                    self.send_message(self.queue.get(), self.events)
                    self.queue.task_done()

    def __del__(self):
        self.connection.close()
