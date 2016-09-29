# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Hewlett Packard Enterprise Development LP
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
topology_connect shell management module.
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from os import getuid
from pwd import getpwuid
from logging import getLogger
from os.path import isabs, join, expanduser
from subprocess import call
from time import sleep

from topology.platforms.shell import PExpectShell, PExpectBashShell


log = getLogger(__name__)

class ConnectPExpectShell(PExpectShell):
    def __init__(self, *args, **kwargs):
        super(ConnectPExpectShell, self).__init__(*args, **kwargs)

        # Clearing values below to don't invoke user, password and
        # initial command cases in connect() method in parent class.
        self._user = None
        self._password = None
        self._initial_command = None

        # Defining our user, password and initial command values to
        # handle tham manually in our _setup_shell() method.
        self._connect_user = kwargs.get('user', None)
        self._connect_password = kwargs.get('password', None)
        self._connect_initial_command = kwargs.get('initial_command', None)

    def _setup_shell(self, connection=None):
        # Setup shell before authentication
        self._pre_setup_shell(connection)

        spawn = self._get_connection(connection)
        # If connection is via user
        if self._connect_user is not None:
            index = spawn.expect(
                [self._user_match,
                 self._initial_prompt,
                 self._password_match],
                timeout=self._timeout
            )
            if 0 == index:
                # Entering user name
                spawn.sendline(self._connect_user)
            elif 1 == index:
                # We already made authentication by passing user as
                # part of connect command: 'user@server'
                spawn.send('\n\r')
            elif 2 == index:
                # User name was specified as part of part of connect
                # command 'user@server'. So, need to provide password
                spawn.sendline(self._connect_password)
            else:
                # We should not go here as timeout exception in this case
                # will be raised
                pass

        # If connection is via password
        if self._connect_password is not None:
            index = spawn.expect(
                [self._password_match, self._initial_prompt],
                timeout=self._timeout
            )
            if 0 == index:
                spawn.sendline(self._connect_password)
            else:
                spawn.send('\n\r')

        # Setup shell before using it
        self._post_setup_shell(connection)

        # Execute initial command if required
        if self._connect_initial_command is not None:
            spawn.expect(
                self._initial_prompt, timeout=self._timeout
            )
            spawn.sendline(self._connect_initial_command)

    def _pre_setup_shell(self, connection=None):
        """
        Method called by subclasses that will be triggered before matching the
        initial prompt.

        :param str connection: Name of the connection to be set up. If not
         defined, the default connection will be set up.
        """

    def _post_setup_shell(self, connection=None):
        """
        Method called by subclasses that will be triggered before
        authentication, means matching the user and password prompt.

        :param str connection: Name of the connection to be set up. If not
         defined, the default connection will be set up.
            """

class ConnectPExpectBashShell(PExpectBashShell, ConnectPExpectShell):
    def __init__(self, *args, **kwargs):
        super(ConnectPExpectBashShell, self).__init__(*args, **kwargs)

        # Clearing values below to don't invoke user, password and
        # initial command cases in connect() method in parent class.
        self._user = None
        self._password = None
        self._initial_command = None

        # Defining our user, password and initial command values to
        # handle tham manually in our _setup_shell() method.
        self._connect_user = kwargs.get('user', None)
        self._connect_password = kwargs.get('password', None)
        self._connect_initial_command = kwargs.get('initial_command', None)

    def _post_setup_shell(self, connection=None):
        super(ConnectPExpectBashShell, self)._setup_shell(connection)

    def _setup_shell(self, connection=None):
        ConnectPExpectShell._setup_shell(self, connection)


class SshMixin(object):
    """
    SSH connection mixin for the Topology shell API.

    This class implements a ``_get_connect_command()`` method that allows to
    interact with a shell through an SSH session, and extends the constructor
    to request for SSH related connection parameters.

    The default options will assume that you will be connecting using a SSH
    key (and you seriously SHOULD). If, for some reason, you MUST use a
    password to connect to the shell in question (and DON'T unless absolutely
    required! Like, really, really, DO NOT!) you must set the ``identity_file``
    to ``None`` and set the options to at least have ``BatchMode=no``. Also,
    as expected by the Topology shell low level API you must pass the
    ``password`` (and ``password_match`` if required) to the constructor.

    Note: The constructor of this class should look as follow::

        # Using PEP 3102 -- Keyword-Only Arguments
        def __init__(
            self, *args,
            user=None, hostname='127.0.0.1', port=22,  # noqa
            options=('BatchMode=yes', ), identity_file='id_rsa',
            **kwargs):

    Sadly, this is Python 3 only. Python 2.7 didn't backported this feature.
    So, this is the legacy way to achieve the same goal. Awful, I know :/

    :param str user: User to connect with. If ``None``, the user running the
     process will be used.
    :param str hostname: Hostname or IP to connect to.
    :param int port: SSH port to connect to.
    :param tuple options: SSH options to use.
    :param str identity_file: Absolute or relative (in relation to ``~/.ssh/``)
     path to the private key identity file. If ``None`` is provided, key based
     authentication will not be used.
    """
    def __init__(self, *args, **kwargs):
        self._ssh_user = kwargs.get('user', None)
        self._hostname = kwargs.pop('hostname', '127.0.0.1')
        self._port = kwargs.pop('port', 22)
        self._options = kwargs.pop('options', ('BatchMode=yes', ))
        self._identity_file = kwargs.pop('identity_file', 'id_rsa')

        # Use current user if not specified
        if self._ssh_user is None:
            self._ssh_user = SshMixin.get_username()

        # Provide a sensible default for the identity file
        if self._identity_file is not None and not isabs(self._identity_file):
            self._identity_file = join(
                expanduser('~/.ssh/'), self._identity_file
            )

        super(SshMixin, self).__init__(*args, **kwargs)

    @staticmethod
    def get_username():
        """
        Get the username.

        :return: The user currently running the process.
        :rtype: str
        """
        return getpwuid(getuid()).pw_name

    def _get_connect_command(self):
        """
        Implementation of the private method defined by the PExpectShell class
        to define the connection command.

        :return: The command that will be used to launch the shell process.
        :rtype: str
        """

        options = ''
        if self._options:
            options = ' -o {}'.format(' -o '.join(self._options))

        if self._identity_file:
            options = ' -i {}{}'.format(self._identity_file, options)

        connect_command = (
            'ssh {self._ssh_user}@{self._hostname} '
            '-p {self._port}{options}'.format(
                **locals()
            )
        )
        return connect_command


class TelnetMixin(object):
    """
    Telnet connection mixin for the Topology shell API.

    Note: The constructor of this class should look as follow::

        # Using PEP 3102 -- Keyword-Only Arguments
        def __init__(
            self, *args,
            hostname='127.0.0.1', port=23,
            **kwargs):

    Sadly, this is Python 3 only. Python 2.7 didn't backported this feature.
    So, this is the legacy way to achieve the same goal. Awful, I know :/

    :param str hostname: Hostname or IP to connect to.
    :param int port: Telnet port to connect to.
    """
    def __init__(self, *args, **kwargs):
        self._hostname = kwargs.pop('hostname', '127.0.0.1')
        self._port = kwargs.pop('port', 23)

        super(TelnetMixin, self).__init__(*args, **kwargs)

    def _get_connect_command(self):
        """
        Implementation of the private method defined by the PExpectShell class
        to define the connection command.

        :return: The command that will be used to launch the shell process.
        :rtype: str
        """
        connect_command = (
            'telnet {self._hostname} {self._port}'.format(
                **locals()
            )
        )
        return connect_command


class SshShell(SshMixin, ConnectPExpectShell):
    """
    Simple class mixing the pexcept based shell with the SSH mixin.
    """


class TelnetShell(TelnetMixin, ConnectPExpectShell):
    """
    Simple class mixing the pexcept based shell with the Telnet mixin.
    """


class SshBashShell(SshMixin, ConnectPExpectBashShell):
    """
    Simple class mixing the Bash specialized pexcept based shell with the SSH
    mixin.
    """


class TelnetBashShell(TelnetMixin, ConnectPExpectBashShell):
    """
    Simple class mixing the Bash specialized pexcept based shell with the
    Telnet mixin.
    """

class OpenswitchVtyShell(SshShell):
    def __init__(self, **kwargs):
        _user = kwargs.get('user', None)

        _initial_prompt = '{}@.+:~# '.format(_user)
        _vtysh_prompt   = '[\w,-]*(switch)\d*(\(.+\))?# '

        super(OpenswitchVtyShell, self).__init__(initial_prompt = _initial_prompt,
                                                 prompt  = _vtysh_prompt,
                                                 initial_command = 'vtysh',
                                                 **kwargs)

    def _post_setup_shell(self, connection=None):
        """
        Overriden setup function that set a pexpect-safe prompt for vtysh shell.
        """
        return
        # TODO
        #
        # Planned to set prompt by executing 'hostname' command and using
        # switch hostname to make 100% the same prompt match as real switch prompt.
        # But 1 of 10 times switch returns incorrect prompt as
        # all appropriate system daemons haven't started yet.
        # Need to additionally implement to wait when switch will be 100% ready.
        spawn = self._get_connection(connection)
        spawn.sendline('')

        # Wait initial prompt
        spawn.expect(
            self._initial_prompt, timeout=self._timeout
        )

        spawn.sendline('hostname')
        spawn.expect(
            self._initial_prompt, timeout=self._timeout
        )
        _hostname = self.get_response()

        self._prompt = '{}(\(.+\))?# '.format(_hostname)
        spawn.sendline('')

class OpenswitchSerialShell(ConnectPExpectShell):
    def __init__(self, **kwargs):
        self._user = kwargs.get('user', None)
        self._user_match = kwargs.get('user_match', None)
        self._serial_command = kwargs.pop('serial_command', None)
        self._bootup_timeout  = int(kwargs.pop('bootup_timeout', '0'))
        self._pre_connect_timeout = int(kwargs.pop('pre_connect_timeout', '0'))
        self._serial_closing_commands = kwargs.pop('closing_commands', {})

        self._onie_prompt = 'ONIE:/ # '
        self._serial_onie_activate_prompt = 'Please press Enter to activate this console. '
        self._vtysh_prompt = '\w+(\(.+\))?# '
        self._serial_prompt = '{}@.+:~# '.format(self._user)

        super(OpenswitchSerialShell, self).__init__(prompt = self._serial_prompt,
                                                    **kwargs)

    def disconnect(self, connection=None):
        """
        See :meth:`BaseShell.disconnect` for more information.
        """
        # Get connection
        spawn = self._get_connection(connection)
        if not spawn.isalive():
            raise AlreadyDisconnectedError(connection)
        self._close_serial_connection()
        spawn.close()

    def _close_serial_connection(self):
        for command in self._serial_closing_commands:
            spawn.send(command)

    def setPromt(self, _promt):
        self._prompt = _promt

    def _get_connect_command(self):
        return self._serial_command

    def _pre_setup_shell(self, connection=None):
        """
        See :meth:`BaseShell.connect` for more information.
        """

        spawn = self._get_connection(connection)

        # Wait for console connecting timeout
        if self._pre_connect_timeout is not None:
            sleep(self._pre_connect_timeout)

        # Checking in what state switch serial console is
        index = self.send_command('\n\r', # Pressing Enter
                                  matches = [self._user_match,
                                             self._onie_prompt,
                                             self._serial_prompt,
                                             self._vtysh_prompt],
                                  timeout = self._bootup_timeout,
                                  newline = False
                                  )

        if 0 == index: # We are in login prompt, which we require
            spawn.send('\n\r')
        elif 1 == index: # We are in ONIE
            spawn.sendline('reboot')
            sleep(self._bootup_timeout)
        elif 2 == index: # We are in already authenticated prompt, exiting
            spawn.sendcontrol('d')
        elif 3 == index: # We are in vtysh, exiting from it
            spawn.sendcontrol('d')
            spawn.sendcontrol('d')

    def get_response(self, connection=None, silent=False):
        try:
            return super(OpenswitchSerialShell, self).get_response( \
                connection,silent)
        except:
            # TODO
            # While reloading DUT a lot of special console symbols are printed.
            # And usually spawn.before.decode(self._encoding) will raise
            # an expection that failed to decode the text.
            # For now just returning as is. However need more proper
            # handling this case.
            spawn = self._get_connection(connection)
            return spawn.before
__all__ = [
    'SshMixin', 'TelnetMixin',
    'SshShell', 'TelnetShell',
    'SshBashShell', 'TelnetBashShell',
    'OpenswitchVtyShell', 'OpenswitchSerialShell',
    'ConnectPExpectShell'
]
