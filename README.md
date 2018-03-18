## Environment

One physical server `homeserver`, 2 jails `firstjail` and `secondjail` inside.
Jails should be accessed by connecting via the homeserver (and then e.g.
running commands inside the specified jail with `jexec`). Or in other words
in case you are not familiar with jails: we want to connect to containers
within a server, and the containers not running their own SSH daemon.

## Problem

This all works fine with a regular one-inventory setup. My example inventory,
`sshjail` plugin (stripped down to show the problem) and test playbook perform
the expected steps:

```
$ ansible-playbook -i inventory.yml test.yml

PLAY [homeserver] ******************************************************************************************************************************************

TASK [Should ping homeserver] ******************************************************************************************************************************
ok: [homeserver]

PLAY [firstjail@homeserver] ********************************************************************************************************************************

TASK [Should ping firstjail@homeserver] ********************************************************************************************************************
HOST IN CONSTRUCTOR TAKEN FROM u'firstjail@homeserver': u'homeserver'
BEFORE SET_HOST_OVERRIDES: (firstjail, homeserver)
AFTER SET_HOST_OVERRIDES: (firstjail, homeserver)
CONNECTING TO (firstjail, homeserver)
ok: [firstjail@homeserver]

TASK [Should ping homeserver (delegated)] ******************************************************************************************************************
ok: [firstjail@homeserver -> homeserver]

TASK [Should ping secondjail@homeserver (delegated)] *******************************************************************************************************
HOST IN CONSTRUCTOR TAKEN FROM u'secondjail@homeserver': u'homeserver'
BEFORE SET_HOST_OVERRIDES: (secondjail, homeserver)
AFTER SET_HOST_OVERRIDES: (secondjail, homeserver)
CONNECTING TO (secondjail, homeserver)
ok: [firstjail@homeserver -> secondjail@homeserver]

PLAY RECAP *************************************************************************************************************************************************
firstjail@homeserver       : ok=3    changed=0    unreachable=0    failed=0
homeserver                 : ok=1    changed=0    unreachable=0    failed=0
```

But with [Packer's Ansible provisioner](https://www.packer.io/docs/provisioners/ansible.html),
which uses a SSH proxy via localhost and therefore injects an additional
inventory file like

```
<the_host_alias> ansible_host=127.0.0.1 ansible_user=<the_user> ansible_port=<local_ssh_proxy_port>
```

the delegation misbehaves and sends tasks to the wrong host. The file
`extrainv` is an example for what Packer created. This is the
problematic playbook behavior using the extra inventory's `ansible_host`
override:

```
$ ./tunnel & # used only for example purposes, not important
$ # ...edit sshjail.py to disable patch...
$ ansible-playbook -i inventory.yml -i extrainv test.yml

PLAY [homeserver] ******************************************************************************************************************************************

TASK [Should ping homeserver] ******************************************************************************************************************************
ok: [homeserver]

PLAY [firstjail@homeserver] ********************************************************************************************************************************

TASK [Should ping firstjail@homeserver] ********************************************************************************************************************
HOST IN CONSTRUCTOR TAKEN FROM u'127.0.0.1': u'127.0.0.1'
BEFORE SET_HOST_OVERRIDES: (None, 127.0.0.1)
AFTER SET_HOST_OVERRIDES: (firstjail, 127.0.0.1)
CONNECTING TO (firstjail, 127.0.0.1)
ok: [firstjail@homeserver]

TASK [Should ping homeserver (delegated)] ******************************************************************************************************************
ok: [firstjail@homeserver -> 127.0.0.1]

TASK [Should ping secondjail@homeserver (delegated)] *******************************************************************************************************
HOST IN CONSTRUCTOR TAKEN FROM u'127.0.0.1': u'127.0.0.1'
BEFORE SET_HOST_OVERRIDES: (None, 127.0.0.1)
AFTER SET_HOST_OVERRIDES: (firstjail, 127.0.0.1)
CONNECTING TO (firstjail, 127.0.0.1)            <----------------- wrong target!
ok: [firstjail@homeserver -> 127.0.0.1]

PLAY RECAP *************************************************************************************************************************************************
firstjail@homeserver       : ok=3    changed=0    unreachable=0    failed=0
homeserver                 : ok=1    changed=0    unreachable=0    failed=0
```

With my hacky patch (get delegate information from caller's stack frame),
behavior is fixed because my custom `sshjail` connection plugin can get
the required information:

```
$ # ...edit sshjail.py to enable patch...
$ ansible-playbook -i inventory.yml -i extrainv test.yml

PLAY [homeserver] ******************************************************************************************************************************************

TASK [Should ping homeserver] ******************************************************************************************************************************
ok: [homeserver]

PLAY [firstjail@homeserver] ********************************************************************************************************************************

TASK [Should ping firstjail@homeserver] ********************************************************************************************************************
HOST IN CONSTRUCTOR TAKEN FROM u'127.0.0.1': u'127.0.0.1'
BEFORE SET_HOST_OVERRIDES: (None, 127.0.0.1)
AFTER SET_HOST_OVERRIDES: (firstjail, 127.0.0.1)
CONNECTING TO (firstjail, 127.0.0.1)
ok: [firstjail@homeserver]

TASK [Should ping homeserver (delegated)] ******************************************************************************************************************
ok: [firstjail@homeserver -> 127.0.0.1]

TASK [Should ping secondjail@homeserver (delegated)] *******************************************************************************************************
HOST IN CONSTRUCTOR TAKEN FROM u'127.0.0.1': u'127.0.0.1'
BEFORE SET_HOST_OVERRIDES: (None, 127.0.0.1)
AFTER SET_HOST_OVERRIDES: (secondjail, 127.0.0.1)
CONNECTING TO (secondjail, 127.0.0.1)            <-----------------
ok: [firstjail@homeserver -> 127.0.0.1]

PLAY RECAP *************************************************************************************************************************************************
firstjail@homeserver       : ok=3    changed=0    unreachable=0    failed=0
homeserver                 : ok=1    changed=0    unreachable=0    failed=0
```

Of course this is a generic problem of Ansible not support "sub-hosts", but
for this case, there seems to be an easy fix.
It would be great to forward information about the delegate to the connection
plugin so it can make correct decisions.
