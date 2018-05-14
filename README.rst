===================
Governance Info Bot
===================

This is a helper bot to easily get governance information from within IRC. By
requesting certain tags from the bot, it can look up the information from
various sources and report it back in the IRC channel.

Governance info commands
========================

Here is a list of the currently supported commands.

?PTL [team or repo]
-------------------

This will look up the PTL for a given team. If a repo is provided (for example:
?PTL openstack/python-cinderclient) it will first look up the owning team of
the repo, then report that PTL of that team.

If run in the #openstack-release IRC channel, this will also look up and report
the designated release liaison for the team.

?REPOS [team]
-------------

This command will report all repos owned by the team.

?CHANNEL [team]
---------------

This will report the official IRC channel used by the team.

?MISSION [team]
---------------

This command will report the mission statement of a team.

?TAGS [repo]
------------

This will report the governance tags asserted by the team repo.


?WHOIS [repo]
-------------

The reverse of ?REPOS, this will look up which team owns a given repo.

Local testing
=============

Copy config.json.sample to config.json::

  cp config.json.sample config.json

Edit config.json contents, for example::

  {
  "irc_nick": "guvnah",
  "irc_pass": "",
  "irc_server": "irc.freenode.net",
  "irc_port": 6667,
  "irc_channels: "#openstack-tc,#openstack-release",
  }

In one terminal, run the bot::

  tox -evenv -- ptgbot -d config.json

Join that channel and give commands to the bot::

  ~add swift
  #swift now discussing ring placement

(note, the bot currently only takes commands from Freenode identified users)

In another terminal, start the webserver::

  cd html && python -m SimpleHTTPServer

Open the web page in a web browser: http://127.0.0.1:8000/ptg.html
