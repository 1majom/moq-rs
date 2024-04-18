#!/bin/bash
set -euo pipefail

cleanup() {
	../kill.sh
}

trap cleanup INT EXIT

export RUST_LOG=debug

echo "Starting moq-api"
PORT=4440 ./dev/api &

echo "Starting hub"
export ARGS=""


echo "Starting relays"
for ((i = 3; i <= 5; i++)); do
	export PORT="$((4440 + i))"
	export API="http://localhost:4440"
	export NODE="https://localhost:${PORT}"
	./dev/relay &
done

while true; do
	sleep 100
done
