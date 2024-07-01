#!/usr/bin/python

import os

from functools import partial
from time import sleep
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import Node

#!/usr/bin/env python

"""
- cmds for 2 relay scenario, !: the /dev/api script is not in the repo, it is changed to fit the current implementation
  +---------+       +------------+   +------------+   +---------+
  | h1(pub) +-------+ h2(relay1) +---+ h3(relay2) +---+ h4(sub) |
  +---------+       +------------+   +------------+   +---------+
                   |       |
                   |       |
                   |       |
                +-----+    |    +----+
                |  h5 |----+    |root|
                |(api)+---------+----+
                +-----+

    - h5 ./dev/api &
    - h2 'RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '10.0.2.1:4443' --api http://10.0.5.1 --node 'https://10.0.2.1:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --dev &'
    - h3 'RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '10.0.2.2:4443' --api http://10.0.4.2 --node 'https://10.0.2.2:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --dev &'
    - h1 ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - |  RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-pub --name bbb https://10.0.2.1:4443 --tls-disable-verify &
    - h4 RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb https://10.0.2.2:4443 --tls-disable-verify | ffplay -
- when running into problems wait and dont forget to use sudo mn -c
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



    pcap_files = ["h1-eth0.pcap", "h4-eth0.pcap", "h3-eth0.pcap", "h2-eth1.pcap"]

    # Loop through each pcap file
    for pcap_file in pcap_files:
        # Remove the file if it exists
        if os.path.exists(pcap_file):
            os.remove(pcap_file)
        # Recreate the file
        open(pcap_file, 'a').close()
        # Change the file permission to read-write for others
        os.chmod(pcap_file, 0o666)


    net = Mininet( topo=None, waitConnected=True, link=partial(TCLink) )
    net.staticArp()
    switch = net.addSwitch('s1',failMode='standalone')
    h1=net.addHost('h1', mac='00:00:00:00:01:01')
    h2=net.addHost('h2', mac='00:00:00:00:02:01')
    h3=net.addHost('h3',ip='10.0.2.2/24', mac='00:00:00:00:03:01')
    h4=net.addHost('h4', ip='10.0.3.2/24', mac='00:00:00:00:04:01')
    h5=net.addHost('h5', ip='10.0.5.1/24', mac='00:00:00:00:05:01')

    a=net.addLink(h1,h2)
    b=net.addLink(h2,h3,
                #    bw=5
                   )
    c=net.addLink(h3,h4)
    d=net.addLink(h2,h5)
    f=net.addLink(h3,h5)

    # we need the access to the host because of the redis container, in the long run it might be easier to put
    # the storing into the binary. But the route destinated to the root interface is not needed, because only
    # the two relays will need access to the redis container and they are connected to the switch.
    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, h5 ).intf1
    root.setIP( '10.0.6.99', intf=intf )


    print("disable ipv6")
    for h in net.hosts:
            h.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
            h.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
            h.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")



    net.start()

    h1.cmd('ip link set h1-eth0 address 00:00:00:00:01:01')

    h2.cmd('ip link set h2-eth0 address 00:00:00:00:02:01')
    h2.cmd('ip link set h2-eth1 address 00:00:00:00:02:02')
    h2.cmd('ip link set h2-eth2 address 00:00:00:00:02:03')

    h3.cmd('ip link set h3-eth1 address 00:00:00:00:03:02')
    h3.cmd('ip link set h3-eth2 address 00:00:00:00:03:03')

    h4.cmd('ip link set h4-eth0 address 00:00:00:00:04:01')

    h5.cmd('ip link set h5-eth0 address 00:00:00:00:05:01')
    h5.cmd('ip link set h5-eth1 address 00:00:00:00:05:02')
    h5.cmd('ip link set h5-eth2 address 00:00:00:00:05:03')



    h2.cmd('ip addr add 10.0.2.1/24 dev h2-eth1')
    h2.cmd('ip addr add 10.0.5.2/24 dev h2-eth2')


    h3.cmd('ip addr add 10.0.3.1/24 dev h3-eth1')
    h3.cmd('ip addr add 10.0.4.1/24 dev h3-eth2')

    h5.cmd('ip addr add 10.0.4.2/24 dev h5-eth1')
    h5.cmd('ip addr add 10.0.6.1/24 dev h5-eth2')

    h1.cmd('ip route add 10.0.2.0/24 via 10.0.0.2')
    h4.cmd('ip route add 10.0.2.0/24 via 10.0.3.1')

    h3.cmd('arp -s 10.0.3.2 00:00:00:00:04:01')
    h4.cmd('arp -s 10.0.3.1 00:00:00:00:03:02')
    h2.cmd('arp -s 10.0.0.1 00:00:00:00:01:01')

    h3.cmd('arp -s 10.0.2.1 00:00:00:00:02:02')
    h2.cmd('arp -s 10.0.2.2 00:00:00:00:03:01')
    h1.cmd('arp -s 10.0.0.2 00:00:00:00:02:01')




    # h2.cmd('arp -s 10.0.0.1 00:00:00:00:01:01')
    # h1.cmd('arp -s 10.0.2.1 00:00:00:00:02:02')
    # h1.cmd('arp -s 10.0.3.1 00:00:00:00:03:02')
    # h1.cmd('arp -s 10.0.4.2 00:00:00:00:05:05')

    # # # Add sticky ARP entries to h4
    # h4.cmd('arp -s 10.0.0.1 00:00:00:00:01:01')
    # h4.cmd('arp -s 10.0.2.1 00:00:00:00:02:02')
    # h4.cmd('arp -s 10.0.3.1 00:00:00:00:03:02')
    # h4.cmd('arp -s 10.0.5.2 00:00:00:00:02:03')



    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)

    h5.cmd('REDIS=10.0.6.99 ./dev/api &')
    h2.cmd('RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind \'10.0.2.1:4443\' --api http://10.0.5.1 --node \'https://10.0.2.1:4443\' --tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key --tls-disable-verify --dev &')
    h3.cmd('RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind \'10.0.2.2:4443\' --api http://10.0.4.2 --node \'https://10.0.2.2:4443\' --tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key --tls-disable-verify --dev &')
    sleep(0.3)

    h1.cmd('ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - |  RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-pub --name bbb https://10.0.2.1:4443 --tls-disable-verify &')
    sleep(0.5)

    # h1.cmd("wireshark --interface h1-eth0 -k &")
    # # h4.cmd("wireshark --interface h4-eth0 -k &")
    # # h3.cmd("wireshark --interface h3-eth0 -k &")
    # # h2.cmd("wireshark --interface h2-eth1 -k &")

    h1.cmd("tshark -i h1-eth0 -w ./h1-eth0.pcap &")
    h4.cmd("tshark -i h4-eth0 -w ./h4-eth0.pcap &")
    h3.cmd("tshark -i h3-eth0 -w ./h3-eth0.pcap &")
    h2.cmd("tshark -i h2-eth1 -w ./h2-eth1.pcap &")


    # h4.cmd('RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb https://10.0.2.2:4443 --tls-disable-verify | ffplay -')
    # h4 RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb https://10.0.2.2:4443 --tls-disable-verify | ffplay -x 200 -y 100 -




    CLI( net )


    net.stop()



