#!/usr/bin/python

import os
import subprocess
import yaml
from functools import partial
from time import sleep
from sys import exit  # pylint: disable=redefined-builtin

from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.node import Node
from mininet.link import TCLink
from mininet import log
import os
import datetime
import glob
import re
import numpy as np
import re
import os
import datetime
import subprocess

my_debug = os.getenv("MY_DEBUG", False)
all_gas_no_brakes= os.getenv("NO_BRAKES", False)
video_on = os.getenv("LOOKY", False)
forklift_certified = not os.getenv("NO_CERT", False)
num_of_tries = int(os.getenv("NUMERO", 1))
gst_shark = int(os.getenv("SHARK", 0))
topofile= os.getenv("TOPO", "tiniest_topo.yaml")


def info(msg):
    log.info(msg + '\n')

def debug(msg):
    if my_debug:
        log.info(msg + '\n')

def relayid_to_ip(relayname, node_names):
    relayid=node_names.index(relayname) + 1
    return f"10.3.0.{relayid}"

if not os.geteuid() == 0:
    exit("** This script must be run as root")
else:
   print("** Mopping up remaining mininet")
for i in range(num_of_tries):
    subprocess.call(['sudo', 'mn', '-c'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(['sudo', 'pkill', '-f','gst-launch'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("** Folding them needed binaries")
    if my_debug:
        subprocess.run(['rm', 'target/debug/*'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['sudo', '-u', 'szebala', '/home/szebala/.cargo/bin/cargo', 'build'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


    if __name__ == '__main__':

        setLogLevel( 'info' )
        baseline_file = datetime.datetime.now().strftime("assumedbaseline_%Y%m%d.txt")
        baseline_path = os.path.join('measurements', baseline_file)
        based_line=0.0
        print(baseline_path)

        if os.path.exists(baseline_path):
            with open(baseline_path, 'r') as file:
                baseline_content = file.read().strip()

            try:
                based_line = float(baseline_content)

            except ValueError:
                # Start the base_try.py script
                subprocess.call(['sudo', 'python', 'base_try.py'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                with open(baseline_path, 'r') as file:
                    baseline_content = file.read().strip()
                    based_line = float(baseline_content)
        else:
            # Start the base_try.py script
            subprocess.call(['sudo', 'python', 'base_try.py'])

            with open(baseline_path, 'r') as file:
                baseline_content = file.read().strip()
                based_line = float(baseline_content)


        net = Mininet( topo=None, waitConnected=True, link=partial(TCLink) )
        net.staticArp()

        switch = net.addSwitch('s1',failMode='standalone')
        with open(f"../cdn-optimization/datasource/{topofile}", 'r') as file:
            config = yaml.safe_load(file)

        relay_number = len(config['nodes'])


        print("** Sorting out the config")
        node_names = [item['name'] for item in config['nodes']]
        edges = config['edges']
        connections = []
        for edge in edges:
            src = edge['node1']
            dst = edge['node2']
            src_index = node_names.index(src) + 1
            dst_index = node_names.index(dst) + 1
            latency = edge['attributes']['latency']
            connection = {'node1': src_index, 'node2': dst_index, 'delay': latency}
            connections.append(connection)
            debug(f"I see {src} to {dst} at index {connection['node1']} and {connection['node2']} with latency {connection['delay']}ms")
        edges = connections


        print("** Baking fresh cert")
        ip_string = ' '.join([f'10.3.0.{i}' for i in range(1, relay_number+1)])
        with open('./dev/cert', 'r') as file:
            cert_content = file.readlines()
        cert_content[-1] = f'go run filippo.io/mkcert -ecdsa -days 10 -cert-file "$CRT" -key-file "$KEY" localhost 127.0.0.1 ::1  {ip_string}'
        with open('./dev/cert2', 'w') as file:
            file.writelines(cert_content)
        env = os.environ.copy()
        env['PATH'] = '/usr/local/go:/usr/local/go/bin:' + env['PATH']
        subprocess.call(['./dev/cert2'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        """ the different networks are:
        - 10.0.x.0/24 - relay to relay connections where x is a counter
        - 10.1.1.0/24 - api network
        - 10.2.0.0/24 - api to host os connection (for docker)
        - 10.3.0.0/24 - relay identifying ips, on the lo interface of the relays
        - 10.4.x.0/24 - pub and sub to relay connections, where x is a counter
        the first_hop_relay is the relay which the pub will use
        the last_hop_relay is the relay which the sub(s) will use (with 3 subs the third will fail, if sleep is higher than 0.2)
        """

        first_hop_relay = [(relayid_to_ip(item['relayid'], node_names), item['track']) for item in config['first_hop_relay']]
        last_hop_relay = [(relayid_to_ip(item['relayid'], node_names), item['track']) for item in config['last_hop_relay']]

        number_of_clients = len(last_hop_relay)+len(first_hop_relay)
        relays = []
        pubs = []
        subs= []
        k=1


        # ** Creating hosts
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


        # ** Setting up full mesh network
        network_counter = 0
        delay=None
        # *** connecting pubs and subs
        for i in range(relay_number):
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

        # *** connecting relays to each other adding delays
        for i in range(relay_number):
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
                    info(f"\n** this delay is put between {host1} {host2}")
                    net.addLink(host1, host2, cls=TCLink, delay=f'{delay}ms',
                    params1={'ip': ip1},
                    params2={'ip': ip2})
                    info(f"\n")

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


        # *** Setting up "api network"
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

        current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        net.start()

        if my_debug:
            dumpNodeConnections(net.hosts)
            info("pubs: " + str(pubs))
            info("subs: " + str(subs))

        template_for_relays = (
                'RUST_LOG=debug RUST_BACKTRACE=0 '
                './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
                '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
                ' {tls_verify} --dev {origi} &'
            )

        origi_api_str=""
        if config['api']=="origi":
            origi_api_str="--original"
            api.cmd('REDIS=10.2.0.99 ./dev/api --bind [::]:4442 &')
        else:
            if config['api']=="opti":
                api.cmd(f'cd ../cdn-optimization; source venv/bin/activate; TOPOFILE={topofile} python -m fastapi dev app/api.py --host 10.1.1.1 --port 4442 &')

            # else:
            #     api.cmd('REDIS=10.2.0.99 ./dev/api --topo-path topo.yaml --bind [::]:4442 &')
            #     template_for_relays = (
            #         'RUST_LOG=debug RUST_BACKTRACE=0 '
            #         './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
            #         '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
            #         '--tls-disable-verify --dev &'
            #     )

        # for some reason this is needed or the first relay wont reach the api
        # (ffmpeg needs the 1s, gst can work with less)
        sleep(2)

        host_counter = 1

        tls_verify_str = ""
        if not forklift_certified:
            tls_verify_str = "--tls-disable-verify"

        for h in relays:
            ip_address = f'10.3.0.{host_counter}'
            debug(f'Starting relay on {h} - {ip_address}')

            h.cmd(template_for_relays.format(
                host=h.name,
                bind=f'{ip_address}:4443',
                api=f'http://10.1.1.1:4442',
                node=f'https://{ip_address}:4443',
                tls_verify=tls_verify_str,
                origi=origi_api_str
            ))
            debug(template_for_relays.format(
                host=h.name,
                bind=f'{ip_address}:4443',
                api=f'http://10.1.1.1:4442',
                node=f'https://{ip_address}:4443',
                tls_verify=tls_verify_str,
                origi=origi_api_str


            ))

            host_counter += 1


        # the two sleeps are needed at that specific line, bc other way they would start and the exact same time,
        # and the pub wouldn't connect to the relay, and the sub couldn't connect to the pub
        sleep(0.5)
        k=0
        def get_video_duration(file_path):
            command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            output = subprocess.check_output(command).decode().strip()
            duration = float(output)
            return duration

        max_video_duration = 0
        max_resolution=300

        for (h,track) in pubs:
            vidi_filenammm=track.split("_")[0]
            track_duration = get_video_duration(f"./dev/{vidi_filenammm}.mp4")
            if track_duration > max_video_duration:
                max_video_duration = track_duration

            resolution=track.split("_")[0].split("-")[1]
            if int(resolution)>max_resolution:
                max_resolution=int(resolution)

            if config['mode'] == 'clock':
                le_cmd=(f'xterm -hold  -T "{h.name}-pub" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --publish --namespace {track} https://{first_hop_relay[k][0]}:4443 --tls-disable-verify" &')
            else:
                if config['mode'] == 'ffmpeg':
                    le_cmd=(f'xterm -hold -T "{h.name}-pub" -e bash -c "ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/{vidi_filenammm}.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - '
                        f' | RUST_LOG=info ./target/debug/moq-pub --name {track} https://{first_hop_relay[k][0]}:4443 --tls-disable-verify" &')
                else:
                    if config['mode'] == 'gst':
                        holder=" "
                        if my_debug:
                            holder=" -hold "
                        gst_shark_str=""
                        if gst_shark>0:
                            gst_shark_str='export GST_DEBUG="GST_TRACER:7"; export GST_SHARK_CTF_DISABLE=TRUE; '
                        if gst_shark==1:
                            gst_shark_str+='export GST_TRACERS="proctime";'
                        if gst_shark==2:
                            gst_shark_str+='export GST_TRACERS="interlatency";'

                        le_cmd=f'xterm {holder} -T "{h.name}-pub" -e bash -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; {gst_shark_str} gst-launch-1.0 -q -v -e filesrc location="./dev/{vidi_filenammm}.mp4"  ! qtdemux name=before01 \
  before01.video_0 ! h264parse name=before02 ! avdec_h264 name=before03 ! videoconvert name=before2 ! timestampoverlay name=middle ! videoconvert name=after1 ! x264enc tune=zerolatency name=after2 ! h264parse name=after3 ! isofmp4mux chunk-duration=1 fragment-duration=1 name=after4 ! moqsink tls-disable-verify=true url="https://{first_hop_relay[k][0]}:4443" namespace="{track}" 2> measurements/baseline_{track}_{current_time}_{h.name}.txt ; sleep 3 "&'

            debug(f'{h}  -  {le_cmd}')
            debug(f'{h}  -  {first_hop_relay[k][0]}')
            h.cmd(le_cmd)
            sleep(0.2)
            k+=1

        # if this is 1.5 or more it will cause problems
        # around 0.7 needed
        sleep(0.7)


        k=0
        for (h,track) in subs:
            if config['mode'] == 'clock':
                le_cmd=(f'xterm -hold  -T "{h.name}-sub-t" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --namespace {track} https://{last_hop_relay[k][0]}:4443 --tls-disable-verify" &')
            else:
                if config['mode'] == 'ffmpeg':
                      le_cmd=(f'xterm -hold -T "{h.name}-sub-t" -e bash  -c "RUST_LOG=info RUST_BACKTRACE=1 ./target/debug/moq-sub --name {track} https://{last_hop_relay[k][0]}:4443 '
                  f' --tls-disable-verify | ffplay -window_title \'{h.name}sub\' -x 360 -y 200 - "&')
                else:
                    filename = f"measurements/{track}_{current_time}_{h.name}"
                    le_sink="autovideosink"
                    if not video_on:
                        le_sink="fakesink"

                    le_cmd=f'xterm  -hold  -T "{h.name}-sub-t" -e bash  -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; export RUST_LOG=info; ./target/debug/moq-sub --name {track} https://{last_hop_relay[k][0]}:4443 | GST_DEBUG=timeoverlayparse:4 gst-launch-1.0 --no-position filesrc location=/dev/stdin ! decodebin ! videoconvert ! timeoverlayparse ! videoconvert ! {le_sink} 2> {filename}.txt" &'

            h.cmd(le_cmd)
            debug(f'{h}  -  {le_cmd}')
            debug(f'{h}  -  {last_hop_relay[k][0]}')
            sleep(0.2)
            k+=1

        sleep(1)

        if video_on:

            if config['mode'] == 'gst':
                sleep(2)
                try:
                    output = subprocess.check_output(['xdotool', 'search', '--name', 'gst-launch'])
                    process_ids = output.decode().split()
                    for i, process_id in enumerate(process_ids):
                        sleep(0.2)
                        subprocess.call(['xdotool', 'windowmove', process_id, f'{i*max_resolution+50}', '0'])
                except subprocess.CalledProcessError:
                        print("No windows found with the name 'gst-launch'")
            else:
                if config['mode'] == 'ffmpeg':
                    for i in range(len(subs)):
                        sleep(0.2)
                        subprocess.call(['xdotool', 'search', '--name', f'h{i}sub', 'windowmove', f'{i*max_resolution+50}', '0'])



        if all_gas_no_brakes:
            sleep(max_video_duration+3)
        else:
            CLI( net )


        for (h,_) in pubs:
            if config['mode'] == 'gst':
                h.cmd('pkill -f gst-launch')
            h.cmd('pkill -f xterm')
        for (h,_) in subs:
            if config['mode'] == 'gst':
                h.cmd('pkill -f gst-launch')
            h.cmd('pkill -f xterm')

        net.stop()
        if (config['mode'] == 'gst'):
            folder_path='measurements'
            list_of_files = [file for file in glob.glob(os.path.join(folder_path, '*')) if not file.startswith('measurements/baseline')]
            latest_files = sorted(list_of_files, key=os.path.getctime, reverse=True)[:len(subs)]
            if gst_shark>0:
                print("latest_files: ", latest_files)
                baseline_files = glob.glob(os.path.join(folder_path, 'baseline*'))
                baseline_file = max(baseline_files, key=os.path.getctime)
                print("baseline_file: ", baseline_file)
                if gst_shark==1:
                    baseline=0
                    with open(baseline_file, 'r') as file:
                        for line in file:
                            element_counts = {}
                            element_sums = {}
                            element_avarages={}
                            for line in file:
                                match = re.search(r'element=\(string\)(\w+), time=\(string\)0:00:00.(\d+)', line)

                                if match:
                                    element = match.group(1)
                                    if element in element_counts:
                                        element_counts[element] += 1
                                    else:
                                        element_counts[element] = 1
                                    time= int(match.group(2))
                                    if element in element_sums:
                                        element_sums[element] += time
                                    else:
                                        element_sums[element] = time

                            for element, count in element_counts.items():
                                print(f"Element: {element}, Count: {count}, sum: {element_sums[element]}, av:{element_sums[element]/count}")
                                element_avarages[element]=element_sums[element]/count
                        element_avarages.pop('middle')
                        baselines = [value for key, value in element_avarages.items() if key.startswith('after')]
                        baseline = sum(baselines)/1e9
                else:
                    if gst_shark==2:
                        baseline=0
                        baseline_plus = []
                        baseline_minus = []
                        with open(baseline_file, 'r') as file:
                            with open('test.txt', 'w') as test_file:
                                for line in file:
                                    match = re.search(r'filesrc0_src, to_pad=\(string\)moqsink0_sink, time=\(string\)0:00:00\.(\d+);', line)
                                    if match:
                                        baseline_plus.append(int(match.group(1)))

                                    match = re.search(r'filesrc0_src, to_pad=\(string\)middle_src, time=\(string\)0:00:00\.(\d+);', line)
                                    if match:
                                        baseline_minus.append(int(match.group(1)))

                            baseline = (sum(baseline_plus) / len(baseline_plus)) / 1e9 - (sum(baseline_minus) / len(baseline_minus)) / 1e9


            latencies = []
            def calculate_statistics(latencies):
                average = np.mean(latencies)
                median = np.median(latencies)
                percentile_99 = np.percentile(latencies, 99)
                return average/1e9, median/1e9, percentile_99/1e9
            def extract_latency(line):
                match = re.search(r'Latency: (\d+)', line)
                if match:
                    return int(match.group(1))
                return None
            for file_path in latest_files:
                with open(file_path, 'r') as file:
                    file_latencies = []
                    for line in file:
                        latency = extract_latency(line)
                        if latency is not None:
                            file_latencies.append(latency)
                    if file_latencies:
                        average, median, percentile_99 = calculate_statistics(file_latencies)
                        with open(f"measurements/{current_time}_enddelays.txt", 'a') as enddelays_file:
                            enddelays_file.write(f"{filename}.txt\n")
                            enddelays_file.write(f">> average; median; percentile_99 timestampoverlay data: {average}; {median}; {percentile_99}\n")
                            enddelays_file.write(f">> subtracting based line: {average-based_line}\n")
                            if gst_shark == 2:
                                enddelays_file.write(f">> subtracting average interlatency: {average-baseline}\n")
                            if gst_shark == 1:
                                enddelays_file.write(f">> subtracting average proctimes: {average-baseline}\n")

                        print(f">> average; median; percentile_99 timestampoverlay data: {average}; {median}; {percentile_99}")
                        print(f">> subtracting based line: {average-based_line}")
                        if gst_shark == 2:
                            print(f">> subtracting average interlatency: {average-baseline}")
                        if gst_shark == 1:
                            print(f">> subtracting average proctimes: {average-baseline}")





