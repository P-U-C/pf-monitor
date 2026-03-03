# Post Fiat Validator Monitor

Production-grade monitoring for Post Fiat Network validator operators.
Uses the standard Prometheus + Grafana + Alertmanager stack that most validators run,
extended with a custom exporter for postfiatd's XRPL-derived JSON-RPC API.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Grafana (:3000)                            │
│  Pre-provisioned dashboards for PF validator operations         │
│  ┌──────────────┬──────────────┬──────────────┬───────────────┐ │
│  │ Operator     │ Consensus &  │ Infra (CPU   │ Governance &  │ │
│  │ Status Panel │ Ledger       │ RAM Disk Net) │ Integrity     │ │
│  └──────────────┴──────────────┴──────────────┴───────────────┘ │
└───────────────────────────┬─────────────────────────────────────┘
                            │ PromQL
┌───────────────────────────▼─────────────────────────────────────┐
│                    Prometheus (:9090)                            │
│  Scrapes every 15s · 30d retention · Alert rule evaluation      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Alert Rules: 25+ rules across 3 groups                    │   │
│  │  • postfiatd_consensus (node down, ledger stale, peers)   │   │
│  │  • postfiatd_infra (CPU, RAM, disk, container OOM)        │   │
│  │  • postfiatd_integrity (config drift, missing keys, fees) │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────┬──────────┬──────────┬──────────┬────────────────────────┘
        │          │          │          │
   ┌────▼───┐ ┌───▼────┐ ┌──▼───┐ ┌───▼──────────────────┐
   │postfiatd│ │  node  │ │cAdvsr│ │  Alertmanager (:9093) │
   │exporter │ │exporter│ │      │ │  Discord / Slack /    │
   │ (:9750) │ │(:9100) │ │(:8080│ │  PagerDuty routing    │
   └────┬────┘ └────────┘ └──────┘ └──────────────────────┘
        │
   ┌────▼────────────────┐
   │   postfiatd node    │
   │  JSON-RPC (:5005)   │
   │                     │
   │ Optional: [insight] │──→ statsd_exporter (:9125/udp → :9102)
   │  server=statsd      │
   └─────────────────────┘
```

## Components

| Service | Port | Purpose |
|---------|------|---------|
| **postfiatd_exporter** | 9750 | Custom Prometheus exporter: scrapes postfiatd JSON-RPC, exposes XRPL/PF metrics + file integrity |
| **node_exporter** | 9100 | Standard host metrics: CPU, RAM, disk, network, load |
| **cAdvisor** | 8080 | Docker container metrics: per-container CPU, memory, network, restarts, OOM |
| **Prometheus** | 9090 | Time-series DB, scraping, alert rule evaluation |
| **Grafana** | 3000 | Dashboards (pre-provisioned) |
| **Alertmanager** | 9093 | Alert routing to Discord, Slack, PagerDuty |
| **statsd_exporter** | 9125/9102 | *(Optional)* Bridge for native rippled `[insight]` StatsD metrics |

## Quick Start

```bash
# 1. Clone and configure
git clone <this-repo> pf-monitor
cd pf-monitor
cp .env.example .env
nano .env  # Set your postfiatd RPC URL and Discord webhook

# 2. Configure Discord alerts
nano alertmanager/alertmanager.yml
# Replace YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN with your Discord webhook

# 3. Launch the stack
docker compose up -d

# 4. Verify
curl http://localhost:9750/metrics     # postfiatd exporter
curl http://localhost:9100/metrics     # node exporter
curl http://localhost:9090/-/healthy   # prometheus
open http://localhost:3000             # grafana (admin/postfiat)
```

## Custom Exporter Metrics

The `postfiatd_exporter` scrapes these JSON-RPC methods every 15s:

| RPC Method | Metrics Exposed |
|------------|----------------|
| `server_info` | server state, uptime, peers, ledger seq/age/hash, load factor, I/O latency, validation quorum, state accounting, base fee, reserves |
| `peers` (admin) | peer count by type (inbound/outbound) |
| `fee` | current/queue size, fee drops (min/median/open_ledger) |
| `feature` (admin) | amendment counts (enabled/supported/vetoed), per-amendment status |
| `validators` (admin) | trusted validator count, publisher list count |
| *filesystem* | config file existence, size, mtime, SHA-256 hash |

Full metric list:

```
# Exporter health
postfiatd_up
postfiatd_scrape_duration_seconds
postfiatd_scrape_errors_total

# Server state
postfiatd_server_state
postfiatd_server_state_duration_seconds
postfiatd_uptime_seconds

# Ledger
postfiatd_validated_ledger_seq
postfiatd_validated_ledger_age_seconds
postfiatd_base_fee_xrp
postfiatd_reserve_base_xrp
postfiatd_reserve_inc_xrp

# Peers
postfiatd_peers_total
postfiatd_peers_by_type{type="inbound|outbound"}
postfiatd_peer_disconnects_total
postfiatd_peer_disconnects_resources_total

# Consensus
postfiatd_load_factor
postfiatd_io_latency_ms
postfiatd_validation_quorum
postfiatd_last_close_converge_seconds
postfiatd_last_close_proposers
postfiatd_jq_trans_overflow

# State accounting
postfiatd_state_accounting_duration_seconds{state="..."}
postfiatd_state_accounting_transitions_total{state="..."}

# Fees
postfiatd_fee_current_ledger_size
postfiatd_fee_current_queue_size
postfiatd_fee_drops_minimum
postfiatd_fee_drops_median
postfiatd_fee_drops_open_ledger

# Governance
postfiatd_amendments_enabled_total
postfiatd_amendments_supported_total
postfiatd_amendments_vetoed_total
postfiatd_amendment_status{name="...", hash_short="..."}
postfiatd_trusted_validators_total
postfiatd_publisher_lists_total

# File integrity
postfiatd_config_file_exists{filename="..."}
postfiatd_config_file_size_bytes{filename="..."}
postfiatd_config_file_modified_timestamp{filename="..."}
```

## Alert Rules (25+ rules)

### Consensus & Network (`postfiatd_consensus`)
| Alert | Condition | Severity |
|-------|-----------|----------|
| PostFiatNodeDown | RPC unreachable >1m | critical |
| PostFiatServerStateNotFull | State != full >2m | critical |
| PostFiatLedgerStale | Age >10s for 1m | warning |
| PostFiatLedgerVeryStaleCritical | Age >30s for 1m | critical |
| PostFiatLedgerNotAdvancing | Seq unchanged 5m | critical |
| PostFiatPeersLow | <5 peers for 2m | warning |
| PostFiatPeersCritical | <2 peers for 1m | critical |
| PostFiatNoInboundPeers | 0 inbound for 5m | warning |
| PostFiatLoadFactorHigh | >1000 for 5m | warning |
| PostFiatIOLatencyHigh | >50ms for 2m | critical |
| PostFiatIOLatencyWarning | >10ms for 5m | warning |
| PostFiatSlowConvergence | >5s for 5m | warning |
| PostFiatJQOverflow | >0 for 1m | warning |

### Infrastructure (`postfiatd_infra`)
| Alert | Condition | Severity |
|-------|-----------|----------|
| HostCPUHigh | >80% for 5m | warning |
| HostCPUCritical | >95% for 2m | critical |
| HostMemoryHigh | >85% for 5m | warning |
| HostMemoryCritical | >95% for 2m | critical |
| HostSwapUsed | >10% for 5m | warning |
| HostDiskHigh | >75% for 5m | warning |
| HostDiskCritical | >90% for 2m | critical |
| HostDiskWillFill24h | Predicted full in 24h | warning |
| HostNetworkErrors | Any errors for 5m | warning |
| PostFiatContainerDown | Container missing 1m | critical |
| PostFiatContainerOOM | Any OOM event | critical |
| PostFiatContainerRestarting | Restart loop | warning |
| PostFiatContainerCPUThrottled | >25% throttled | warning |

### Post Fiat Integrity (`postfiatd_integrity`)
| Alert | Condition | Severity |
|-------|-----------|----------|
| PostFiatConfigFileMissing | Any config file gone | critical |
| PostFiatValidatorTokenMissing | Token file gone | critical |
| PostFiatValidatorKeysMissing | Keys file gone | critical |
| PostFiatConfigFileChanged | Config modified in 1h | warning |
| PostFiatQuorumLow | Quorum <3 for 5m | warning |
| PostFiatFeeSpike | Open ledger fee >50k drops | warning |
| PostFiatTxQueueBuilding | >100 txns queued | warning |
| PostFiatAmendmentVetoed | Any vetoed amendments | info |

## Optional: Native StatsD Integration

rippled (and postfiatd, being a fork) supports native StatsD metric export.
This gives you internal engine metrics that the JSON-RPC API doesn't expose.

Add to your `postfiatd.cfg`:
```
[insight]
server=statsd
address=<monitor-host>:9125
prefix=postfiatd
```

Then uncomment the `statsd-exporter` service in `docker-compose.yml` and the
corresponding Prometheus scrape target.

## Grafana Dashboard

The pre-provisioned dashboard includes:

- **Operator Status Row** — UP/DOWN, server state, peers, ledger age, I/O latency, uptime, quorum (color-coded stat panels)
- **Consensus & Ledger** — Ledger sequence over time, ledger age with threshold lines, peer breakdown, convergence time, load factor
- **Infrastructure** — CPU/RAM/Disk with threshold lines, network I/O, disk I/O, system load vs core count
- **Container Metrics** — postfiatd container CPU, memory, network I/O
- **Governance & Economics** — Amendment counts, fee levels over time, transaction queue depth
- **Config Integrity** — File existence status, file size tracking (detect truncation)

Dashboard auto-refreshes every 15s and defaults to 3h time range.

## Directory Structure

```
pf-monitor/
├── docker-compose.yml                    # Full stack definition
├── .env.example                          # Configuration template
│
├── exporters/
│   ├── postfiatd_exporter.py            # Custom Prometheus exporter
│   ├── Dockerfile                        # Exporter container build
│   └── statsd_mapping.yml               # Optional StatsD metric mapping
│
├── prometheus/
│   ├── prometheus.yml                    # Scrape config & targets
│   └── rules/
│       └── postfiat_alerts.yml          # 25+ alert rules
│
├── alertmanager/
│   └── alertmanager.yml                 # Discord/Slack/PD routing
│
└── grafana/
    ├── provisioning/
    │   ├── datasources/prometheus.yml   # Auto-configure Prometheus DS
    │   └── dashboards/default.yml       # Auto-load dashboard JSONs
    └── dashboards/
        └── pf-overview.json             # Pre-built validator dashboard
```

## Security Notes

- Bind Grafana/Prometheus to localhost or behind a reverse proxy with auth
- The exporter mounts your config directory **read-only**
- cAdvisor runs privileged for Docker socket access — standard for container monitoring
- For remote access, put Caddy/nginx in front with TLS + basic auth
- The exporter never modifies any postfiatd files

## Extending

**Add Loki for log aggregation:**
```yaml
# Add to docker-compose.yml
loki:
  image: grafana/loki:2.9.0
  ports: ["3100:3100"]

promtail:
  image: grafana/promtail:2.9.0
  volumes:
    - /var/log:/var/log:ro
    - /var/lib/docker/containers:/var/lib/docker/containers:ro
```

**Add Blackbox Exporter for external probing:**
```yaml
blackbox:
  image: prom/blackbox-exporter:v0.25.0
  ports: ["9115:9115"]
```

Then add a Prometheus scrape job to probe your validator's peer port from outside.

## Useful PromQL Queries

```promql
# Is my validator healthy? (boolean)
postfiatd_up == 1
  and postfiatd_server_state{postfiatd_server_state="full"} == 1
  and postfiatd_peers_total >= 3

# Ledger advancement rate (ledgers/second)
rate(postfiatd_validated_ledger_seq[5m])

# Time since last state change
postfiatd_server_state_duration_seconds

# Peer churn rate
rate(postfiatd_peer_disconnects_total[1h])

# Disk fill prediction (hours until full)
(node_filesystem_avail_bytes{mountpoint="/"}) /
  (rate(node_filesystem_avail_bytes{mountpoint="/"}[6h]) * -1) / 3600

# Container memory growth rate
deriv(container_memory_usage_bytes{name="postfiatd"}[1h])
```
