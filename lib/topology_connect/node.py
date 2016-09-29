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

from copy import deepcopy
import re
from logging import getLogger
from abc import ABCMeta, abstractmethod

from six import add_metaclass

from topology.platforms.platform import BasePlatform
from topology.platforms.node import CommonNode


log = getLogger(__name__)


@add_metaclass(ABCMeta)
class ConnectNode(CommonNode):
    """
    Base node class for Topology Connect.

    See :class:`topology.platform.CommonNode` for more information.
    """

    @abstractmethod
    def __init__(self, identifier, **kwargs):
        super(ConnectNode, self).__init__(identifier, **kwargs)
        self._validate_attributes(kwargs, self._get_supported_attributes())

    @abstractmethod
    def start(self):
        """
        Starts the Node.
        """

    @abstractmethod
    def stop(self):
        """
        Stops the Node.
        """
    @abstractmethod
    def _get_supported_attributes(self):
        """
        Return node supported attributes. Please refer to _validate_attributes.
        """

    def bring_port_up(self, biport):
        """
        Method to bring interface up
        """

    def wait_port_becomes_up(self, biport):
        """
        Method to wait when interface will be up
        """

    def _validate_attributes(self, attrs, supp_attrs, parent_attr=''):
        """
        Method to validate JSON attributes specified.
        Attributes should be returned by _get_supported_attributes() as dictonary.
        Plese see an dictonary example below:
        {'password': '\w*', <<< The attr. value is regex validation
         '+user': '\w*',   <<< '+' at the beginning means it is mandatory attr.
         'clear_config': 'true|false',
         'bootup_timeout': '\d+',
         'sys_init_after_bootup_timeout': '\d+'},
         'serial': {
             '+serial_command': '.+',   <<< '+' means it is mandatory attr.
             'user': '\w*',
             'password': '\w*',
             'pre_connect_timeout': '\d+',
             'closing_commands': None  <<< None means no attr. value validation
             },
         'interfaces': {
             None: {     <<< The name of attribute is not taken into account.
                 '+name': '\w+', <<< Mandatory attribute
                 'speed': '\d+',
                 'bring_intf_up_timeout': '\d+'
                 }
            }
        }
        """
        local_supp_attr = deepcopy(supp_attrs)
        #Creating list of mandatory attributes
        mandatory_attrs = []
        if None not in local_supp_attr:
            for key, val in local_supp_attr.items():
                if key[0] == '+':
                    tmp_key = key[1:]
                    local_supp_attr[tmp_key] = local_supp_attr.pop(key)
                    mandatory_attrs.append(tmp_key)

        #Check whether input attributes are supported
        for key, val in attrs.items():
            _attr = key
            if parent_attr:
                _attr = parent_attr+'.'+key
            #Special case to analyze attributes with name None.
            #Usually it is interface attributes
            if None in local_supp_attr:
                self._validate_attributes(attrs[key], supp_attrs[None], _attr)
                continue
            assert key in local_supp_attr, \
                'Node \'{}\': unknown attribute specified \'{}\''.format(
                    self.identifier, _attr)
            #Don't validate value of attributes with None value
            if local_supp_attr[key] is None:
                continue

            #Analize sub-attributes, means attributes which value is dictionary
            if isinstance(val, dict):
                _key = key
                if key not in supp_attrs:
                    assert key in mandatory_attrs, \
                        'Node \'{}\': unknown attribute specified \'{}\''.format(
                    self.identifier, _attr)
                    _key = '+' + key
                self._validate_attributes(attrs[key],
                                          supp_attrs[_key],
                                          _attr)
                continue
            #Run regex to validate attribute value
            if val is not None:
                assert re.fullmatch(local_supp_attr[key], val) is not None, \
                    'Node \'{}\': value \'{}\' of attribute \'{}\' is '\
                    'incorrect'.format(self.identifier, val, _attr)

        #Check for mandatory attributes
        for key in mandatory_attrs:
            assert key in attrs, 'Node \'{}\': mandatory attribute '\
            '\'{}\' was not specified'.format(self.identifier, key)

    def clear_config(self):
        """
        Method to clear configured configuration on the node
        """

    def rollback(self):
        """
        Method to rollback in case of node or testscript failure
        """


@add_metaclass(ABCMeta)
class CommonConnectNode(ConnectNode):
    """
    Common Connect Node class for Topology Connect.

    This class will automatically auto-connect to all its shells on start and
    disconnect on stop.

    See :class:`topology_connect.platform.ConnectNode` for more information.
    """

    @abstractmethod
    def __init__(self, identifier, fqdn='127.0.0.1', **kwargs):
        super(CommonConnectNode, self).__init__(identifier, **kwargs)
        self._fqdn = fqdn

    def start(self):
        """
        Connect to all node shells.
        """
        for shell in self._shells.values():
            shell.connect()
        self.clear_config()

    def stop(self):
        """
        Disconnect from  all node shells.
        """
        for shell in self._shells.values():
            shell.disconnect()

    def _get_services_address(self):
        return self._fqdn


__all__ = ['ConnectNode', 'CommonConnectNode']
