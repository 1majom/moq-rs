#!/usr/bin/python

"""
default sw with controller, might be a bit slower
"""

import re
import sys
from sys import exit  # pylint: disable=redefined-builtin

from mininet.net import Mininet
from mininet.util import dumpNodeConnections, quietRun, waitListening
from mininet.log import setLogLevel, info, error, lg
from mininet.node import Node
from mininet.cli import CLI
from mininet.link import Intf, TCLink
from mininet.topo import SingleSwitchTopo
from mininet.topolib import TreeTopo

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
    "Create and test a simple network"

    # try to get hw intf from the command line; by default, use eth1
    intfName = sys.argv[ 1 ] if len( sys.argv ) > 1 else 'veth2'
    info( '*** Connecting to hw intf: %s' % intfName , '\n' )

    info( '*** Checking', intfName, '\n' )
    checkIntf( intfName )

    net = Mininet( topo=TreeTopo( depth=1, fanout=3 ), waitConnected=True, link=TCLink )
    switch = net.switches[ 0 ]

    info( '*** Adding hardware interface', intfName, 'to switch',
          switch.name, '\n' )

    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, switch ).intf1
    root.setIP( '10.0.0.99', intf=intf )
    # Start network that now includes link to root namespace


    net.start()
    # Add routes from root ns to hosts
    root.cmd( 'route add -net ' + '10.0.0.0/24' + ' dev ' + str( intf ) )
    h1, s1 = net.get('h1'), net.get('s1')

    # Get the link object between h1 and s1
    link = net.linksBetween(h1, s1)[0]
    link.intf1.config(delay='0ms')

    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)
    CLI( net )

    # print( "Testing network connectivity" )
    # net.pingAll()
    # result = net.hosts[0].cmd('./target/debug/moq-relay --bind \'10.0.0.2:4443\' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --dev &')
    # print(result)
    # result = net.hosts[1].cmd('./target/debug/moq-pub --name bbb "https://10.0.0.2:4443" &')
    # print( result )
    net.stop()

# need to modify the cert gen as always
# h1 ./target/debug/moq-relay --bind '10.0.0.1:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --dev &
# h1 ffmpeg -hide_banner -v quiet -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame  | ./target/debug/moq-pub --name bbb "https://10.0.0.1:4443" &
# h2 ./target/debug/moq-sub --name bbb https://10.0.0.1:4443/bbb | ffplay -
# sudo ip link add veth2 type veth
# sudo ip link set veth2 up
# sudo ip link set veth2 address 00:00:00:00:00:99
# sudo mn --custom mininet-type.py --topo mytopo

