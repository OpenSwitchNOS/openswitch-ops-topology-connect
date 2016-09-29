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
topology_connect base node module.
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from logging import getLogger
import time
import re

from ..node import CommonConnectNode
from ..shell import SshBashShell


log = getLogger(__name__)


class HostNode(CommonConnectNode):
    """
    FIXME: Document.
    """
    _intf_settings = {}
    _valid_attrs = {'+type': 'host',
                     '+IP': '.+',
                     '+user': '.*',
                     'password': '.*',
                     'interfaces': {
                         None: {
                             '+name': '\w+',
                             'speed': '\d+',
                             'bring_intf_up_timeout': '\d+',
                             'clear_config': 'true|false'
                             }
                         }
                     }

    def __init__(self, identifier, **kwargs):
        self._IP = kwargs.get('IP', None)
        user = kwargs.get('user', None)
        password = kwargs.get('password', None)
        self._intf_settings = kwargs.get('interfaces', '')

        if password is None:
            kwargs['password'] = None

        super(HostNode, self).__init__(identifier, **kwargs)
        self._register_shell(
            'bash',
            SshBashShell(
                hostname=self._IP,
                identity_file=None,
                options=('BatchMode=no',
                         'StrictHostKeyChecking=no'),
                initial_prompt='\w+@.+[#$] ',
                **kwargs)
            )

    def bring_port_up(self, biport):
        """
        Method to bring interface up
        """
        intf_config, real_label, label = self._get_interface_config(biport)
        print('\nHost \'{}\', interface \'{}\'(real name \'{}\'): bringing interface up'.format(
            self.identifier, label, real_label))
        bash = self.get_shell('bash')
        bash('ifconfig {} up'.format(real_label))

        return real_label

    def wait_port_becomes_up(self, biport):
        iter = 0
        port_is_up = False
        intf_config, real_label, label = self._get_interface_config(biport)
        print('\nHost \'{}\', interface \'{}\'(real name \'{}\'): ' \
            'Waiting when interface will be up'.format( \
            self.identifier, label, real_label), end='', flush=True)
        bring_intf_up_timeout = int(intf_config.get('bring_intf_up_timeout',30))

        bash = self.get_shell('bash')
        while iter < bring_intf_up_timeout:
            print('.', end='', flush=True)
            out = bash('ip link show '+ real_label)
            if ' state UP ' in out:
                port_is_up = True
                break;
            iter += 1
            time.sleep(1)
        assert port_is_up,'\nHost \'{}\', interface \'{}\'(real name \'{}\'):'\
            'couldn\'t bring interface UP'.format(self.identifier, label, \
                                                  real_label)
        print('done\n', end='', flush=True)

    def _get_supported_attributes(self):
        return self._valid_attrs

    def _get_interface_config(self, biport):
        intf_label = biport.metadata.get('label', \
                                         biport.identifier.split('-')[1])
        assert intf_label in self._intf_settings, \
        'Node {}: unknown interface \'{}\''.format(self.identifier, intf_label)
        intf_config = self._intf_settings[intf_label]
        real_name = intf_config.get('name', intf_label)

        return intf_config, real_name, intf_label

    def clear_config(self):
        print('\nHost {}: clearing configuration'.format(self.identifier))
        bash = self.get_shell('bash')

        #Remove sub and vlan interfaces
        for interface in self._intf_settings:
            if 'true' != self._intf_settings[interface].get('clear_config', \
                                                            'true'):
                continue
            intf_name = self._intf_settings[interface].get('name', '')
            #Remove all IPv4 and IPv6 addresses
            bash('ip addr flush dev {}'.format(intf_name))
            #Shutdown interface
            bash('ip link set dev {} down'.format(intf_name))
            out = bash('ip link show')
            for match in re.finditer('{intf}\.\d+@{intf}: '.format(
                intf=intf_name), out):
                    tmp = match.group()
                    intf = tmp[:tmp.find('@')]
                    bash('ip link del {}'.format(intf))

    def _get_services_address(self):
        return self._IP

class UncheckedHostNode(CommonConnectNode):
    """
    FIXME: Document.
    """
    def __init__(
            self, identifier,
            identity_file='id_rsa',
            **kwargs):

        super(UncheckedHostNode, self).__init__(identifier, **kwargs)
        self._register_shell(
            'bash',
            SshBashShell(
                hostname=self._fqdn,
                identity_file=identity_file,
                options=('BatchMode=yes', 'StrictHostKeyChecking=no')
            )
        )


__all__ = ['HostNode', 'UncheckedHostNode']
