#!/usr/bin/python

from functools import partial
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import Node

#!/usr/bin/env python

"""
nope
"""

import re
import sys

from sys import exit  # pylint: disable=redefined-builtin

from mininet.cli import CLI
from mininet.log import setLogLevel, info, error
from mininet.net import Mininet
from mininet.util import quietRun
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import info
from mininet.node import Node

from mininet.link import TCLink

def checkIntf( intf ):
    "Make sure intf exists and is not configured."
    config = quietRun( 'ifconfig %s 2>/dev/null' % intf, shell=True )
    if not config:
        error( 'Error:', intf, 'does not exist!\n' )
        exit( 1 )
    ips = re.findall( r'\d+\.\d+\.\d+\.\d+', config )
    if ips:
        error( 'Error:', intf, 'has an IP address,'
               'and is probably in use!\n' )
        exit( 1 )



if __name__ == '__main__':
    setLogLevel( 'info' )

    intfName = 'veth2'
    info( '*** Connecting to hw intf: %s' % intfName , '\n' )

    info( '*** Checking', intfName, '\n' )
    checkIntf( intfName )

    net = Mininet( topo=None, waitConnected=True, link=partial(TCLink) )
    switch = net.addSwitch('s1',failMode='standalone')
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.2.3/24')
    h4 = net.addHost('h4', ip='10.0.3.4/24')


    # Add more hosts as needed

    # Step 2: Create links between hosts and switches
    net.addLink(h1, h2)
    net.addLink(h2, h3)
    net.addLink(h3, h4)


    info( '*** Adding hardware interface', intfName, 'to switch',
          switch.name, '\n' )

    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, switch ).intf1
    root.setIP( '10.0.0.99', intf=intf )
    # Start network that now includes link to root namespace


    net.start()
    # Add routes from root ns to hosts
    # root.cmd( 'route add -net ' + '10.0.0.0/24' + ' dev ' + str( intf ) )
    for h in [h1, h2, h3, h4]:
        h.cmd('sysctl -w net.ipv4.ip_forward=1')
	# h3 ip addr add 10.0.3.3/24 dev h3-eth1
    # h2 ip addr add 10.0.2.2/24 dev h2-eth1
    h3.cmd('ip addr add 10.0.3.3/24 dev h3-eth1')
    h2.cmd('ip addr add 10.0.2.2/24 dev h2-eth1')
    h1.cmd('ip route add 10.0.3.0/24 dev h1-eth0')
    h1.cmd('ip route add 10.0.2.0/24 dev h1-eth0')
    h2.cmd('ip route add 10.0.3.0/24 dev h2-eth1')
    h3.cmd('ip route add 10.0.0.0/24 dev h3-eth0')
    h4.cmd('ip route add 10.0.2.0/24 dev h4-eth0')
    h4.cmd('ip route add 10.0.0.0/24 dev h4-eth0')

    # link = net.linksBetween(h1, switch)[0]
    # link.intf1.config(bw=1000)
    # link.intf2.config(bw=1000)


    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)

    CLI( net )


    net.stop()

# need to modify the cert gen as always
# h1 ./target/debug/moq-relay --bind '10.0.0.1:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --dev &
# h2 ffmpeg -hide_banner -v quiet -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame  | ./target/debug/moq-pub --name bbb "https://10.0.0.1:4443" &
# h3 ./target/debug/moq-sub --name bbb https://10.0.0.1:4443/bbb | ffplay -
# sudo ip link add veth2 type veth
# sudo ip link set veth2 up
# sudo ip link set veth2 address 00:00:00:00:00:99

