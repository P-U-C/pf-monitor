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
  │ Alertmanager (:9093) │              │                          │
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

## Requirements

- Docker + Docker Compose v2
- Network access from monitor host to validator host on ports 9750 and 9100
- A Discord webhook URL for alerts (optional but recommended)
