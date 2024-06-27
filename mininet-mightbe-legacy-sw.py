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
    h1=net.addHost('h1')
    a=net.addLink(h1,switch)
    b=net.addLink(net.addHost('h2'),switch
                #   delay='10ms',
				  )
    c=net.addLink(net.addHost('h3'),switch)



    info( '*** Adding hardware interface', intfName, 'to switch',
          switch.name, '\n' )

    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, switch ).intf1
    root.setIP( '10.0.0.99', intf=intf )


    net.start()
    # Add routes from root ns to hosts
    root.cmd( 'route add -net ' + '10.0.0.0/24' + ' dev ' + str( intf ) )


    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)
    CLI( net )


    net.stop()



