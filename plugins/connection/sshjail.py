from copy import deepcopy
import os
import re
from pipes import quote as shell_quote
from shlex import split as shell_split

from ansible import errors
from ansible import utils, __version__ as _ansible_version
from ansible.plugins.connection import ConnectionBase

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()
vvv = display.vvv

# Previously we copied the upstream plugin to *this* directory and did `import ssh as ssh_connection_plugin`
import ansible.plugins.connection.ssh as ssh_connection_plugin

ansible_version = tuple(map(int, _ansible_version.split('.')[:2]))
assert ansible_version >= (2, 0), "We don't support Ansible 1.x anymore"

SSH_JAIL_SEP = '@'


class Connection(ConnectionBase):
    """Remote jail based connections"""

    transport = 'ssh'
    has_pipelining = ssh_connection_plugin.Connection.has_pipelining

    def __init__(self, play_context, *args, **kwargs):
        super(Connection, self).__init__(play_context, *args, **kwargs)
        self._init_args = (args, kwargs)

        self.host = None
        self.jail = None
        self.ssh_host = None
        self.jid = None

        self._ssh_plugin_play_context = deepcopy(play_context)

        # At this point, `self._play_context.remote_addr` may be e.g. 127.0.0.1 if packer has put an override for
        # `ansible_host` in the inventory, so we have to fill in the value later in `set_host_overrides`
        # because there we get the actual host name.
        self._set_host(self._play_context.remote_addr)

        print('HOST IN CONSTRUCTOR TAKEN FROM %r: %r' % (self._play_context.remote_addr, self.ssh_host))

    def _set_host(self, host):
        if self.host is not None:
            return

        if SSH_JAIL_SEP in host:
            self.host = host
            self.jail, ssh_host = self.host.split(SSH_JAIL_SEP, 1)
            if not self.ssh_host:
                self.ssh_host = ssh_host

            self._ssh_plugin_play_context.remote_addr = self.ssh_host
            self.ssh = ssh_connection_plugin.Connection(self._ssh_plugin_play_context, *self._init_args[0], **self._init_args[1])
        else:
            self.ssh_host = host

    def set_host_overrides(self, host, variables, templar):
        super(Connection, self).set_host_overrides(host, variables)

        print('BEFORE SET_HOST_OVERRIDES: (%s, %s)' % (self.jail, self.ssh_host))

        # Because Ansible doesn't provide information about the delegate in `set_host_overrides`, we have to
        # retrieve that information ourselves.
        import inspect
        frame = inspect.currentframe()
        try:
            # WITHOUT PATCH
            delegate_to = None

            # WITH PATCH
            # delegate_to = frame.f_back.f_locals['self']._task.delegate_to
            # print('DELEGATE_TO %r' % delegate_to)
        finally:
            del frame

        self._set_host(delegate_to if delegate_to is not None else host.get_name())
        print('AFTER SET_HOST_OVERRIDES: (%s, %s)' % (self.jail, self.ssh_host))

        if self.host is None:
            raise ValueError('Host not given in jail@server notation')

    def _connect(self):
        self._lazy_connect()
        return self

    def _lazy_connect(self):
        if self.jid:
            return
        self.jid = 123 # fake, no need to know anything about jails for this GitHub issue ;)
        print('CONNECTING TO (%s, %s)' % (self.jail, self.ssh_host))

    def exec_command(self, cmd, in_data=None, sudoable=False):
        self._lazy_connect()
        # ...
        return self.ssh.exec_command(cmd, sudoable=False, in_data=in_data)

    def put_file(self, in_path, out_path):
        with open(in_path, 'rb') as f:
            d = f.read()
        self.put_bytes(d, out_path)

    def put_bytes(self, in_data, out_path):
        if in_data:
            put_cmd = "cat - > %s" % shell_quote(out_path)
        else:
            put_cmd = "cat /dev/null > %s" % shell_quote(out_path)
        self.exec_command(put_cmd, in_data=in_data, sudoable=False)

    def fetch_file(self, in_path, out_path):
        raise NotImplementedError('fetch_file')

    def close(self):
        pass
