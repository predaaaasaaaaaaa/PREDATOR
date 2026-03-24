---
id: domain-enum
name: Domain Enumeration
description: Complete domain and subdomain enumeration with DNS analysis
category: osint
version: "1.0.0"
tags: [domain, subdomain, dns, enumeration]
tools: [whois, subdomain_enum, dnsrecon, theharvester, nmap]
requires: [whois, dig]
---

# Domain Enumeration Skill

Perform comprehensive domain enumeration:

1. **WHOIS** — Registrant info, dates, nameservers
2. **DNS Records** — A, AAAA, MX, NS, TXT, SOA, SRV, CNAME
3. **Zone Transfer** — Attempt AXFR on nameservers
4. **Subdomain Enumeration** — Use Sublist3r, Amass, or Subfinder
5. **theHarvester** — Gather emails, hosts from public sources
6. **Reverse DNS** — Map IPs back to hostnames
7. **Port Scan** — Identify services on discovered hosts

Present all subdomains with resolved IPs in a clean table.
Highlight any interesting findings (dev subdomains, staging, admin panels).
