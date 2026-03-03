#!/usr/bin/env python3
"""
postfiatd_exporter.py — Prometheus exporter for Post Fiat / XRPL-fork validators.

Scrapes the postfiatd JSON-RPC API and exposes metrics at /metrics.
Also monitors file integrity (SHA-256) for critical config files.

Default port: 9750
"""

import argparse
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import requests
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Enum,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    start_http_server,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("postfiatd_exporter")

# ═══════════════════════════════════════════════════════════════════
# Registry & Metrics
# ═══════════════════════════════════════════════════════════════════

registry = CollectorRegistry()

# -- Exporter health --
SCRAPE_DURATION = Histogram(
    "postfiatd_scrape_duration_seconds",
    "Time spent scraping postfiatd",
    registry=registry,
)
SCRAPE_ERRORS = Counter(
    "postfiatd_scrape_errors_total",
    "Total scrape errors",
    ["method"],
    registry=registry,
)
EXPORTER_UP = Gauge(
    "postfiatd_up",
    "Whether postfiatd RPC is reachable (1=up, 0=down)",
    registry=registry,
)

# -- Node identity --
NODE_INFO = Info(
    "postfiatd_node",
    "Static node identity info",
    registry=registry,
)

# -- Server state --
SERVER_STATE = Enum(
    "postfiatd_server_state",
    "Current server state",
    states=[
        "disconnected", "connected", "syncing",
        "tracking", "full", "proposing", "validating",
    ],
    registry=registry,
)
SERVER_STATE_DURATION = Gauge(
    "postfiatd_server_state_duration_seconds",
    "Duration in current server state",
    registry=registry,
)
UPTIME = Gauge(
    "postfiatd_uptime_seconds",
    "Server uptime in seconds",
    registry=registry,
)

# -- Ledger --
LEDGER_SEQ = Gauge(
    "postfiatd_validated_ledger_seq",
    "Latest validated ledger sequence number",
    registry=registry,
)
LEDGER_AGE = Gauge(
    "postfiatd_validated_ledger_age_seconds",
    "Age of latest validated ledger in seconds",
    registry=registry,
)
LEDGER_HASH = Info(
    "postfiatd_validated_ledger",
    "Latest validated ledger hash",
    registry=registry,
)
LEDGER_BASE_FEE = Gauge(
    "postfiatd_base_fee_xrp",
    "Base transaction fee in XRP",
    registry=registry,
)
LEDGER_RESERVE_BASE = Gauge(
    "postfiatd_reserve_base_xrp",
    "Base reserve in XRP",
    registry=registry,
)
LEDGER_RESERVE_INC = Gauge(
    "postfiatd_reserve_inc_xrp",
    "Reserve increment in XRP",
    registry=registry,
)

# -- Peers --
PEERS_TOTAL = Gauge(
    "postfiatd_peers_total",
    "Total connected peers",
    registry=registry,
)
PEERS_BY_TYPE = Gauge(
    "postfiatd_peers_by_type",
    "Peers by connection type",
    ["type"],
    registry=registry,
)
PEER_DISCONNECTS = Gauge(
    "postfiatd_peer_disconnects_total",
    "Total peer disconnections",
    registry=registry,
)
PEER_DISCONNECTS_RESOURCES = Gauge(
    "postfiatd_peer_disconnects_resources_total",
    "Peer disconnections due to resource limits",
    registry=registry,
)

# -- Consensus --
LOAD_FACTOR = Gauge(
    "postfiatd_load_factor",
    "Current load factor (1 = normal)",
    registry=registry,
)
IO_LATENCY = Gauge(
    "postfiatd_io_latency_ms",
    "I/O latency in milliseconds",
    registry=registry,
)
VALIDATION_QUORUM = Gauge(
    "postfiatd_validation_quorum",
    "Number of trusted validators needed for consensus",
    registry=registry,
)
LAST_CLOSE_CONVERGE = Gauge(
    "postfiatd_last_close_converge_seconds",
    "Last close convergence time in seconds",
    registry=registry,
)
LAST_CLOSE_PROPOSERS = Gauge(
    "postfiatd_last_close_proposers",
    "Number of proposers in last close",
    registry=registry,
)
JQ_TRANS_OVERFLOW = Gauge(
    "postfiatd_jq_trans_overflow",
    "Job queue transaction overflow count",
    registry=registry,
)

# -- State accounting --
STATE_DURATION = Gauge(
    "postfiatd_state_accounting_duration_seconds",
    "Total time spent in each server state",
    ["state"],
    registry=registry,
)
STATE_TRANSITIONS = Gauge(
    "postfiatd_state_accounting_transitions_total",
    "Number of transitions into each server state",
    ["state"],
    registry=registry,
)

# -- Fee info --
FEE_CURRENT_LEDGER_SIZE = Gauge(
    "postfiatd_fee_current_ledger_size",
    "Number of transactions in the current open ledger",
    registry=registry,
)
FEE_CURRENT_QUEUE_SIZE = Gauge(
    "postfiatd_fee_current_queue_size",
    "Number of transactions waiting in the queue",
    registry=registry,
)
FEE_DROPS_MINIMUM = Gauge(
    "postfiatd_fee_drops_minimum",
    "Minimum fee in drops for the current open ledger",
    registry=registry,
)
FEE_DROPS_MEDIAN = Gauge(
    "postfiatd_fee_drops_median",
    "Median fee in drops",
    registry=registry,
)
FEE_DROPS_OPEN_LEDGER = Gauge(
    "postfiatd_fee_drops_open_ledger",
    "Fee to enter the open ledger in drops",
    registry=registry,
)

# -- Amendments --
AMENDMENTS_ENABLED = Gauge(
    "postfiatd_amendments_enabled_total",
    "Number of enabled amendments",
    registry=registry,
)
AMENDMENTS_SUPPORTED = Gauge(
    "postfiatd_amendments_supported_total",
    "Number of supported amendments",
    registry=registry,
)
AMENDMENTS_VETOED = Gauge(
    "postfiatd_amendments_vetoed_total",
    "Number of vetoed amendments",
    registry=registry,
)
AMENDMENT_STATUS = Gauge(
    "postfiatd_amendment_status",
    "Individual amendment status (1=enabled, 0=disabled, -1=vetoed)",
    ["name", "hash_short"],
    registry=registry,
)

# -- Validators --
TRUSTED_VALIDATORS = Gauge(
    "postfiatd_trusted_validators_total",
    "Total trusted validators in UNL",
    registry=registry,
)
PUBLISHER_LISTS = Gauge(
    "postfiatd_publisher_lists_total",
    "Number of validator list publishers",
    registry=registry,
)

# -- File integrity --
FILE_EXISTS = Gauge(
    "postfiatd_config_file_exists",
    "Whether a critical config file exists (1=yes, 0=no)",
    ["filename"],
    registry=registry,
)
FILE_SIZE = Gauge(
    "postfiatd_config_file_size_bytes",
    "Size of a critical config file",
    ["filename"],
    registry=registry,
)
FILE_MODIFIED = Gauge(
    "postfiatd_config_file_modified_timestamp",
    "Last modified timestamp of a critical config file",
    ["filename"],
    registry=registry,
)
FILE_HASH = Info(
    "postfiatd_config_file_hash",
    "SHA-256 hash (short) of critical config files",
    registry=registry,
)

# ═══════════════════════════════════════════════════════════════════
# RPC helpers
# ═══════════════════════════════════════════════════════════════════

def rpc(url: str, method: str, params=None, timeout: int = 5):
    """JSON-RPC call to postfiatd."""
    try:
        resp = requests.post(
            url,
            json={"method": method, "params": params or [{}]},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("result")
    except Exception as e:
        SCRAPE_ERRORS.labels(method=method).inc()
        log.warning("RPC %s failed: %s", method, e)
        return None


# ═══════════════════════════════════════════════════════════════════
# Collectors
# ═══════════════════════════════════════════════════════════════════

def collect_server_info(url: str):
    result = rpc(url, "server_info")
    if not result or "info" not in result:
        EXPORTER_UP.set(0)
        return
    EXPORTER_UP.set(1)
    info = result["info"]

    # Identity
    NODE_INFO.info({
        "build_version": str(info.get("build_version", "")),
        "pubkey_node": str(info.get("pubkey_node", "")),
        "pubkey_validator": str(info.get("pubkey_validator", info.get("validation_public_key", ""))),
        "network_id": str(info.get("network_id", "")),
        "hostid": str(info.get("hostid", "")),
    })

    # Server state
    state = info.get("server_state", "disconnected")
    SERVER_STATE.state(state)
    dur_us = info.get("server_state_duration_us", "0")
    SERVER_STATE_DURATION.set(int(dur_us) / 1e6)
    UPTIME.set(info.get("uptime", 0))

    # Peers
    PEERS_TOTAL.set(info.get("peers", 0))
    PEER_DISCONNECTS.set(int(info.get("peer_disconnects", 0)))
    PEER_DISCONNECTS_RESOURCES.set(int(info.get("peer_disconnects_resources", 0)))

    # Consensus
    LOAD_FACTOR.set(info.get("load_factor", 1))
    IO_LATENCY.set(info.get("io_latency_ms", 0))
    VALIDATION_QUORUM.set(info.get("validation_quorum", 0))
    JQ_TRANS_OVERFLOW.set(int(info.get("jq_trans_overflow", 0)))

    lc = info.get("last_close", {})
    LAST_CLOSE_CONVERGE.set(lc.get("converge_time_s", 0))
    LAST_CLOSE_PROPOSERS.set(lc.get("proposers", 0))

    # Validated ledger
    vl = info.get("validated_ledger", info.get("closed_ledger", {}))
    if vl:
        LEDGER_SEQ.set(vl.get("seq", 0))
        LEDGER_AGE.set(vl.get("age", 0))
        LEDGER_BASE_FEE.set(float(vl.get("base_fee_xrp", 0)))
        LEDGER_RESERVE_BASE.set(float(vl.get("reserve_base_xrp", 0)))
        LEDGER_RESERVE_INC.set(float(vl.get("reserve_inc_xrp", 0)))
        LEDGER_HASH.info({"hash": str(vl.get("hash", ""))})

    # State accounting
    sa = info.get("state_accounting", {})
    for s, vals in sa.items():
        if isinstance(vals, dict):
            STATE_DURATION.labels(state=s).set(int(vals.get("duration_us", 0)) / 1e6)
            STATE_TRANSITIONS.labels(state=s).set(int(vals.get("transitions", 0)))


def collect_peers(url: str):
    result = rpc(url, "peers")
    if not result or "peers" not in result:
        return
    peers = result["peers"]
    inbound = sum(1 for p in peers if p.get("type") == "in")
    outbound = sum(1 for p in peers if p.get("type") == "out")
    PEERS_BY_TYPE.labels(type="inbound").set(inbound)
    PEERS_BY_TYPE.labels(type="outbound").set(outbound)


def collect_fee(url: str):
    result = rpc(url, "fee")
    if not result:
        return
    FEE_CURRENT_LEDGER_SIZE.set(int(result.get("current_ledger_size", 0)))
    FEE_CURRENT_QUEUE_SIZE.set(int(result.get("current_queue_size", 0)))
    drops = result.get("drops", {})
    FEE_DROPS_MINIMUM.set(int(drops.get("minimum_fee", 0)))
    FEE_DROPS_MEDIAN.set(int(drops.get("median_fee", 0)))
    FEE_DROPS_OPEN_LEDGER.set(int(drops.get("open_ledger_fee", 0)))


def collect_feature(url: str):
    result = rpc(url, "feature")
    if not result:
        return
    enabled = 0
    supported = 0
    vetoed = 0
    for key, val in result.items():
        if not isinstance(val, dict) or "name" not in val:
            continue
        name = val.get("name", key[:12])
        is_enabled = val.get("enabled", False)
        is_supported = val.get("supported", False)
        is_vetoed = val.get("vetoed", False)
        if is_enabled:
            enabled += 1
            AMENDMENT_STATUS.labels(name=name, hash_short=key[:12]).set(1)
        elif is_vetoed:
            vetoed += 1
            AMENDMENT_STATUS.labels(name=name, hash_short=key[:12]).set(-1)
        else:
            if is_supported:
                supported += 1
            AMENDMENT_STATUS.labels(name=name, hash_short=key[:12]).set(0)

    AMENDMENTS_ENABLED.set(enabled)
    AMENDMENTS_SUPPORTED.set(supported)
    AMENDMENTS_VETOED.set(vetoed)


def collect_validators(url: str):
    result = rpc(url, "validators")
    if not result:
        return
    pls = result.get("publisher_lists", [])
    PUBLISHER_LISTS.set(len(pls))
    total_trusted = sum(len(pl.get("list", [])) for pl in pls if pl.get("available"))
    TRUSTED_VALIDATORS.set(total_trusted)


def collect_file_integrity(paths: list[str]):
    hash_info = {}
    for path_str in paths:
        p = Path(path_str)
        fname = p.name
        if p.exists():
            FILE_EXISTS.labels(filename=fname).set(1)
            stat = p.stat()
            FILE_SIZE.labels(filename=fname).set(stat.st_size)
            FILE_MODIFIED.labels(filename=fname).set(stat.st_mtime)
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            hash_info[fname] = h.hexdigest()[:16]
        else:
            FILE_EXISTS.labels(filename=fname).set(0)
            FILE_SIZE.labels(filename=fname).set(0)
            FILE_MODIFIED.labels(filename=fname).set(0)
    if hash_info:
        FILE_HASH.info(hash_info)


# ═══════════════════════════════════════════════════════════════════
# Main scrape loop
# ═══════════════════════════════════════════════════════════════════

def scrape_all(rpc_url: str, admin_rpc_url: str, config_paths: list[str]):
    with SCRAPE_DURATION.time():
        collect_server_info(rpc_url)
        collect_peers(admin_rpc_url)
        collect_fee(rpc_url)
        collect_feature(admin_rpc_url)
        collect_validators(admin_rpc_url)
        collect_file_integrity(config_paths)


def main():
    parser = argparse.ArgumentParser(description="Prometheus exporter for postfiatd")
    parser.add_argument("--rpc-url", default="http://127.0.0.1:5005")
    parser.add_argument("--admin-rpc-url", default=None)
    parser.add_argument("--port", type=int, default=9750)
    parser.add_argument("--interval", type=int, default=15, help="Scrape interval in seconds")
    parser.add_argument("--config-paths", nargs="+", default=[
        "/opt/postfiatd/postfiatd.cfg",
        "/opt/postfiatd/validator-keys.json",
        "/opt/postfiatd/validator-token.single",
    ])
    args = parser.parse_args()
    admin_url = args.admin_rpc_url or args.rpc_url

    log.info("Starting postfiatd_exporter on :%d", args.port)
    log.info("  RPC: %s | Admin: %s", args.rpc_url, admin_url)
    log.info("  Interval: %ds | Files: %s", args.interval, args.config_paths)

    # Start Prometheus HTTP server
    from prometheus_client import make_wsgi_app
    from wsgiref.simple_server import make_server
    import threading

    app = make_wsgi_app(registry)
    httpd = make_server("0.0.0.0", args.port, app)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    log.info("Metrics endpoint: http://0.0.0.0:%d/metrics", args.port)

    while True:
        scrape_all(args.rpc_url, admin_url, args.config_paths)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
