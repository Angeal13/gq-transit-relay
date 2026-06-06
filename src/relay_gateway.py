# relay_gateway.py — Bioko Intranet District Relay Node
# Runs on the Raspberry Pi 3 at each district terminal.
#
# Responsibilities:
#   1. Transparent HTTP proxy: buses POST to http://bioko-server/api/*
#      which dnsmasq resolves to the city hall IP over the backbone.
#      No special Pi config needed — buses just use the same SERVER_URL.
#   2. Local cache: if the backbone link to City Hall is down,
#      incoming bus events are stored in SQLite and forwarded when
#      the backbone recovers.
#   3. Health reporter: POSTs this relay node's status to City Hall every 60s.
#   4. Bus tracker: logs which bus IDs are currently connected via DHCP.

import os
import time
import json
import sqlite3
import logging
import threading
import subprocess
from datetime import datetime

import requests
from flask import Flask, request, jsonify, Response

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/opt/bioko_relay/relay.log', mode='a'),
    ]
)
logger = logging.getLogger('relay')

# ── Config from .env ──────────────────────────────────────────────────────────
NODE_NAME    = os.getenv('NODE_NAME',    'unknown')
CITYHAL_IP   = os.getenv('CITYHAL_IP',   '10.10.0.1')
API_KEY      = os.getenv('API_KEY',      '')
CACHE_DB     = os.getenv('RELAY_CACHE_DB', '/opt/bioko_relay/cache.db')
HEALTH_INTERVAL = int(os.getenv('HEALTH_REPORT_INTERVAL', '60'))
UPSTREAM_BASE   = f"http://{CITYHAL_IP}"
LISTEN_PORT     = 5000   # same port as city hall — Pi buses use identical URL

app = Flask(__name__)


# ── SQLite offline cache ──────────────────────────────────────────────────────

def init_cache():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_queue (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint  TEXT    NOT NULL,
            payload   TEXT    NOT NULL,
            headers   TEXT    NOT NULL,
            queued_at TEXT    NOT NULL,
            attempts  INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"Cache DB ready: {CACHE_DB}")


def cache_event(endpoint: str, payload: dict, headers: dict):
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "INSERT INTO event_queue (endpoint, payload, headers, queued_at) VALUES (?,?,?,?)",
        (endpoint, json.dumps(payload), json.dumps(dict(headers)),
         datetime.utcnow().isoformat())
    )
    conn.commit()
    size = conn.execute("SELECT COUNT(*) FROM event_queue").fetchone()[0]
    conn.close()
    logger.warning(f"Backbone down — queued event. Queue size: {size}")


def flush_cache():
    """Try to forward all queued events to City Hall. Called after backbone recovers."""
    conn = sqlite3.connect(CACHE_DB)
    rows = conn.execute(
        "SELECT id, endpoint, payload, headers FROM event_queue ORDER BY id ASC LIMIT 100"
    ).fetchall()
    conn.close()

    if not rows:
        return 0

    forwarded = 0
    for row_id, endpoint, payload_str, headers_str in rows:
        try:
            headers = json.loads(headers_str)
            headers['X-Relay-Node'] = NODE_NAME
            headers['X-Relay-Flush'] = 'true'
            r = requests.post(
                f"{UPSTREAM_BASE}{endpoint}",
                json=json.loads(payload_str),
                headers=headers,
                timeout=8
            )
            r.raise_for_status()
            conn = sqlite3.connect(CACHE_DB)
            conn.execute("DELETE FROM event_queue WHERE id=?", (row_id,))
            conn.commit()
            conn.close()
            forwarded += 1
        except Exception as e:
            logger.warning(f"Flush failed for event {row_id}: {e}")
            break   # backbone still down — stop trying

    if forwarded:
        logger.info(f"Flushed {forwarded} cached events to City Hall.")
    return forwarded


# ── Backbone health check ─────────────────────────────────────────────────────

_backbone_up = True
_backbone_lock = threading.Lock()

def check_backbone() -> bool:
    try:
        r = requests.get(f"{UPSTREAM_BASE}/api/positions?region=Bioko",
                         timeout=4)
        return r.status_code < 500
    except Exception:
        return False


def backbone_monitor():
    global _backbone_up
    while True:
        time.sleep(15)
        up = check_backbone()
        with _backbone_lock:
            was_up = _backbone_up
            _backbone_up = up
        if up and not was_up:
            logger.info("Backbone recovered — flushing cache.")
            flush_cache()
        elif not up and was_up:
            logger.warning("Backbone link to City Hall is DOWN.")


# ── Transparent proxy ─────────────────────────────────────────────────────────
# All Pi bus API calls land here because dnsmasq resolves 'bioko-server'
# to this relay node's IP. We forward them to City Hall, or cache if down.

PROXY_ENDPOINTS = [
    '/api/bus/stop',
    '/api/bus/heartbeat',
    '/api/bus/register',
    '/api/engine/reading',
]

@app.route('/api/<path:subpath>', methods=['GET', 'POST'])
def proxy(subpath):
    endpoint = f"/api/{subpath}"
    method   = request.method

    # For GET requests (route downloads, positions), always try to forward live
    if method == 'GET':
        try:
            upstream_headers = {
                k: v for k, v in request.headers if k not in ('Host', 'Content-Length')
            }
            upstream_headers['X-Relay-Node'] = NODE_NAME
            r = requests.get(
                f"{UPSTREAM_BASE}{endpoint}",
                params=request.args,
                headers=upstream_headers,
                timeout=8
            )
            return Response(r.content, status=r.status_code,
                            content_type=r.headers.get('Content-Type', 'application/json'))
        except Exception as e:
            logger.warning(f"GET proxy failed for {endpoint}: {e}")
            return jsonify({'error': 'relay: upstream unavailable'}), 503

    # For POST requests (events), cache if backbone is down
    if method == 'POST':
        payload = request.get_json(force=True) or {}
        fwd_headers = {
            k: v for k, v in request.headers if k not in ('Host', 'Content-Length')
        }
        fwd_headers['X-Relay-Node'] = NODE_NAME

        with _backbone_lock:
            backbone_available = _backbone_up

        if backbone_available:
            try:
                r = requests.post(
                    f"{UPSTREAM_BASE}{endpoint}",
                    json=payload,
                    headers=fwd_headers,
                    timeout=8
                )
                r.raise_for_status()
                return jsonify({'status': 'ok', 'via': f'relay:{NODE_NAME}'}), r.status_code
            except Exception as e:
                logger.warning(f"POST forward failed for {endpoint}: {e}. Caching.")
                with _backbone_lock:
                    _backbone_up = False

        # Cache the event
        cache_event(endpoint, payload, fwd_headers)
        return jsonify({'status': 'queued', 'relay': NODE_NAME}), 202

    return jsonify({'error': 'method not supported'}), 405


# ── Health reporter ───────────────────────────────────────────────────────────

def get_connected_buses() -> list:
    """Read dnsmasq DHCP leases to see which buses are currently connected."""
    buses = []
    leases_file = '/var/lib/misc/dnsmasq.leases'
    try:
        with open(leases_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 4:
                    # Format: expiry mac ip hostname
                    buses.append({'ip': parts[2], 'hostname': parts[3]})
    except FileNotFoundError:
        pass
    return buses


def get_cache_size() -> int:
    try:
        conn = sqlite3.connect(CACHE_DB)
        n = conn.execute("SELECT COUNT(*) FROM event_queue").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def get_signal_strength() -> dict:
    """Read Ubiquiti radio signal via iwconfig (if available)."""
    try:
        result = subprocess.run(['iwconfig', 'eth0'], capture_output=True, text=True, timeout=3)
        # Parse signal level from iwconfig output
        for line in result.stdout.split('\n'):
            if 'Signal level' in line:
                parts = line.split('Signal level=')
                if len(parts) > 1:
                    level = parts[1].split(' ')[0]
                    return {'signal_dbm': level, 'source': 'iwconfig'}
    except Exception:
        pass
    return {'signal_dbm': 'unknown', 'source': 'unavailable'}


def health_reporter():
    while True:
        time.sleep(HEALTH_INTERVAL)
        try:
            with _backbone_lock:
                backbone_available = _backbone_up

            report = {
                'node_name':       NODE_NAME,
                'backbone_up':     backbone_available,
                'cache_size':      get_cache_size(),
                'connected_buses': get_connected_buses(),
                'signal':          get_signal_strength(),
                'timestamp':       datetime.utcnow().isoformat() + 'Z',
            }
            if backbone_available:
                requests.post(
                    f"{UPSTREAM_BASE}/api/relay/health",
                    json=report,
                    headers={'X-API-Key': API_KEY},
                    timeout=8
                )
                logger.info(
                    f"Health report sent: backbone={'UP'}, "
                    f"buses={len(report['connected_buses'])}, "
                    f"cache={report['cache_size']}"
                )
        except Exception as e:
            logger.warning(f"Health report failed: {e}")


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_cache()

    # Flush any events cached from before this boot
    if check_backbone():
        flush_cache()
    else:
        logger.warning("Backbone not reachable at startup — will retry every 15s.")

    threading.Thread(target=backbone_monitor, daemon=True, name='backbone-monitor').start()
    threading.Thread(target=health_reporter,  daemon=True, name='health-reporter').start()

    logger.info(
        f"Relay node '{NODE_NAME}' listening on :{LISTEN_PORT} | "
        f"Upstream: {UPSTREAM_BASE}"
    )
    app.run(host='0.0.0.0', port=LISTEN_PORT, threaded=True)
