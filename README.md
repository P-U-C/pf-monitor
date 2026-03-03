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

## Verify It's Working

**Check all containers are running:**
```bash
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep pf-
```

**Check exporter is scraping postfiatd:**
```bash
curl -s http://localhost:9750/metrics | head -20
```

**Check Prometheus is scraping all targets:**
```bash
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys,json
targets=json.load(sys.stdin)['data']['activeTargets']
for t in targets:
    print(f\"{t['labels'].get('job','?'):25s} {t['health']:10s} {t['lastError'][:50] if t['lastError'] else 'OK'}\")"
```

**Check alerts:**
```bash
# Quick summary of what's firing
curl -s 'localhost:9090/api/v1/alerts' | python3 -c "
import sys, json
data = json.load(sys.stdin)
alerts = data.get('data', {}).get('alerts', [])
if not alerts:
    print('No alerts firing')
else:
    for a in alerts:
        print(f\"{a['labels'].get('severity','?'):8s} {a['labels'].get('alertname','')} — {a['annotations'].get('summary','')}\")
"

# Full alert detail
curl -s localhost:9093/api/v2/alerts | python3 -m json.tool
```

**Test Discord webhook manually:**
```bash
# Replace with your actual webhook URL from .env or alertmanager.yml
curl -H "Content-Type: application/json" \
  -d '{"content":"🧪 Test alert from PF Monitor"}' \
  "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

**Restart / stop / logs:**
```bash
# Restart everything
docker compose -f docker-compose.local.yml restart

# Restart one service
docker compose -f docker-compose.local.yml restart postfiatd-exporter

# View logs
docker compose -f docker-compose.local.yml logs -f --tail 50

# Full stop and start
docker compose -f docker-compose.local.yml down
docker compose -f docker-compose.local.yml up -d

# Rebuild exporter after code change
docker compose -f docker-compose.local.yml up -d --build postfiatd-exporter
```

## Requirements

- Docker + Docker Compose v2
- Network access from monitor host to validator host on ports 9750 and 9100
- A Discord webhook URL for alerts (optional but recommended)
