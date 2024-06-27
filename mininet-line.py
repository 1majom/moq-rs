#!/usr/bin/python

from functools import partial
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import Node

#!/usr/bin/env python

"""
Extra steps:
  - need to modify the cert gen as always!
  - in the script we count on a veth2 interface being available, it will get the 10.0.0.99 address
  - cmds for 3 host scenario
  h1 ./target/debug/moq-relay --bind '10.0.0.1:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --dev &
  h2 ffmpeg -hide_banner -v quiet -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame  | ./target/debug/moq-pub --name bbb "https://10.0.0.99:4443" &
  h3 ./target/debug/moq-sub --name bbb https://10.0.0.99:4443/bbb | ffplay -
  sudo ip link add veth2 type veth
  sudo ip link set veth2 up
  sudo ip link set veth2 address 00:00:00:00:00:99
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

    a=net.addLink(h1,h2)
    b=net.addLink(h2,h3)
    c=net.addLink(h3,h4)

    # h1 h1-eth0:h2-eth0
    # h2 h2-eth0:h1-eth0 h2-eth1:h3-eth0
    # h3 h3-eth0:h2-eth1 h3-eth1:h4-eth0
    # h4 h4-eth0:h3-eth1
    #




    net.start()
    # Add routes from root ns to hosts
    # root.cmd( 'route add -net ' + '10.0.0.0/24' + ' dev ' + str( intf ) )
    h2.cmd('ip addr add 10.0.1.1/24 dev h2-eth1')
    h3.cmd('ip addr del 10.0.0.3/24 dev h3-eth0')
    h3.cmd('ip addr add 10.0.1.2/24 dev h3-eth0')
    h3.cmd('ip addr add 10.0.2.1/24 dev h3-eth1')

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



