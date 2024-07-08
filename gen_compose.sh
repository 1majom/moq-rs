#!/bin/bash

topology_file=$1

if [ -z "$topology_file" ]; then
	read -p "Please enter topo: " middle_part
	allowed_topologies="spineleaf line star"

	if [[ " $allowed_topologies " =~ " $middle_part " ]]; then
		topology_file="dev/topos/topo_${middle_part}.yaml"
	else
		echo "Invalid topology: $middle_part. Allowed values are $allowed_topologies."
		exit 1
	fi
fi

if [ "$topology_file" == "old" ]; then
	cp dev/topos/topo_old.yaml topo.yaml
    cp docker-compose-old.yml docker-compose.yml
    echo "Using old docker-compose configuration."
    exit 0
fi


relays=($(awk '/nodes:/,/edges:/{if (!/edges:/)print}' $topology_file | grep -v 'nodes:' | tr -d ' -'))

cp $topology_file topo.yaml


cat << EOF > docker-compose.yml
version: "3.8"

x-relay: &x-relay
  build: .
  entrypoint: ["moq-relay"]
  environment:
    RUST_LOG: \${RUST_LOG:-debug}
  volumes:
  - ./dev/localhost.crt:/etc/tls/cert:ro
  - ./dev/localhost.key:/etc/tls/key:ro
  - certs:/etc/ssl/certs
  depends_on:
    install-certs:
      condition: service_completed_successfully

services:
  redis:
    image: redis:7
    ports:
    - "6400:6379"

  api:
    build: .
    volumes:
      - ./topo.yaml:/topo.yaml:ro
    entrypoint: moq-api
    command: --listen [::]:4440 --redis redis://redis:6379 --topo-path topo.yaml
EOF

for relay in "${relays[@]}"; do
cat << EOF >> docker-compose.yml
  relay${relay}:
    <<: *x-relay
    command: --listen [::]:${relay} --tls-cert /etc/tls/cert --tls-key /etc/tls/key --api http://api:4440 --api-node https://localhost:${relay} --dev
    ports:
    - "${relay}:${relay}"
    - "${relay}:${relay}/udp"
EOF
done

cat << EOF >> docker-compose.yml
  install-certs:
    image: golang:latest
    working_dir: /work
    command: go run filippo.io/mkcert -install
    environment:
      CAROOT: /work/caroot
    volumes:
    - \${CAROOT:-.}:/work/caroot
    - certs:/etc/ssl/certs
    - ./dev/go.mod:/work/go.mod:ro
    - ./dev/go.sum:/work/go.sum:ro

volumes:
  certs:
EOF
