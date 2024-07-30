#!/usr/bin/python
"""
This is the most simple example to showcase Containernet.
"""
from mininet.net import Containernet
from mininet.node import Controller
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
setLogLevel('debug')

net = Containernet(controller=Controller)
info('*** Adding controller\n')
net.addController('c0')
info('*** Adding docker containers\n')

# moq-rs-dir      latest    0073cbea1ebf   32 minutes ago   847MB
# moq-rs-relay2   latest    3731b76e78da   32 minutes ago   847MB
# moq-rs-api      latest    2bdda06dc79d   32 minutes ago   847MB
# moq-rs-relay1   latest    81c44dbbc760   32 minutes ago   847MB
# redis           7         aceb1262c1ea   4 weeks ago      117MB
d1 = net.addDocker('redis', ip='10.0.0.2', dimage="leredis", dcmd="redis-server")
d2 = net.addDocker('moq-rs-api', ip='10.0.0.3', dimage="lemoq", dcmd="moq-api --redis redis://10.0.0.2:6379", ports=[80])


d3 = net.addDocker('moq-rs-dir', ip='10.0.0.4', dimage="lemoq", dcmd="moq-dir --tls-cert /etc/tls/cert --tls-key /etc/tls/key",volumes=["/home/szebala/Proj/moq-rs/dev/localhost.crt:/etc/tls/cert", "/home/szebala/Proj/moq-rs/dev/localhost.key:/etc/tls/key", "/var/lib/docker/volumes/certs:/etc/ssl/certs"], ports=[(443])
d4 = net.addDocker('moq-rs-relay1', ip='10.0.0.5', dimage="lemoq", dcmd="moq-relay  --tls-cert /etc/tls/cert --tls-key /etc/tls/key --tls-disable-verify --api http://10.0.0.3 --node https://10.0.0.5 --dev --announce https://10.0.0.4",volumes=["/home/szebala/Proj/moq-rs/dev/localhost.crt:/etc/tls/cert", "/home/szebala/Proj/moq-rs/dev/localhost.key:/etc/tls/key", "/var/lib/docker/volumes/certs:/etc/ssl/certs"],ports=[443], port_bindings={443: 4443})
d5 = net.addDocker('moq-rs-relay2', ip='10.0.0.6', dimage="lemoq", dcmd="moq-relay  --tls-cert /etc/tls/cert --tls-key /etc/tls/key --tls-disable-verify --api http://10.0.0.3 --node https://10.0.0.6 --dev --announce https://10.0.0.4", volumes=["/home/szebala/Proj/moq-rs/dev/localhost.crt:/etc/tls/cert", "/home/szebala/Proj/moq-rs/dev/localhost.key:/etc/tls/key", "/var/lib/docker/volumes/certs:/etc/ssl/certs"],ports=[443], port_bindings={443: 4444})

info('*** Adding switches\n')
s1 = net.addSwitch('s1')
s2 = net.addSwitch('s2')
info('*** Creating links\n')
net.addLink(d1, s1)
net.addLink(s1, s2, cls=TCLink, delay='100ms', bw=1)
net.addLink(s2, d2)
info('*** Starting network\n')
net.start()
info('*** Testing connectivity\n')
net.ping([d1, d2])
info('*** Running CLI\n')
CLI(net)
info('*** Stopping network')
net.stop()

