# -*- coding: utf-8 -*-
# All rights reserved
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

"""Bot for providing governance and release information.

Largely based on the OpenStack PTGBot.
"""

import argparse
import collections
import daemon
import irc.bot
import json
import logging.config
import os
import time
import ssl
import textwrap

from guvnahbot import governance

try:
    import daemon.pidlockfile as pid_file_module
except ImportError:
    # as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
    # instead it depends on lockfile-0.9.1
    import daemon.pidfile as pid_file_module

irc.client.ServerConnection.buffer_class.errors = 'replace'
# If a long message is split, how long to sleep between sending parts
# of a message.  This is lower than the general recommended interval,
# but in practice freenode allows short bursts at a higher rate.
MESSAGE_CONTINUATION_SLEEP = 0.5
# The amount of time to sleep between messages.
ANTI_FLOOD_SLEEP = 2
ACTIONS = ['?PTL', '?REPOS', '?CHANNEL', '?MISSION', '?TAGS', '?WHOIS']


class GuvnahBot(irc.bot.SingleServerIRCBot):
    log = logging.getLogger("guvnahbot.bot")

    def __init__(self, nickname, password, server, port, channels):
        if port == 6697:
            factory = irc.connection.Factory(wrapper=ssl.wrap_socket)
            irc.bot.SingleServerIRCBot.__init__(self,
                                                [(server, port)],
                                                nickname, nickname,
                                                connect_factory=factory)
        else:
            irc.bot.SingleServerIRCBot.__init__(self,
                                                [(server, port)],
                                                nickname, nickname)
        self.nickname = nickname
        self.password = password
        self.chans = channels.split(',')
        self.identify_msg_cap = False
        self.team_data = governance.get_team_data()

    def on_nicknameinuse(self, c, e):
        self.log.debug("Nickname in use, releasing")
        c.nick(c.get_nickname() + "_")
        c.privmsg("nickserv", "identify %s " % self.password)
        c.privmsg("nickserv", "ghost %s %s" % (self.nickname, self.password))
        c.privmsg("nickserv", "release %s %s" % (self.nickname, self.password))
        time.sleep(ANTI_FLOOD_SLEEP)
        c.nick(self.nickname)

    def on_welcome(self, c, e):
        self.identify_msg_cap = False
        self.log.debug("Requesting identify-msg capability")
        c.cap('REQ', 'identify-msg')
        c.cap('END')
        if (self.password):
            self.log.debug("Identifying to nickserv")
            c.privmsg("nickserv", "identify %s " % self.password)
        for channel in self.chans:
            self.log.info("Joining %s" % channel)
            c.join(channel)
        time.sleep(ANTI_FLOOD_SLEEP)

    def on_cap(self, c, e):
        self.log.debug("Received cap response %s" % repr(e.arguments))
        if e.arguments[0] == 'ACK' and 'identify-msg' in e.arguments[1]:
            self.log.debug("identify-msg cap acked")
            self.identify_msg_cap = True

    def usage(self, channel):
        self.send(channel, "Available actions are ?PTL|?REPOS|?CHANNEL|"
                           "?MISSION|?TAGS|?WHOIS")

    def send_ptl_liaison(self, channel, team_name):
        """Send the PTL for a team and liaison if available."""
        try:
            team_name = governance.get_repo_owner(self.team_data, team_name)
        except ValueError:
            pass
        team_dict = self.team_data.get(team_name)
        team = governance.Team(team_name, team_dict)
        self.send(channel, '%s PTL: %s (%s)' % (team_name.title(),
                                                team.ptl['name'],
                                                team.ptl['irc']))
        if 'release' in channel:
            l_name, l_irc = team.liaison
            if l_name:
                self.send(channel, '%s Liaison: %s (%s)' % (team_name.title(),
                                                            l_name,
                                                            l_irc))

    def send_repos(self, channel, team_name):
        """Send the repos for a team."""
        self.send(channel, '%s repos:' % team_name.title())
        for repo in governance.get_repositories(self.team_data, team_name):
            self.send(channel, '        %s' % repo.name)

    def send_channel(self, channel, team_name):
        """Sends the IRC channel used by a team."""
        try:
            team_name = governance.get_repo_owner(self.team_data, team_name)
        except ValueError:
            pass
        team_dict = self.team_data.get(team_name)
        team = governance.Team(team_name, team_dict)
        self.send(channel, '%s uses IRC channel %s' % (team_name.title(),
                                                       team.irc_channel))

    def send_mission(self, channel, team_name):
        """Sends the mission statement of a team."""
        team_dict = self.team_data.get(team_name)
        team = governance.Team(team_name, team_dict)
        self.send(channel, "%s's mission statement is: %s" % (
            team_name.title(), team.mission))

    def send_tags(self, channel, team_or_repo):
        """Sends the tags of a team."""
        tags = set()
        team_name = team_or_repo
        try:
            team_name = governance.get_repo_owner(self.team_data, team_or_repo)
            tags = governance.get_tags_for_deliverable(self.team_data,
                                                       team_name,
                                                       team_or_repo)
        except ValueError:
            pass
        else:
            team_dict = self.team_data.get(team_name)
            team = governance.Team(team_name, team_dict)
            tags = team.tags

        self.send(channel, "%s asserts tags: %s" % (
            team_name.title(), tags))

    def send_whois(self, channel, repo_name):
        """Sends the team that owns a repo."""
        try:
            team_name = governance.get_repo_owner(self.team_data, repo_name)
            self.send(channel, '%s is owned by %s' % (repo_name, team_name))
        except ValueError:
            self.send(channel,
                      'Error getting whois. Is %s a repo?' % repo_name)

    def on_pubmsg(self, c, e):
        if not self.identify_msg_cap:
            self.log.debug("Ignoring message because identify-msg "
                           "cap not enabled")
            return
        # nick = e.source.split('!')[0]
        msg = e.arguments[0][1:]
        chan = e.target

        if msg.startswith('?'):
            words = msg.split()
            if len(words) < 2 and words[0] == '??':
                self.usage(chan)
                return

            action = words[0].lower()
            team_or_repo = words[1].lower()
            if action == '?ptl':
                self.send_ptl_liaison(chan, team_or_repo)
            elif action == '?repos':
                self.send_repos(chan, team_or_repo)
            elif action == '?channel':
                self.send_channel(chan, team_or_repo)
            elif action == '?mission':
                self.send_mission(chan, team_or_repo)
            elif action == '?tags':
                self.send_tags(chan, team_or_repo)
            elif action == '?whois':
                self.send_whois(chan, team_or_repo)

    def send(self, channel, msg):
        # 400 chars is an estimate of a safe line length (which can vary)
        chunks = textwrap.wrap(msg, 400)
        if len(chunks) > 10:
            raise Exception("Unusually large message: %s" % (msg,))
        for count, chunk in enumerate(chunks):
            self.connection.privmsg(channel, chunk)
            if count:
                time.sleep(MESSAGE_CONTINUATION_SLEEP)
        time.sleep(ANTI_FLOOD_SLEEP)


def start(configpath):
    with open(configpath, 'r') as fp:
        config = json.load(fp, object_pairs_hook=collections.OrderedDict)

    if 'log_config' in config:
        log_config = config['log_config']
        fp = os.path.expanduser(log_config)
        if not os.path.exists(fp):
            raise Exception("Unable to read logging config file at %s" % fp)
        logging.config.fileConfig(fp)
    else:
        logging.basicConfig(level=logging.DEBUG)

    bot = GuvnahBot(config['irc_nick'],
                    config.get('irc_pass', ''),
                    config['irc_server'],
                    config['irc_port'],
                    config['irc_channels'])
    bot.start()


def main():
    parser = argparse.ArgumentParser(description='Governance info bot.')
    parser.add_argument('configfile', help='specify the config file')
    parser.add_argument('-d', dest='nodaemon', action='store_true',
                        help='do not run as a daemon')
    args = parser.parse_args()

    if not args.nodaemon:
        pid = pid_file_module.TimeoutPIDLockFile(
            "/var/run/guvnahbot/guvnahbot.pid", 10)
        with daemon.DaemonContext(pidfile=pid):
            start(args.configfile)
    start(args.configfile)


if __name__ == "__main__":
    main()
