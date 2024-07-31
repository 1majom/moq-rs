#!/usr/bin/python

import os
import subprocess
import yaml
from functools import partial
from time import sleep
from sys import exit  # pylint: disable=redefined-builtin

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.util import dumpNodeConnections, quietRun
from mininet.log import setLogLevel, info, error
from mininet.cli import CLI
from mininet.node import Node, OVSSwitch
from mininet.link import TCLink
from mininet import log

def info(msg):
    log.info(msg + '\n')

my_debug=False
def debug(msg):
    if my_debug:
        log.info(msg + '\n')



if not os.geteuid() == 0:
    exit("** This script must be run as root")
else:
   print("** Running mininet clean")

subprocess.call(['sudo', 'mn', '-c'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("** Getting them needed binaries")
subprocess.run(['sudo', '-u', 'szebala', '/home/szebala/.cargo/bin/cargo', 'build'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if not os.path.exists("topo.yaml"):
    subprocess.run(['cp', './dev/topos/topo_line.yaml', 'topo.yaml'], check=True)

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
    # in the topo2.yaml we get the exact number of needed hosts for the relays, so in the beginning we add 2 more hosts
    # one for the pub and one for the sub
    # but after that the host for the api is also created with the highest number.
    # so if we want to use the hosts which we wanted to use as clients we should choose the -2 and -3 indexes
    # but here we can tell the exact ips of the relays the clients will use
    # > one of the places which you could change the script
    # the first_hop_relay is the relay which the pub will use
    # the last_hop_relay is the relay which the sub(s) will use (with 3 subs the third will fail)
    first_hop_relay = "10.3.0.2"
    last_hop_relay = ["10.3.0.3","10.3.0.1"]
    number_of_clients = len(last_hop_relay)+1
    hosts = []

    for i in range(num_hosts+number_of_clients):
        host = net.addHost(f'h{i+1}', ip="")
        host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((i+1)))

        hosts.append(host)

    # Setting up full mesh network
    network_counter = 0
    delay=None
    for i in range(num_hosts+number_of_clients):
        for j in range(i + 1, num_hosts+number_of_clients):
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
                info(f"\n** the last printed delays are put between {host1} {host2}")
            ip1 = f"10.0.{network_counter}.1"
            ip2 = f"10.0.{network_counter}.2"
            host1.cmd(f'ip route add 10.3.0.{j+1}/32 via {ip2}')
            host2.cmd(f'ip route add 10.3.0.{i+1}/32 via {ip1}')
            debug(f'ip route add 10.3.0.{j+1}/32 via {ip2}')
            debug(f'ip route add 10.3.0.{i+1}/32 via {ip1}')
            network_counter += 1
            delay=None


    api=net.addHost('h999', ip="10.2.0.1")
    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, api ).intf1
    root.setIP( '10.2.0.99', intf=intf )


    # Setting up "api network"
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

    if my_debug:
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
        debug(f'Starting relay on {h} - {ip_address}')

        h.cmd(template_for_relays.format(
            host=h.name,
            bind=f'{ip_address}:4443',
            api=f'http://10.1.1.1',
            node=f'https://{ip_address}:4443'
        ))

        host_counter += 1


    # the two sleeps are needed at that specific line, bc other way they would start and the exact same time,
	# and the pub wouldnt connect to the relay, and the sub couldnt connect to the pub

    sleep(0.7)
    net.hosts[-2].cmd(f'xterm -e bash -c "ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - | RUST_LOG=info ./target/debug/moq-pub --name bbb https://{first_hop_relay}:4443 --tls-disable-verify" &')
    debug(f'{net.hosts[-2]}  -  {first_hop_relay}')
    for i in range(number_of_clients-1):
        le_id=(i+3)
        sleep(0.2)
        net.hosts[-le_id].cmd(f'xterm -e bash -c "RUST_LOG=info RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb https://{last_hop_relay[i]}:4443 --tls-disable-verify | ffplay -window_title pipe{i} -x 360 -y 200 -"&')
        debug(f'{net.hosts[-le_id]}  -  {last_hop_relay[i]}')

    for i in range(number_of_clients-1):
        sleep(1)
        subprocess.call(['xdotool', 'search', '--name', f'pipe{i}', 'windowmove', f'{i*300+0}', '0'])

    CLI( net )
    for i in range(number_of_clients):
        net.hosts[-(i+2)].cmd('pkill -f xterm')

    net.stop()



