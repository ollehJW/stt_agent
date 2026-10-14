#!/usr/bin/env bash
set -euo pipefail
cd /home/jongwook/wiavoice
source /home/jongwook/wiatts/env.sh
export WIAVOICE_DATA=/data/wiavoice
exec python -m uvicorn backend.main:app --host 127.0.0.1 --port 1015 --no-proxy-headers
