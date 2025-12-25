import time
import sys
import re
import os

from distutils.util import strtobool

import ipaddress
# sudo apt install python3-whois
import whois
# sudo apt install python3-cymruwhois
import cymruwhois


def check_if_ip(check):
    try:
        ip = ipaddress.ip_address(check)
        return True
    except ValueError:
        return False
    except:
        return False


class trigger:
    def trigger_notice(self):
        if self.hostname == 'NickServ!NickServ@services.' and self.widelands['nickserv']['replay']:
            self.update('nickserv', 'replay', False)
            self.send_message('NICKSERV: {}'.format(self.content))

    def trigger_ctcp(self):
        content = self.content.split()
        if content[0] == 'ACTION':
            self.send_notice('\x01ACTION {}\x01'.format(' '.join(str(i) for i in content[1:])), self.user)

        if content[0] == 'VERSION':
            self.send_notice('\x01VERSION {}:{}:{}\x01'.format(self.widelands['nickserv']['username'], self.version, os.uname()[0]), self.user)

        if content[0] == 'TIME':
            self.send_notice('\x01TIME {}\x01'.format(time.strftime("%A, %d. %B %Y %H:%M:%S %Z")), self.user)

        if content[0] == 'USERINFO':
            self.send_notice('\x01USERINFO Ich bin ein automatisch denkendes Wesen, auch bekannt als Bot!\x01', self.user)

        if content[0] == 'CLIENTINFO':
            self.send_notice('\x01CLIENTINFP ACTION CLIENTINFO FINGER PING SOURCE TIME URL USERINFO VERSION\x01', self.user)

        if content[0] == 'URL':
            self.send_notice('\x01URL Frag den janus im freenode\x01', self.user)

        if content[0] == 'SOURCE':
            self.send_notice('\x01SOURCE Frag den janus im freenode\x01', self.user)

        if content[0] == 'PING':
            if len(content) > 1:
                self.send_notice('\x01PING {}\x01'.format(' '.join(str(i) for i in content[1:])), self.user)

        if content[0] == 'FINGER':
            self.send_notice('\x01FINGER Du nicht nehmen Kerze! You don\'t take candle!\x01', self.user)

    def trigger_admin(self):
        content = self.content.split()
        if content[1] == 'debug':
            if len(content) == 2:
                self.send_message("Debug: {}".format("AN" if self.widelands['admin']['debug'] else "AUS"), self.target)
            elif len(content) >= 3:
                try:
                    self.update('admin', 'debug', bool(strtobool(content[2])))
                    self.send_message("Debug: {}".format("AN" if self.widelands['admin']['debug'] else "AUS"), self.target)
                except ValueError as Error:
                    self.send_message("Debug: {}".format(Error))

        if content[1] == 'ping':
            if len(content) == 2:
                self.send_message("PING: {}".format("AN" if self.widelands['ping']['use'] else "AUS"), self.target)
            elif len(content) >= 3:
                try:
                    self.update('ping', 'use', bool(strtobool(content[2])))
                    self.send_message("PING: {}".format("AN" if self.widelands['ping']['use'] else "AUS"), self.target)
                except ValueError as Error:
                    self.send_message("PING: {}".format(Error))

        if content[1] == 'channel':
            if len(content) == 2:
                if len(self.channels) > 0:
                    self.send_message('Ich bin in {}.'.format(', '.join(self.channels)), self.target)
            else:
                if content[2] == 'join':
                    if len(content) == 4 and content[3].startswith('#'):
                        self.post_string('JOIN {}'.format(content[3]))
                        self.channels.append(content[3])
                        self.update('channel', 'liste', self.channels)
                if content[2] == 'part':
                    if len(content) == 4 and content[3].startswith('#'):
                        if content[3] in self.channels:
                            self.post_string('PART {}'.format(content[3]))
                            self.channels.remove(content[3])
                            self.update('channel', 'liste', self.channels)
                        else:
                            self.send_message('{} ist mir nicht bekannt!'.format(content[3]), self.target)

        if content[1] == 'reconnect':
            self.send_message('Try to reconnect', self.target)
            self.reconnect()

        if content[1] == 'logging':
            if len(content) == 2:
                self.send_message('Aktuelles Log Level ist: {}'.format(self.logger.getEffectiveLevel()), self.target)
            elif len(content) == 3:
                self.logger.setLevel(self.logLevel[content[2].upper()])
                self.send_message('Log Level {} wurde gesetzt'.format(self.logger.getEffectiveLevel()), self.target)

        if content[1] == 'event':
            if len(content) == 2:
                if len(self.events) > 0:
                    self.send_message('Ich gebe in {} wieder.'.format(', '.join(self.events)), self.target)
                else:
                    self.send_message('Ich gebe in keinem Kanal wieder', self.target)
            else:
                if content[2] == 'join':
                    if len(content) == 4 and content[3].startswith('#'):
                        self.events.append(content[3])
                        self.update('channel', 'event', self.events)
                if content[2] == 'part':
                    if len(content) == 4 and content[3].startswith('#'):
                        if content[3] in self.events:
                            self.events.remove(content[3])
                            self.update('channel', 'event', self.events)
                        else:
                            self.send_message('{} ist mir nicht bekannt!'.format(content[3]), self.target)


    def trigger_nickserv(self):
        content = self.content.split()
        if content[1] == "register":
            self.send_message('REGISTER {} {}'.format(self.widelands['nickserv']['password'],
                self.widelands['nickserv']['email']), 'NICKSERV')

        if content[1] == "verify":
            self.send_message('VERIFY REGISTER {} {}'.format(self.widelands['nickserv']['username'],
                content[2]), 'NICKSERV')

        if content[1] == "identify":
            self.send_message('IDENTIFY {} {}'.format(self.widelands['nickserv']['username'],
                self.widelands['nickserv']['password']), 'NICKSERV')

        if content[1] == "status":
            self.update('nickserv', 'replay', True)
            self.send_message('STATUS', 'NICKSERV')

    def trigger_privmsg(self):
        content = self.content.split()
        if not re.search('^s\/', self.content, re.IGNORECASE):
            """
            für später, als überlegung, todo
            einem namen pro kanal das letzte statement
            * Methode 1:
              self.backlog.setdefault(self.name, {})[self.target] = self.content
            * Methode 2:
              from collections import defaultdict
              self.backlog = defaultdict(dict)
              self.backlog[self.name][self.target] = self.content
            """
            self.backlog[self.name] = self.content

        if self.target == "#widelands" and ' '.join(content[1:]) == "has joined the lobby.":
            with open(self.widelands['channel']['welcome']) as gct:
                content_gct = gct.readlines()
                self.send_message(content_gct[0].format(content[0]), self.target)
            #pass

        if self.hostname == self.widelands['admin']['hosts']:
            if re.search('^nickserv', self.content, re.IGNORECASE):
                self.trigger_nickserv()
            if re.search('^admin', self.content, re.IGNORECASE):
                if len(content) >= 2:
                    self.trigger_admin()
                else:
                    self.send_message("Hier sollte was stehen", self.target)

        if re.search('^s\/', self.content, re.IGNORECASE):
            content_neu = self.backlog[self.name]
            for step in self.content.split(";"):
                msg = ''
                if len(step.split("/")) == 4:
                    _, muster, ersatz, count = step.split("/")
                    try:
                        count = int(count) if count != '' else 0
                    except:
                        msg = f'"{count}" muss irgendwie einer Zahl nahe kommen!'
                elif len(step.split("/")) == 3:
                    _, muster, ersatz = step.split("/")
                    count = 0
                else:
                    msg = 'Da fehlt was! Nur was?'

                if msg:
                    self.send_message(f'Error: {msg}', self.target)
                else:
                    content_neu = re.sub(re.escape(muster), ersatz, content_neu, count)

            if content_neu != self.backlog[self.name]:
                self.send_message(f'{self.name} meinte: {content_neu}', self.target)
            else:
                self.send_message('Info: Es hat sich nichts geändert.', self.target)

        if re.search('^whois', self.content, re.IGNORECASE):
            string = ' '.join(content[1:])
            if check_if_ip(string):
                whois_ip = cymruwhois.Client()
                lookup = whois_ip.lookup(string)
                self.send_message(f'ASN:     {lookup.asn}', self.target)
                self.send_message(f'Prefix:  {lookup.prefix}', self.target)
                self.send_message(f'IP:      {lookup.ip}', self.target)
                self.send_message(f'Country: {lookup.cc}', self.target)
                self.send_message(f'Owner:   {lookup.owner}', self.target)
            else:
                try:
                    domain = whois.query(string)
                    #domain_name = domain.name
                    self.send_message(f'Name:      {domain.name}', self.target)
                    self.send_message(f'Registrar: {domain.registrar}', self.target)
                    self.send_message(f'Expire:    {domain.expiration_date}', self.target)
                except Exception as e:
                    self.send_message(f'Error: {e}', self.target)

        if self.content.find('{}ping'.format(self.trigger)) == 0 \
                or re.search('^ping {}'.format(self.widelands['nickserv']['username']), self.content, re.IGNORECASE):
            self.send_message('pong {}'.format(self.name), self.target)

