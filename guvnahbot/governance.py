#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Work with the governance repository.

Adapted and heavily in debt to the openstack/releases governance.py source."""

import requests
import weakref

from guvnahbot import wiki
from guvnahbot import yamlutils


PROJECTS_LIST = "http://git.openstack.org/cgit/openstack/governance/plain/reference/projects.yaml"  # noqa


def get_team_data(url=PROJECTS_LIST):
    """Return the parsed team data from the governance repository.

    :param url: Optional URL to the location of the projects.yaml
        file. Defaults to the most current version in the public git
        repository.
    """
    r = requests.get(url)
    return yamlutils.loads(r.text)


def get_tags_for_deliverable(team_data, team, name):
    """Return the tags for the deliverable owned by the team."""
    if team not in team_data:
        return set()
    team_info = team_data[team]
    dinfo = team_info['deliverables'].get(name)
    if not dinfo:
        return set()
    return set(dinfo.get('tags', [])).union(set(team_info.get('tags', [])))


def get_repo_owner(team_data, repo_name):
    """Return the name of the team that owns the repository.

    :param team_data: The result of calling :func:`get_team_data`
    :param repo_name: Long name of the repository, such as 'openstack/nova'.
    """
    for team, info in team_data.items():
        for dname, dinfo in info.get('deliverables', {}).items():
            if repo_name in dinfo.get('repos', []):
                return team
    raise ValueError('Repository %s not found in governance list' % repo_name)


class Team(object):
    _liaison_data = None

    def __init__(self, name, data):
        self.name = name
        self.data = data
        # Protectively initialize the ptl data structure in case part
        # of it is missing from the project list, then replace any
        # values we do have from that data.
        self.ptl = {
            'name': 'MISSING',
            'irc': 'MISSING',
        }
        self.ptl.update(data.get('ptl', {}))
        self.irc_channel = '#%s' % data.get('irc-channel', '#UNKNOWN##')
        self.mission = data.get('mission', '')
        self.deliverables = {
            dn: Deliverable(dn, di, self)
            for dn, di in self.data.get('deliverables', {}).items()
        }

    @property
    def tags(self):
        return set(self.data.get('tags', []))

    @property
    def liaison(self):
        if self._liaison_data is None:
            # Only hit the wiki page one time.
            Team._liaison_data = wiki.get_liaison_data()
        team_liaison = self._liaison_data.get(self.name.lower(), {})
        return (team_liaison.get('Liaison'),
                team_liaison.get('IRC Handle'))


class Deliverable(object):
    def __init__(self, name, data, team):
        self.name = name
        self.data = data
        self.team = weakref.proxy(team)
        self.repositories = {
            rn: Repository(rn, self)
            for rn in self.data.get('repos', [])
        }

    @property
    def type(self):
        for t in self.tags:
            if t.startswith('type:'):
                return t.partition(':')[-1]
        return 'other'

    @property
    def model(self):
        for t in self.tags:
            if t.startswith('release:'):
                return t.partition(':')[-1]
        return 'none'

    @property
    def tags(self):
        return set(self.data.get('tags', [])).union(self.team.tags)


class Repository(object):
    def __init__(self, name, deliverable):
        self.name = name
        self.deliverable = weakref.proxy(deliverable)

    @property
    def tags(self):
        return self.deliverable.tags

    @property
    def code_related(self):
        return not (self.name.endswith('-specs') or
                    'cookiecutter' in self.name)


def get_repositories(team_data, team_name=None, deliverable_name=None,
                     tags=[], code_only=False):
    """Return a sequence of repositories, possibly filtered.

    :param team_data: The result of calling :func:`get_team_data`
    :param team_name: The name of the team owning the repositories. Can be
        None.
    :para deliverable_name: The name of the deliverable to which all
       repos should belong.
    :param tags: The names of any tags the repositories should
        have. Can be empty.
    :param code_only: Boolean indicating whether to return only code
      repositories (ignoring specs and cookiecutter templates).
    """
    if tags:
        tags = set(tags)
    if team_name:
        try:
            teams = [Team(team_name, team_data[team_name])]
        except KeyError:
            raise RuntimeError('No team %r found in %r' %
                               (team_name, list(team_data.keys())))
    else:
        teams = [Team(n, i) for n, i in team_data.items()]
    for team in teams:
        if deliverable_name and deliverable_name not in team.deliverables:
            continue
        if deliverable_name:
            deliverables = [team.deliverables[deliverable_name]]
        else:
            deliverables = team.deliverables.values()
        for deliverable in deliverables:
            for repository in deliverable.repositories.values():
                if tags and not tags.issubset(repository.tags):
                    continue
                if code_only and not repository.code_related:
                    continue
                yield repository
