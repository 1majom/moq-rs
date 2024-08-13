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
import os

my_debug = os.getenv("MY_DEBUG", False)


def info(msg):
    log.info(msg + '\n')

def debug(msg):
    if my_debug:
        log.info(msg + '\n')

if not os.geteuid() == 0:
    exit("** This script must be run as root")
else:
   print("** Running mininet clean")

def relayid_to_ip(relayid):
    return f"10.3.0.{relayid}"

subprocess.call(['sudo', 'mn', '-c'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("** Getting them needed binaries")
if my_debug:
    subprocess.run(['rm', 'target/debug/*'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

subprocess.run(['sudo', '-u', 'szebala', '/home/szebala/.cargo/bin/cargo', 'build'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if not os.path.exists("topo.yaml"):
    subprocess.run(['cp', './dev/topos/topo_line.yaml', 'topo.yaml'], check=True)

if __name__ == '__main__':

    setLogLevel( 'info' )

    net = Mininet( topo=None, waitConnected=True, link=partial(TCLink) )
    net.staticArp()

    switch = net.addSwitch('s1',failMode='standalone')
    with open("topo.yaml", 'r') as file:
        config = yaml.safe_load(file)

    original_api = config['origi_api']
    relay_number = len(config['nodes'])

    ip_string = ' '.join([f'10.3.0.{i}' for i in range(1, relay_number+1)])
    with open('./dev/cert', 'r') as file:
        cert_content = file.readlines()
    cert_content[-1] = f'go run filippo.io/mkcert -ecdsa -days 10 -cert-file "$CRT" -key-file "$KEY" localhost 127.0.0.1 ::1  {ip_string}'
    with open('./dev/cert', 'w') as file:
        file.writelines(cert_content)

    edges = config['delays']
    # the different networks are:
    # 10.0.x/24 - relay to relay connections there x is a counter
    # 10.1.1/24 - api network
    # 10.2.0/24 - api to host os connection (for docker)
    # 10.3.0/24 - relay identifing ips, on the lo interface of relays
    # 10.4.x/24 - pub and sub to relay connections, there x is a counter
    # the first_hop_relay is the relay which the pub will use
    # the last_hop_relay is the relay which the sub(s) will use (with 3 subs the third will fail, if sleep is higher than 0.2)
    first_hop_relay = [(relayid_to_ip(item['relayid']), item['track']) for item in config['first_hop_relay']]
    last_hop_relay = [(relayid_to_ip(item['relayid']), item['track']) for item in config['last_hop_relay']]

    number_of_clients = len(last_hop_relay)+len(first_hop_relay)
    relays = []
    pubs = []
    subs= []
    k=1
    # Create hosts

    for i in range(relay_number):
        host = net.addHost(f'h{k}', ip="")
        host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((k)))
        relays.append(host)

        k += 1

    for i in range(len(first_hop_relay)):
        host = net.addHost(f'h{k}', ip="")
        host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((k)))
        pubs.append((host,first_hop_relay[i][1]))

        k += 1

    for i in range(len(last_hop_relay)):
        host = net.addHost(f'h{k}', ip="")
        host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((k)))
        subs.append((host,last_hop_relay[i][1]))

        k += 1




    # Setting up full mesh network
    network_counter = 0
    delay=None
    for i in range(relay_number):
        # connecting pubs and subs
        matching_pubs = [g for g, (ip, _) in enumerate(first_hop_relay) if ip.split('.')[-1] == str(i+1)]
        for index in matching_pubs:
            net.addLink( pubs[index][0],relays[i],
                params1={'ip': f"10.4.{network_counter}.{2*index+1}/24"},
                params2={'ip':  f"10.4.{network_counter}.{2*index+2}/24"})
            pubs[index][0].cmd(f'ip route add 10.3.0.{i+1}/32 via 10.4.{network_counter}.{2*index+2}')
            debug(f'ip route add 10.3.0.{i+1}/32 via 10.4.{network_counter}.{2*index+2}')
            network_counter += 1

        matching_subs = [g for g, (ip, _) in enumerate(last_hop_relay) if ip.split('.')[-1] == str(i+1)]
        for index in matching_subs:
            net.addLink( subs[index][0],relays[i],
                params1={'ip': f"10.5.{network_counter}.{2*index+1}/24"},
                params2={'ip':  f"10.5.{network_counter}.{2*index+2}/24"})
            subs[index][0].cmd(f'ip route add 10.3.0.{i+1}/32 via 10.5.{network_counter}.{2*index+2}')
            debug(f'ip route add 10.3.0.{i+1}/32 via 10.5.{network_counter}.{2*index+2}')
            network_counter += 1
    for i in range(relay_number):
        # connecting relays to each other adding delays
        for j in range(i + 1, relay_number):
            for edge in edges:
                if i+1 == edge['node1'] and j+1 == edge['node2']:
                    delay=edge['delay']
                    break
            ip1 = f"10.0.{network_counter}.1/24"
            ip2 = f"10.0.{network_counter}.2/24"

            host1 = relays[i]
            host2 = relays[j]
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


    for host in relays:
            net.addLink(
                host, switch, params1={'ip': f"10.1.1.{ip_counter}/24"},
            )
            ip_counter += 1

    net.start()

    if my_debug:
        dumpNodeConnections(net.hosts)
        info("pubs: " + str(pubs))
        info("subs: " + str(subs))


    template_for_relays=""
    if original_api:
        api.cmd('REDIS=10.2.0.99 ./dev/api &')
        template_for_relays = (
            'RUST_LOG=debug RUST_BACKTRACE=0 '
            './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
            '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
            '--tls-disable-verify --dev --original &'
        )
    else:
        api.cmd('REDIS=10.2.0.99 ./dev/api --topo-path topo.yaml &')
        template_for_relays = (
            'RUST_LOG=debug RUST_BACKTRACE=0 '
            './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
            '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
            '--tls-disable-verify --dev &'
        )




    host_counter = 1

    for h in relays:
        ip_address = f'10.3.0.{host_counter}'
        debug(f'Starting relay on {h} - {ip_address}')

        h.cmd(template_for_relays.format(
            host=h.name,
            bind=f'{ip_address}:4443',
            api=f'http://10.1.1.1',
            node=f'https://{ip_address}:4443'
        ))
        debug(template_for_relays.format(
            host=h.name,
            bind=f'{ip_address}:4443',
            api=f'http://10.1.1.1',
            node=f'https://{ip_address}:4443'
        ))

        host_counter += 1


    # the two sleeps are needed at that specific line, bc other way they would start and the exact same time,
    # and the pub wouldnt connect to the relay, and the sub couldnt connect to the pub

    sleep(0.7)
    k=0
    for (h,track) in pubs:
        if config['clock']:
            le_cmd=(f'xterm -hold  -T "h{k}-pub" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --publish --namespace {track} https://{first_hop_relay[k][0]}:4443 --tls-disable-verify" &')
        else:
            le_cmd=(f'xterm -hold -T "h{k}-pub" -e bash -c "ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/{track}.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - '
                    f' | RUST_LOG=info ./target/debug/moq-pub --name {track} https://{first_hop_relay[k][0]}:4443 --tls-disable-verify" &')
        h.cmd(le_cmd)
        debug(f'{h}  -  {le_cmd}')
        debug(f'{net.hosts[k]}  -  {first_hop_relay[k][0]}')
        sleep(0.2)
        k+=1

    # net.hosts[-2].cmd(f'xterm -e bash -c "ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - | RUST_LOG=info ./target/debug/moq-pub --name bbb https://{first_hop_relay}:4443 --tls-disable-verify" &')

    k=0
    for (h,track) in subs:
        if config['clock']:
            le_cmd=(f'xterm -hold  -T "h{k}-sub-t" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --namespace {track} https://{last_hop_relay[k][0]}:4443 --tls-disable-verify" &')
        else:
            le_cmd=(f'xterm -hold -T "h{k}-sub-t" -e bash  -c "RUST_LOG=info RUST_BACKTRACE=1 ./target/debug/moq-sub --name {track} https://{last_hop_relay[k][0]}:4443 '
              f' --tls-disable-verify | ffplay -window_title \'h{k}sub\' -x 360 -y 200 -"&')

        h.cmd(le_cmd)
        debug(f'{h}  -  {le_cmd}')
        debug(f'{h}  -  {last_hop_relay[k][0]}')
        sleep(0.2)
        k+=1

    sleep(1)

    for i in range(len(subs)):
        sleep(0.2)
        subprocess.call(['xdotool', 'search', '--name', f'h{i}sub', 'windowmove', f'{i*360+50}', '0'])

    CLI( net )
    for (h,_) in pubs:
        h.cmd('pkill -f xterm')
    for (h,_) in subs:
        h.cmd('pkill -f xterm')

    net.stop()



