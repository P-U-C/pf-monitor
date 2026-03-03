# Post Fiat Validator Monitor

Prometheus + Grafana + Alertmanager monitoring for Post Fiat Network validators.
Custom exporter for postfiatd JSON-RPC, 25+ alert rules, pre-built Grafana dashboard, Discord alerting.

## Quick Start

```bash
git clone <repo> && cd pf-monitor
chmod +x setup.sh
```

### Option A: All on one machine (simple)

Everything runs on the validator host. Quick to set up, but if the machine goes down you won't get an alert.

```bash
./setup.sh local
```

### Option B: Split across two machines (recommended)

Exporters run on the validator. Prometheus/Grafana/Alertmanager run on a separate machine (Proxmox LXC, Oracle VPS, etc). If the validator dies, the monitor stays up and alerts fire.

**On the validator host:**
```bash
./setup.sh split-validator
```

**On the monitor host:**
```bash
./setup.sh split-monitor
```

That's it. The script asks for your RPC URL, Discord webhook, and passwords interactively.

## What's Monitored

**Consensus** — node reachable, server state full, ledger advancing, ledger age, peer count, inbound peers, I/O latency, convergence time, load factor, job queue overflow

**Infrastructure** — CPU, RAM, disk, swap, network errors, disk fill prediction, container status, OOM events, restart loops, CPU throttling

**Post Fiat specific** — validator key files exist/unchanged, token presence, quorum, fee spikes, transaction queue, amendment votes

## Architecture

```
  Monitor host                          Validator host
  ┌──────────────────────┐              ┌──────────────────────────┐
  │ Prometheus (:9090)   │──── scrapes ──→ postfiatd_exporter (:9750)
  │ Grafana    (:3000)   │              │ node_exporter      (:9100)
  │ Alertmanager (:9093) │              │ cAdvisor           (:8080)
  │        │             │              │                          │
  │        ▼             │              │ postfiatd (your node)    │
  │  Discord / Slack     │              └──────────────────────────┘
  └──────────────────────┘
```

In local mode, everything runs in the left box on the validator host.

## Grafana Dashboard

Pre-loaded at `http://<host>:3000` with panels for:
- Operator status (up/down, server state, peers, ledger age, I/O latency, uptime, quorum)
- Ledger tracking and consensus convergence
- Peer breakdown (inbound/outbound)
- Host CPU, RAM, disk, network, load
- Container CPU, memory, network
- Governance (amendments, fee levels, tx queue)
- Config integrity (file existence, size tracking)

## Alert Routing

| Severity | Destination | Timing |
|----------|-------------|--------|
| Critical | Discord + PagerDuty | Immediate, repeat every 30m |
| Warning | Discord | 5m group wait, repeat every 4h |
| Info | Discord | 15m group wait, repeat every 24h |

Critical alerts suppress matching warnings automatically.

## Files

```
pf-monitor/
├── setup.sh                         ← Run this
├── docker-compose.local.yml         ← All-in-one mode
├── docker-compose.exporters.yml     ← Split: validator host
├── docker-compose.monitor.yml       ← Split: monitor host
├── exporters/
│   ├── postfiatd_exporter.py        ← Custom Prometheus exporter
│   ├── Dockerfile
│   └── statsd_mapping.yml           ← Optional StatsD bridge
├── prometheus/
│   ├── prometheus.template.yml      ← Template (setup.sh generates prometheus.yml)
│   └── rules/
│       └── postfiat_alerts.yml      ← 25+ alert rules
├── alertmanager/
│   └── alertmanager.yml             ← Discord/Slack/PagerDuty routing
└── grafana/
    ├── provisioning/                ← Auto-configures datasource + dashboard loading
    └── dashboards/
        └── pf-overview.json         ← Pre-built dashboard
```

## Docker Networking: Admin RPC Access

The postfiatd exporter calls several admin-only RPC methods (`peers`, `feature`, `validators`).
When the exporter runs in Docker, it reaches postfiatd via `host.docker.internal`, which resolves
to the Docker bridge IP (typically `172.17.0.1` or `172.18.0.1`) — **not** `127.0.0.1`.

If postfiatd's `admin` config only allows `127.0.0.1`, those calls return `Forbidden`.

**Fix** — add the Docker bridge subnet to `postfiatd.cfg`:

```ini
[port_rpc_admin_local]
...
admin = 127.0.0.1,172.17.0.0/16,172.18.0.0/16
```

Restart postfiatd after editing. The exporter will then have full access to admin methods.

**Graceful degradation** — if admin methods are blocked, the exporter does not crash.
It logs a warning, increments `postfiatd_scrape_errors_total`, and skips those metrics
(`postfiatd_peers_by_type`, `postfiatd_amendments_*`, `postfiatd_trusted_validators_total`).
Core health metrics (`postfiatd_up`, server state, ledger, fee) are public and always available.

## Requirements

- Docker + Docker Compose v2
- Network access from monitor host to validator host on ports 9750, 9100, 8080
- A Discord webhook URL for alerts (optional but recommended)
