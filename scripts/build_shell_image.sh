#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t a2a-shell:latest -f docker/shell/Dockerfile docker/shell
echo "Built a2a-shell:latest"
