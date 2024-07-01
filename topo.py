# sudo mn --switch=lxbr --custom ./topo.py --topo=minimal,delay=10ms,bw=1,loss=0

"""Custom topology

       /----------------------\
h1-eth0|10.0.1.1       r3-eth0|10.0.1.2
+--------------+       +-------------+r3-eth2   tc-link   h2-eth0+-------+
|    host1     |       |    router   |---------------------------| host2 |
+--------------+       +-------------+10.0.3.2           10.0.3.1+-------+
h1-eth1|10.0.2.1       r3-eth1|10.0.2.2
       \----------------------/

sudo mn --custom ./topo.py
"""

import os

from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import Host
from mininet.topo import Topo

class MyHost ( Host ):
    def __init__( self, name, inNamespace=True, **params ):
        super().__init__(name, inNamespace, **params)
        self.offload = params.get('offload', True)

    def configDefault (self, *args, **kw):
        super().configDefault(*args, **kw)
        try:
            fn = getattr(self, f"config_{self.name}")
        except AttributeError:
            return
        fn(self)

    def config_h1(self, host):
        """ Configure host1. """
        host.cmd("ip link set dev h1-eth1 down" )
        host.cmd("ip link set dev h1-eth1 address 00:00:10:00:02:01" )
        host.cmd("ip addr add 10.0.2.1/24 dev h1-eth1")
        host.cmd("ip link set dev h1-eth1 up")
        host.cmd("ip route add 10.0.3.0/24 via 10.0.1.2")

        host.cmd("ip rule add from 10.0.2.1 lookup 50")
        host.cmd("ip route add 10.0.3.0/24 via 10.0.2.2 table 50")

    def config_h2(self, host):
        """ Configure host2. """
        host.cmd("ip route add default via 10.0.3.2")
        #host.cmd("ip link set dev h2-eth0 mtu 1500")

        if host.offload:
            features = []
        else:
            features = [
                "generic-segmentation-offload",
                "tx-gre-segmentation",
                "tx-udp_tnl-segmentation",
                "tx-udp-segmentation",
                "rx-checksumming",
                "tx-checksumming",
                "tx-checksum-ip-generic",
                "tx-checksum-sctp",
                "scatter-gather",
                "tx-scatter-gather",
                "tx-scatter-gather-fraglist",
                "tcp-segmentation-offload",
                "tx-tcp-segmentation",
                "tx-tcp-ecn-segmentation",
                "tx-tcp-mangleid-segmentation",
                "tx-tcp6-segmentation",
                "rx-vlan-offload",
                "tx-vlan-offload",
                "highdma",
                "tx-lockless",
                "tx-gre-csum-segmentation",
                "tx-ipxip4-segmentation",
                "tx-ipxip6-segmentation",
                "tx-udp_tnl-csum-segmentation",
                "tx-sctp-segmentation",
                "tx-gso-list",
                "tx-vlan-stag-hw-insert",
                "rx-vlan-stag-hw-parse",
            ]
        # https://packetbomb.com/how-can-the-packet-size-be-greater-than-the-mtu/
        for dev in ["h2-eth0"]:
            for f in features:
                host.cmd(f"ethtool -K {dev} {f} off")

    def config_r3(self, host):
        """ Configure the router. """
        host.cmd("sysctl -w net.ipv4.ip_forward=1")

        host.cmd("ip link set dev r3-eth1 down" )
        host.cmd("ip link set dev r3-eth1 address 00:00:10:00:02:02" )
        host.cmd("ip addr add 10.0.2.2/24 dev r3-eth1")
        host.cmd("ip link set dev r3-eth1 up")

        host.cmd("ip link set dev r3-eth2 down" )
        host.cmd("ip link set dev r3-eth2 address 00:00:10:00:03:02" )
        host.cmd("ip addr add 10.0.3.2/24 dev r3-eth2")
        host.cmd("ip link set dev r3-eth2 up")

class MyTopo( Topo ):
    "Simple topology."

    def build( self, delay=20, bw=1, loss=None, offload=None ):
        "Create custom topo."

        self.offload = offload is None or offload == "enable"

        delay = str(delay)
        if delay.isdecimal():
            delay += 'ms'

        # Add hosts and switches
        host1   = self.addHost( 'h1', cls=MyHost,
                                ip='10.0.1.1/24', mac='00:00:10:00:01:01' )
        host2   = self.addHost( 'h2', cls=MyHost,
                                ip='10.0.3.1/24', mac='00:00:10:00:03:01',
                                offload=self.offload )
        router  = self.addHost( 'r3', cls=MyHost,
                                ip='10.0.1.2/24', mac='00:00:10:00:01:02' )

        # Add links
        self.addLink( host1, router )
        self.addLink( host1, router )
        self.addLink( host2, router, cls=TCLink, bw=bw, delay=delay, loss=loss )


def new_start(self):
    """ Configure hosts. """
    orig_start(self)
    with open("/tmp/mininet_is_ready", "w") as f:
        f.write("")
orig_start = Mininet.start
Mininet.start = new_start

topos = { 'minimal': MyTopo }

if os.environ["TERM"].startswith("screen"):
    screen_title = 'mininet:0'
    print("k%s\\" % screen_title)
    print("]0;%s" % screen_title)
