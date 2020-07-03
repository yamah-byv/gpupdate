#
# GPOA - GPO Applier for Linux
#
# Copyright (C) 2019-2020 BaseALT Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from storage import registry_factory

from .control_applier import control_applier
from .polkit_applier import (
      polkit_applier
    , polkit_applier_user
)
from .systemd_applier import systemd_applier
from .firefox_applier import firefox_applier
from .chromium_applier import chromium_applier
from .cups_applier import cups_applier
from .package_applier import (
      package_applier
    , package_applier_user
)
from .shortcut_applier import (
    shortcut_applier,
    shortcut_applier_user
)
from .gsettings_applier import (
    gsettings_applier,
    gsettings_applier_user
)
from .firewall_applier import firewall_applier
from .folder_applier import (
      folder_applier
    , folder_applier_user
)
from .quota_applier import quota_applier
from .cifs_applier import cifs_applier_user
from util.windows import get_sid
from util.users import (
    is_root,
    get_process_user,
    username_match_uid,
    with_privileges
)
from util.logging import slogm

import logging

def determine_username(username=None):
    '''
    Checks if the specified username is valid in order to prevent
    unauthorized operations.
    '''
    name = username

    # If username is not set then it will be the name
    # of process owner.
    if not username:
        name = get_process_user()
        logging.debug(slogm('Username is not specified - will use username of current process'))

    if not username_match_uid(name):
        if not is_root():
            raise Exception('Current process UID does not match specified username')

    logging.debug(slogm('Username for frontend is set to {}'.format(name)))

    return name

class frontend_manager:
    '''
    The frontend_manager class decides when and how to run appliers
    for machine and user parts of policies.
    '''

    def __init__(self, username, is_machine):
        self.storage = registry_factory('registry')
        self.username = determine_username(username)
        self.is_machine = is_machine
        self.process_uname = get_process_user()
        self.sid = get_sid(self.storage.get_info('domain'), self.username, is_machine)

        self.machine_appliers = dict({
              'control':  control_applier(self.storage)
            , 'polkit':   polkit_applier(self.storage)
            , 'systemd':  systemd_applier(self.storage)
            , 'firefox':  firefox_applier(self.storage, self.sid, self.username)
            , 'chromium': chromium_applier(self.storage, self.sid, self.username)
            , 'shortcuts': shortcut_applier(self.storage)
            , 'gsettings': gsettings_applier(self.storage)
            , 'cups': cups_applier(self.storage)
            , 'firewall': firewall_applier(self.storage)
            , 'folders': folder_applier(self.storage, self.sid)
            , 'quota': quota_applier(self.storage)
            , 'package': package_applier(self.storage)
        })

        # User appliers are expected to work with user-writable
        # files and settings, mostly in $HOME.
        self.user_appliers = dict({
              'shortcuts': shortcut_applier_user(self.storage, self.sid, self.username)
            , 'folders': folder_applier_user(self.storage, self.sid, self.username)
            , 'gsettings': gsettings_applier_user(self.storage, self.sid, self.username)
            , 'cifs': cifs_applier_user(self.storage, self.sid, self.username)
            , 'package': package_applier_user(self.storage, self.sid, self.username)
            , 'polkit': polkit_applier_user(self.storage, self.sid, self.username)
        })

    def machine_apply(self):
        '''
        Run global appliers with administrator privileges.
        '''
        if not is_root():
            logging.error('Not sufficient privileges to run machine appliers')
            return
        logging.debug(slogm('Applying computer part of settings'))
        for applier_name, applier_object in self.machine_appliers.items():
            try:
                applier_object.apply()
            except Exception as exc:
                logging.error('Error occured while running applier {}: {}'.format(applier_name, exc))

    def user_apply(self):
        '''
        Run appliers for users.
        '''
        if is_root():
            for applier_name, applier_object in self.user_appliers.items():
                try:
                    applier_object.admin_context_apply()
                except Exception as exc:
                    logging.error('Error occured while running applier {}: {}'.format(applier_name, exc))

                try:
                    with_privileges(self.username, applier_object.user_context_apply)
                except Exception as exc:
                    logging.error('Error occured while running applier {}: {}'.format(applier_name, exc))
        else:
            for applier_name, applier_object in self.user_appliers.items():
                try:
                    applier_object.user_context_apply()
                except Exception as exc:
                    logging.error('Error occured while running applier {}: {}'.format(applier_name, exc))

    def apply_parameters(self):
        '''
        Decide which appliers to run.
        '''
        if self.is_machine:
            self.machine_apply()
        else:
            self.user_apply()

