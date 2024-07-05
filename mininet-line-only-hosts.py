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
  +---------+       +------------+   +------------+   +---------+
  | h1(pub) +------>+ h2(relay1) +-->+ h3(relay2) +-->+ h4(sub) |
  +---------+       +------------+   +------------+   +---------+
                   |       |
                   |       |
                   |       |
                +-----+    |    +---------------------+
                |  h5 |----+    |root(redis container)|
                |(api)+---------+---------------------+
                +-----+
- the /dev/api script is not in the original repo, it is changed to fit the current implementation
- these would be commands for 2 relays, 1 publisher and 1 subscriber, but for some reason if ran from the mininet cli it wont work as expected
    - h5 REDIS=10.0.6.99 ./dev/api &
    - h2 'RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '10.0.2.1:4443' --api http://10.0.5.1 --node 'https://10.0.2.1:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --dev &'
    - h3 'RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '10.0.2.2:4443' --api http://10.0.4.2 --node 'https://10.0.2.2:4443' --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --dev &'
    - h1 ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - |  RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-pub --name bbb https://10.0.2.1:4443 --tls-disable-verify &
    - h4 RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb https://10.0.2.2:4443 --tls-disable-verify | ffplay -
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
import subprocess
import os

# Running cleanup before starting the mininet
if not os.geteuid() == 0:
    exit("This script must be run as root")
subprocess.call(['sudo', 'mn', '-c'])



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
    h1=net.addHost('h1')
    h2=net.addHost('h2')
    h3=net.addHost('h3',ip='10.0.2.2/24')
    h4=net.addHost('h4', ip='10.0.3.2/24')
    h5=net.addHost('h5', ip='10.0.5.1/24')

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

    # there were some lines making sure there are no arp traffic while streaming, but they are not needed

    h2.cmd('ip addr add 10.0.2.1/24 dev h2-eth1')
    h2.cmd('ip addr add 10.0.5.2/24 dev h2-eth2')


    h3.cmd('ip addr add 10.0.3.1/24 dev h3-eth1')
    h3.cmd('ip addr add 10.0.4.1/24 dev h3-eth2')

    h5.cmd('ip addr add 10.0.4.2/24 dev h5-eth1')
    h5.cmd('ip addr add 10.0.6.1/24 dev h5-eth2')

    h1.cmd('ip route add 10.0.2.0/24 via 10.0.0.2')
    h4.cmd('ip route add 10.0.2.0/24 via 10.0.3.1')


    print( "Dumping host connections" )
    dumpNodeConnections(net.hosts)

    h5.cmd('REDIS=10.0.6.99 ./dev/api > /tmp/out-h5 &')
    template_for_relays = (
        'RUST_LOG=debug RUST_BACKTRACE=0 SSLKEYLOGFILE=./ssl/{host} '
        './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
        '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
        '--tls-disable-verify --dev > /tmp/out-{host} &'
    )

    h2.cmd(template_for_relays.format(
        host='h2', bind='10.0.2.1:4443', api='http://10.0.5.1', node='https://10.0.2.1:4443'
    ))
    sleep(0.7)

    h3.cmd(template_for_relays.format(
        host='h3', bind='10.0.2.2:4443', api='http://10.0.4.2', node='https://10.0.2.2:4443'
    ))
    sleep(0.7)


	# for troubleshooting
    for h in [h1, h2, h3, h4]:
        h.cmd(f"tshark -i any -w ./{h.name}.pcap &")

	# Sadly these two commands have to be run manually in xterm windows started by xterm h1 h4 because for some reason otherwise the stream would stop after 90ish seconds
	# h1
	# ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - |   SSLKEYLOGFILE=./ssl/h1 RUST_LOG=info RUST_BACKTRACE=1 ./target/debug/moq-pub --name bbb https://10.0.2.1:4443 --tls-disable-verify > /tmp/out-h1
    # h4
	# RUST_LOG=debug RUST_BACKTRACE=1 SSLKEYLOGFILE=./ssl/h4  ./target/debug/moq-sub --name bbb https://10.0.2.2:4443 --tls-disable-verify | ffplay -x 200 -y 100 -




    CLI( net )


    net.stop()



