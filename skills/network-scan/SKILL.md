---
id: network-scan
name: Network Scanning
description: Comprehensive network discovery and mapping
category: pentesting
version: "1.0.0"
tags: [network, scanning, discovery, mapping]
tools: [nmap, masscan]
requires: [nmap]
---

# Network Scanning Skill

Perform comprehensive network scanning:

1. **Host Discovery** — Ping sweep to identify live hosts (nmap -sn)
2. **Port Scanning** — SYN scan on discovered hosts
3. **Service Detection** — Version detection on open ports (-sV)
4. **OS Fingerprinting** — Identify operating systems (-O)
5. **NSE Scripts** — Run relevant NSE scripts for detailed info
6. **Network Mapping** — Build a map of the network topology

Present results as:
- List of live hosts with open ports
- Service matrix (host × port × service)
- Network topology summary
- Interesting findings and recommendations
