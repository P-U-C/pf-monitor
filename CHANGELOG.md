# Changelog

All notable changes to pf-monitor are documented here.

---

## [1.0.0] — 2026-03-03

### Added
- Initial release
- Custom Prometheus exporter for postfiatd JSON-RPC API (`postfiatd_exporter.py`)
  - Core metrics: server state, ledger, peers, consensus, fees, amendments
  - Admin metrics: peer breakdown, trusted validators (requires admin RPC access)
  - File integrity checks: validator key files, token, config
  - Container monitoring via Docker socket
  - Graceful degradation when admin RPC is blocked (Docker bridge issue)
- 25+ Prometheus alert rules with critical/warning/info severity
- Pre-built Grafana dashboard (pf-overview)
- Alertmanager with Discord/Slack/PagerDuty routing
- `setup.sh` — interactive setup for local and split deployment modes
- Three Docker Compose variants: local, split-validator, split-monitor
- Docker build includes `VERSION` label for traceability

---

## How to Release

```bash
./release.sh 1.1.0   # bumps VERSION, creates CHANGELOG entry, tags git
```
