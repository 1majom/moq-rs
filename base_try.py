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


#!/usr/bin/env python
tls_verify= os.getenv("TLS_VERIFY", True)

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



def debug(msg):
    if my_debug:
        log.info(msg + '\n')

def main():
    setLogLevel('info')
    template_for_relays = (
        'RUST_LOG=debug RUST_BACKTRACE=0 '
        './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
        '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
        ' {tls_verify} --dev {origi} &'
    )

    with open("../cdn-optimization/datasource/small_topo.yaml", 'r') as file:
        config = yaml.safe_load(file)

    print("** Baking fresh cert")
    ip_string = ' '.join(['12.0.1.2 12.0.1.1 12.0.2.2 12.0.2.1'])
    with open('./dev/cert', 'r') as file:
        cert_content = file.readlines()
    cert_content[-1] = f'go run filippo.io/mkcert -ecdsa -days 10 -cert-file "$CRT" -key-file "$KEY" localhost 127.0.0.1 ::1  {ip_string}'
    with open('./dev/cert2', 'w') as file:
        file.writelines(cert_content)
    env = os.environ.copy()
    env['PATH'] = '/usr/local/go:/usr/local/go/bin:' + env['PATH']
    subprocess.call(['./dev/cert2'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    tls_verify_str = ""
    if not tls_verify:
        tls_verify_str = "--tls-disable-verify"

    current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    assumed_baseline = 0

    net = Mininet(topo=None, waitConnected=False, link=partial(TCLink))
    net.staticArp()

    # Create 3 hosts
    baseline_sub = net.addHost('h1', ip="")
    baseline_relay = net.addHost('h2', ip="")
    baseline_pub = net.addHost('h3', ip="")

    # Connect the hosts
    net.addLink(baseline_pub, baseline_relay,
                params1={'ip': f"12.0.1.1/24"},
                params2={'ip': f"12.0.1.2/24"})
    net.addLink(baseline_relay, baseline_sub,
                params1={'ip': f"12.0.2.2/24"},
                params2={'ip': f"12.0.2.1/24"})

    api=net.addHost('h999', ip="12.2.0.1")
    root = Node( 'root', inNamespace=False )
    intf = net.addLink( root, api ).intf1
    root.setIP( '12.2.0.99', intf=intf )
    net.addLink(
         api,baseline_relay,params1={'ip': f"12.1.0.1/24"},params2={'ip': f"12.1.0.2/24"}
    )
    api.cmd('REDIS=12.2.0.99 ./dev/api --bind [::]:4442 &')

    net.start()
    baseline_sub.cmd('ip route add 12.0.1.0/30 via 12.0.2.2')
    baseline_pub.cmd('ip route add 12.0.2.0/30 via 12.0.1.2')

    # Start the relay on one of the hosts
    baseline_relay.cmd(template_for_relays.format(
        host=baseline_relay,
        bind='12.0.1.2:4443',
        api='http://12.1.0.1:4442',
        node='https://12.0.1.2:4443',
        tls_verify=tls_verify_str,
        origi="--original"
    ))
    sleep(1)
    # Start the publisher on one host
    track = config['first_hop_relay'][0]['track']
    print(f"track: {track}")
    vidi_filenammm = track.split("_")[0]
    baseline_pub.cmd(f'xterm -hold -T "Publisher" -e bash -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; gst-launch-1.0 -q -v -e filesrc location="./dev/{vidi_filenammm}.mp4"  ! qtdemux name=before01 \
  before01.video_0 ! h264parse name=before02 ! avdec_h264 name=before03 ! videoconvert name=before2 ! timestampoverlay name=middle ! videoconvert name=after1 ! x264enc tune=zerolatency name=after2 ! h264parse name=after3 ! isofmp4mux chunk-duration=1 fragment-duration=1 name=after4 ! moqsink tls-disable-verify=true url="https://12.0.1.2:4443" namespace="{track}";sleep 0.1 "&')
    sleep(0.5)
    baseline_sub.cmd(f'xterm -hold -T "Subscriber" -e bash -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; export RST_LOG=debug; ./target/debug/moq-sub --name {track} https://12.0.1.2:4443 | GST_DEBUG=timeoverlayparse:4 gst-launch-1.0 --no-position filesrc location=/dev/stdin ! decodebin ! videoconvert ! timeoverlayparse ! videoconvert ! fakesink 2> measurements/baseline_test_{current_time}.txt.txt" &')
    sleep(10)
    folder_path = 'measurements'
    lat = sorted([file for file in glob.glob(os.path.join(folder_path, '*')) if not file.startswith('measurements/baseline_test_')], key=os.path.getctime, reverse=True)[0]

    with open(lat, 'r') as file:
        file_latencies = []
        for line in file:
            latency = extract_latency(line)
            if latency is not None:
                file_latencies.append(latency)
        if file_latencies:
            average, median, percentile_99 = calculate_statistics(file_latencies)
            print(f"assumed baseline:{average}")
            assumed_baseline = average
            baseline_file = datetime.datetime.now().strftime("measurements/assumedbaseline_%Y%m%d.txt")
            with open(baseline_file, 'w') as file:
                file.write(str(assumed_baseline))

    net.stop()
    print(f"assumed baseline: {assumed_baseline}")
    subprocess.call(['sudo', 'pkill', '-f','xterm'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
