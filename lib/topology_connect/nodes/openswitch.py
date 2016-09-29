# -*- coding: utf-8 -*-
#
# Copyright Mellanox Technologies, Ltd. 2001-2016.
# This software product is licensed under Apache version 2, as detailed in
# the LICENSE file.
#

"""
topology_connect base node module.
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from logging import getLogger
from time import sleep
from subprocess import call
import pytest

from ..node import CommonConnectNode
from ..shell import OpenswitchVtyShell, SshBashShell, OpenswitchSerialShell


log = getLogger(__name__)

image_load_status = []
@pytest.fixture(autouse=True)
def declare_image_load_status(request):
    request.function.__globals__['image_load_status'] = image_load_status

class OpenswitchNode(CommonConnectNode):
    """
    FIXME: Document.
    """
    _valid_attrs = {'+type': 'openswitch',
                     '+user': '\w*',
                     '+IP': '([0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|'\
                     '(\d{1,3}\.){3}\d{1,3}|'\
                     '^(?:[a-zA-Z0-9]+|[a-zA-Z0-9][-a-zA-Z0-9]+[a-zA-Z0-9])'\
                     '(?:\.[a-zA-Z0-9]+|[a-zA-Z0-9][-a-zA-Z0-9]+[a-zA-Z0-9])?$',
                     'password': '\w*',
                     'clear_config': 'true|false',
                     'reboot_command': '.+',
                     'bootup_timeout': '\d+',
                     'sys_init_after_bootup_timeout': '\d+',
                     'bootloader_bootup_timeout': '\d+',
                     'image': {
                         '+path': '.+',
                         '+server': {
                            '+IP': '.+',
                            'user': '\w*',
                            'password': '\w*'
                            }
                     },
                     'serial': {
                         '+serial_command': '.+',
                         'user': '\w*',
                         'password': '\w*',
                         'pre_connect_timeout': '\d+',
                         'closing_commands': None
                         },
                     'interfaces': {
                         None: {
                             '+name': '\w+',
                             'speed': '\d+',
                             'bring_intf_up_timeout': '\d+'
                             }
                         }
                     }

    def __init__(
            self, identifier,
            **kwargs):
        super(OpenswitchNode, self).__init__(identifier, **kwargs)
        self._type = kwargs.pop("type", "")
        user = kwargs.get('user', None)
        password = kwargs.get('password', None)
        self._IP = kwargs.pop('IP', None)
        self._bootup_timeout = int(kwargs.pop('bootup_timeout', '0'))
        self._sys_init_after_bootup_timeout  = int(kwargs.pop(
            'sys_init_after_bootup_timeout', '0'))
        self._bootloader_bootup_timeout =  int(kwargs.pop(
            'bootloader_bootup_timeout', '0'))
        self._intf_attrs = kwargs.pop('interfaces', None)
        self._image_attrs = kwargs.pop('image', None)
        self._serial_attrs = kwargs.pop('serial', None)
        self._reboot_command = kwargs.pop('reboot_command', None)
        self._clear_config = kwargs.pop('clear_config', 'true')
        if '' == password:
            kwargs['password'] = None

        self._shells['vtysh'] = OpenswitchVtyShell(
            hostname = self._IP,
            identity_file = None, options = ('BatchMode=no',
                'StrictHostKeyChecking=no', ),
            **kwargs
        )
        self._shells['bash'] = SshBashShell(
            hostname = self._IP,
            identity_file = None, options = ('BatchMode=no',
                'StrictHostKeyChecking=no', ),
            initial_prompt='\w+@.+[#$] ',
            **kwargs
        )
        self._shells['vsctl'] = SshBashShell(
            hostname = self._IP,
            identity_file = None, options = ('BatchMode=no',
                'StrictHostKeyChecking=no', ),
            prefix='ovs-vsctl ',
            initial_prompt='\w+@.+[#$] ',
            **kwargs
        )
        if self._image_attrs is not None:
            self._load_image_attrs()
            self._burn_image()

    def _get_interface_config(self, biport):
        label = biport.metadata.get('label', biport.identifier.split('-')[1])
        assert label in self._intf_attrs, \
        'Switch \'{}\': unknown interface \'{}\''.format(self.identifier, \
                                                         label)

        intf_config = self._intf_attrs[label]
        real_label = intf_config.get('name', label)

        return intf_config, real_label, label

    def bring_port_up(self, biport):
        """
        Method to bring interface up
        """
        intf_config, real_label, label = self._get_interface_config(biport)

        print('\nSwitch \'{}\', interface \'{}\'(real name \'{}\'): '\
            'bringing interface up'.format(self.identifier, label, \
                                           real_label))
        vtysh = self.get_shell('vtysh')
        out = vtysh('show interface '+ real_label)
        if 'Interface {} is up'.format(real_label) not in out:
            vtysh('config')
            vtysh('interface '+ real_label)
            if 'speed' in intf_config:
                vtysh('speed '+ intf_config['speed'])
            vtysh('no shutdown')
            vtysh('exit')
            vtysh('exit')

        return real_label

    def wait_port_becomes_up(self, biport):
        iter = 0
        port_is_up = False
        intf_config, real_label, label = self._get_interface_config(biport)
        bring_intf_up_timeout = int(intf_config.get('bring_intf_up_timeout',
                                                    30))
        print('\nSwitch \'{self.identifier}\', interface \'{label}\''\
            '(real name \'{real_label}\'): '\
            'Waiting when interface will be up'.format(**locals()),\
             end='', flush=True)

        vtysh = self.get_shell('vtysh')
        while iter < bring_intf_up_timeout:
            print('.', end='', flush=True)
            out = vtysh('show interface '+ real_label)
            if 'Admin state is up' in out:
                port_is_up = True
                break;
            iter += 1
            sleep(1)
        assert port_is_up, '\nSwitch \'{self.identifier}\', '\
            'interface \'{label}\'(real name \'{real_label}\'): '\
            'couldn\'t bring interface UP'.format(**locals())
        print('done\n', flush=True)

    def clear_config(self):
        if 'true' != self._clear_config:
            return
        print('\nSwitch \'{}\': clearing configuration'.format(self.identifier))
        vtysh = self.get_shell('vtysh')
        vtysh('copy startup-config running-config')

    def _burn_image(self):
        _serial_login_prompt = '[lL]ogin: '
        _serial_prompt = '{}@.+:~# '.format(self._image_user)
        _serial_onie_prompt = 'ONIE:/ # '
        _serial_vtysh_prompt = '.+(\(.+\))?# '
        _serial_boot_prompt = 'OpenSwitch '
        _serial_boot_onie_prompt = 'ONIE'
        _serial_grub_prompt = '(OpenSwitch Primary Image|'\
            'OpenSwitch Secondary Image)'

        if self._image_attrs is None:
            return
        if self._IP in image_load_status:
            return
        image_load_status.append(self._IP)

        print('\nBurning image to \'{}\''.format(self.identifier))
        params = {'user_match': _serial_login_prompt,
                  'bootup_timeout': self._bootup_timeout}
        params.update(self._serial_attrs)
        serial = OpenswitchSerialShell(**params)

        try:
            serial.connect()
        except:
            self._reboot_switch()
            serial.connect()

        self._erase_startup_config()

        spawn = serial._get_connection(None)
        serial.setPromt(_serial_grub_prompt)
        temp = serial._timeout
        if 0 != self._bootloader_bootup_timeout:
            serial._timeout = self._bootloader_bootup_timeout
        print("Rebooting switch \'{}\'".format(self.identifier))
        serial('reboot')
        serial._timeout = temp
        serial.setPromt(_serial_boot_prompt)
        print("We are in Grub. Choosing ONIE")
        sleep(1)
        serial.send_command('\x1b[B', newline=False)# Press Arror down
        serial.send_command('\x1b[B', newline=False)# Press Arror down
        serial.send_command('\x1b[B', newline=False)# Press Arror down
        sleep(1)
        serial.setPromt(_serial_boot_onie_prompt)
        serial.send_command('\n\r', newline=False)# Press Enter
        print("We are in ONIE. Choosing ONIE rescue")
        sleep(1)
        serial.send_command('\x1b[B', newline=False)# Press Arror down
        sleep(1)
        print("We are in ONIE rescue. Waiting to press enter to activate console")
        serial.setPromt('Please press Enter to activate this console.')
        # TODO make configurable via JSON attribute
        # Need to wait while ONIE is taking IP address from DHCP
        serial._timeout = 180
        serial.send_command('\n\r', newline=False)# Press Enter
        serial._timeout = temp
        serial.setPromt(_serial_onie_prompt)
        serial.send_command('\n\r', newline=False)# Press Enter
        print("We are in ONIE rescue. Downloading image from {}".format(
            self._image_server_ip))
        serial.setPromt('Do you want to continue connecting\? \(y\/n\) ')
        serial('scp {self._image_server_user}@{self._image_server_ip}:'\
               '{self._image_path} ./'.format(**locals()))
        serial.setPromt('.+password: ')
        serial('y')# Press 'y'
        spawn.sendline(self._image_server_password)
        out = ''
        prev_out = ''
        message = ''
        # Loop to wait for image downloading.
        # When timeout occured(default is 30 seconds) while waiting for ONIE
        # prompt, we check previous output and new one.
        # If outputs are different then we assume that image download
        # didn't stuck and continue waiting.
        while True:
            try:
                spawn.expect(_serial_onie_prompt, timeout=serial._timeout)
                message = spawn.before.decode(serial._encoding)
            except:
                message = spawn.before.decode(serial._encoding)
                prev_out = message[message.rfind('\r') + 1 :]
                assert prev_out != out, \
                    'Switch \'{self.identifier}\': '\
                    'Timeout occured while downloading image '\
                    'from {self._image_server_user}@{self._image_server_ip}:'\
                    '{self._image_path}'.format(**locals())
                out = prev_out
                continue
            break
        serial.setPromt(_serial_onie_prompt)
        rc = serial('echo $?')
        assert '0' == rc, 'Switch \'{}\': Failed to download image: \'{}\''. \
            format(self.identifier, message)
        serial.setPromt('[rR]estart')
        print('We are in ONIE rescue. Executing onie installer')
        file_name = self._image_path[self._image_path.rfind('/')+1:]
        out = serial('sh {}'.format(file_name))
        assert 'Installation finished. No error reported.' in out, \
            'Switch \'{}\':Failed to burning image'.format(self.identifier)
        print('Successfully burned image')
        print('Waiting to switch boot up')
        temp = serial._timeout
        if 0 != self._bootloader_bootup_timeout:
            serial._timeout = self._bootloader_bootup_timeout
        serial.setPromt(_serial_grub_prompt)
        serial('')
        serial._timeout = temp
        serial.setPromt(_serial_login_prompt)
        serial.send_command('\n\r', newline=False)# Press Enter

        sleep(self._sys_init_after_bootup_timeout)
        self._create_startup_config()
        print('Switch \'{}\' is ready for the tests :)'.format(
            self.identifier))

    def _erase_startup_config(self):
        print('Erasing startup config...', end='', flush=True)
        vtysh = self.get_shell('vtysh')
        vtysh.connect()
        prev_prompt = vtysh._prompt
        vtysh._prompt = 'Do you want to continue \[y\/n\]'
        vtysh('erase startup-config')
        vtysh._prompt = prev_prompt
        vtysh('y')
        vtysh.disconnect()
        print('done')

    def _create_startup_config(self):
        print('Creating "empty" startup config...', end='', flush=True)
        vtysh = self.get_shell('vtysh')
        seconds = 0
        while seconds < 15:
            vtysh('copy running-config startup-config')
            out = vtysh('show startup-config')
            if 'No saved configuration exists' not in out:
                break
            seconds += 1
            sleep(1)
        vtysh.disconnect()
        print('done')

    def _reboot_switch(self):
        if self._reboot_command is not None:
            printf('Switch \'{}\': rebooting'.format(self.identifier))
            ret = call(self._reboot_command)
            assert 0 == ret, 'Failed to reboot switch \'{}\''.format(self.__i)
            sleep(self._bootup_timeout)

    def _get_supported_attributes(self):
        return self._valid_attrs

    def _load_image_attrs(self):
        _image_server_attr = self._image_attrs.get('server', None)
        self._image_path = self._image_attrs.get('path', None)
        self._image_user = self._image_attrs.get('user', None)
        self._image_password = self._image_attrs.get('password', None)
        if '' == self._image_password:
            self._image_password = None
        self._image_server_ip = _image_server_attr.get('IP', None)
        self._image_server_user = _image_server_attr.get('user', None)
        self._image_server_password = _image_server_attr.get('password', None)
        if '' == self._image_server_password:
            self._image_server_password = None

    def rollback(self):
        self._reboot_switch()

    def _get_services_address(self):
        return self._IP

__all__ = ['OpenswitchNode']

