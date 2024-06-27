#!/usr/bin/python

from functools import partial
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import Node

#!/usr/bin/env python

"""
- cmds for 1 relay scenario, h4 is left out :c
  +----------+   +------------+   +-----------+
  | h1 (pub) +---+ h2 (relay) +---+ h3 (sub)  |
  +----------+   +------------+   +-----------+

    - h2 ./target/debug/moq-relay --bind '10.0.1.1:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --dev &
    - h1 ffmpeg -hide_banner         -stream_loop -1 -re     -i ./dev/bbb.mp4        -c copy -an     -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - | ./target/debug/moq-pub --name bbb2 https://10.0.1.1:4443 --tls-disable-verify &
    - h3 ./target/debug/moq-sub --name bbb2 https://10.0.1.1:4443 --tls-disable-verify | ffplay -


- cmds for 2 relay scenario, !: the /dev/api script is not in the repo, it is changed to fit the current implementation
  +----------+   +------------+   +-----------+   +----------+
  | h1 (pub) +---+ h2 (relay) +---+ h3 (relay)+---+ h4 (sub) |
  +----------+   +------------+   +-----------+   +----------+
                         |                |
                   +-----+ s1 +--------+--+
                   |                   |
                 +----+              +-------------------------------------------+
                 |h5  |              |root(host system running redis for the api)|
                 +----+              +-------------------------------------------+


    - h5 ./dev/api &
    - h2 RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '10.0.1.1:4443' --api http://10.0.3.1 --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --dev &
    - h3 RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '10.0.1.2:4443' --api http://10.0.3.1 --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --dev &
	- h1 ffmpeg -hide_banner         -stream_loop -1 -re     -i ./dev/bbb.mp4        -c copy -an     -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - |  RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-pub --name bbb2 https://10.0.1.1:4443 --tls-disable-verify &
    - h4 RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb2 https://10.0.1.2:4443 --tls-disable-verify | ffplay -
"""

import re

from sys import exit  # pylint: disable=redefined-builtin

from mininet.cli import CLI
from mininet.log import setLogLevel, info, error
from mininet.net import Mininet
from mininet.util import quietRun
from mininet.cli import CLI
from mininet.log import info
from mininet.node import Node

from mininet.link import TCLink


if __name__ == '__main__':
    setLogLevel( 'info' )


    net = Mininet( topo=None, waitConnected=True, link=partial(TCLink) )
    switch = net.addSwitch('s1',failMode='standalone')
    h1=net.addHost('h1')
    h2=net.addHost('h2')
    h3=net.addHost('h3', ip='10.0.1.2/24')
    h4=net.addHost('h4', ip='10.0.2.2/24')
    h5=net.addHost('h5', ip='10.0.3.1/24')

    a=net.addLink(h1,h2)
    b=net.addLink(h2,h3)
    c=net.addLink(h3,h4)
    d=net.addLink(h2,switch)
    e=net.addLink(h5,switch)
    f=net.addLink(h3,switch)

    # we need the access to the host because of the redis container, in the long run it might be easier to put
    # the storing into the binary. But the route destinated to the root interface is not needed, because only
    # the two relays will need access to the redis container and they are connected to the switch.
    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, switch ).intf1
    root.setIP( '10.0.3.99', intf=intf )






    net.start()
    h2.cmd('ip addr add 10.0.1.1/24 dev h2-eth1')
    h3.cmd('ip addr del 10.0.0.3/24 dev h3-eth0')
    h3.cmd('ip addr add 10.0.1.2/24 dev h3-eth0')
    h3.cmd('ip addr add 10.0.2.1/24 dev h3-eth1')

    h2.cmd('ip addr add 10.0.3.2/24 dev h2-eth2')
    h3.cmd('ip addr add 10.0.3.3/24 dev h3-eth2')

    h1.cmd('ip route add 10.0.1.0/24 via 10.0.0.2')
    h1.cmd('ip route add 10.0.2.0/24 via 10.0.0.2')

    h2.cmd('ip route add 10.0.2.0/24 via 10.0.1.2')

    h3.cmd('ip route add 10.0.0.0/24 via 10.0.1.1')
    h4.cmd('ip route add 10.0.0.0/24 via 10.0.2.1')
    h4.cmd('ip route add 10.0.1.0/24 via 10.0.2.1')

    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)
    CLI( net )


    net.stop()



