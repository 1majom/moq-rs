#!/usr/bin/python

import os

from functools import partial
from time import sleep
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import Node

from sys import exit  # pylint: disable=redefined-builtin

from mininet.cli import CLI
from mininet.log import setLogLevel, info, error
from mininet.net import Mininet
from mininet.util import quietRun
from mininet.cli import CLI
from mininet import log
from mininet.node import Node
from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink
import subprocess
import yaml
import os

def info(msg):
    log.info(msg + '\n')


if not os.geteuid() == 0:
    exit("This script must be run as root")
else:
   info("Running mininet clean")

subprocess.call(['sudo', 'mn', '-c'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
info("Fresh /etc/hosts")

if __name__ == '__main__':

    setLogLevel( 'info' )



    net = Mininet( topo=None, waitConnected=True, link=partial(TCLink) )
    net.staticArp()

    switch = net.addSwitch('s1',failMode='standalone')


    with open("topo2.yaml", 'r') as file:
        config = yaml.safe_load(file)

    num_hosts = config['nodes']['number']
    edges = config['edges']

    # Create hosts
    hosts = []

    for i in range(num_hosts):
        host = net.addHost(f'h{i+1}', ip="")
        host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((i+1)))

        hosts.append(host)



    network_counter = 0
    delay=None
    # Create links
    for i in range(num_hosts):
        for j in range(i + 1, num_hosts):
            for edge in edges:
                if i+1 == edge['node1'] and j+1 == edge['node2']:
                    delay=edge['delay']
                    break
            ip1 = f"10.0.{network_counter}.1/24"
            ip2 = f"10.0.{network_counter}.2/24"



            host1 = hosts[i]
            host2 = hosts[j]
            if delay is None:
                net.addLink(host1, host2, cls=TCLink,
                params1={'ip': ip1},
                params2={'ip': ip2})
            else:
                net.addLink(host1, host2, cls=TCLink, delay=f'{delay}ms',
                params1={'ip': ip1},
                params2={'ip': ip2})
                info(f"\n {host1} {host2}")
            ip1 = f"10.0.{network_counter}.1"
            ip2 = f"10.0.{network_counter}.2"
            host1.cmd(f'ip route add 10.3.0.{j+1}/32 via {ip2}')
            host2.cmd(f'ip route add 10.3.0.{i+1}/32 via {ip1}')
            info(f'ip route add 10.3.0.{j+1}/32 via {ip2}')
            info(f'ip route add 10.3.0.{i+1}/32 via {ip1}')
            network_counter += 1
            delay=None




    api=net.addHost('h999', ip="10.2.0.1")
    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, api ).intf1
    root.setIP( '10.2.0.99', intf=intf )



    ip_counter = 1
    net.addLink(
         api,switch,params1={'ip': f"10.1.1.{ip_counter}/24"},

    )
    ip_counter += 1


    for host in net.hosts:
        if host is not api:
            net.addLink(
                host, switch, params1={'ip': f"10.1.1.{ip_counter}/24"},
            )
            ip_counter += 1

    net.start()

    info( "Dumping host connections\n" )
    dumpNodeConnections(net.hosts)

    api.cmd('REDIS=10.2.0.99 ./dev/api &')

    template_for_relays = (
        'RUST_LOG=debug RUST_BACKTRACE=0 '

        './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
        '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
        '--tls-disable-verify --dev &'
    )
    host_counter = 1

    for h in net.hosts[:-3]:

        ip_address = f'10.3.0.{host_counter}'
        info(f'Starting relay on {h} - {ip_address}')

        h.cmd(template_for_relays.format(
            host=h.name,
            bind=f'{ip_address}:4443',
            api=f'http://10.1.1.1',
            node=f'https://{ip_address}:4443'
        ))

        host_counter += 1

    first_hop_relay = "10.3.0.2"
    last_hop_relay = "10.3.0.3"
    sleep(0.7)
    info(f'{net.hosts[-2]}  -  {first_hop_relay}')
    net.hosts[-2].cmd(f'xterm -e bash -c "ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - | RUST_LOG=info ./target/debug/moq-pub --name bbb https://{first_hop_relay}:4443 --tls-disable-verify" &')

    # """
    #  h1 ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - | RUST_LOG=warn RUST_BACKTRACE=1 ./target/debug/moq-pub --name bbb https://10.0.2.1:4443 --tls-disable-verify &
    #  h4 RUST_LOG=info RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb https://10.0.2.2:4443 --tls-disable-verify | ffplay -x 200 -y 100 -

    # """

    sleep(0.7)
    net.hosts[-3].cmd(f'xterm -e bash -c "RUST_LOG=info RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb https://{last_hop_relay}:4443 --tls-disable-verify | ffplay -x 200 -y 100 -"&')
    info(f'{net.hosts[-3]}  -  {last_hop_relay}')

    CLI( net )
    net.hosts[-3].cmd('pkill -f xterm')
    net.hosts[-2].cmd('pkill -f xterm')
    net.stop()


