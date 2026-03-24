---
id: log-analysis
name: Security Log Analysis
description: Security log analysis for auth logs, web server logs, and anomaly detection
category: forensics
version: "1.0.0"
tags: [logs, analysis, siem, anomaly, detection, auth, web]
tools: [grep, awk, sed, sort, uniq, jq, python3]
requires: [grep, awk]
---

# Security Log Analysis Skill

You are analyzing security logs to detect intrusions, anomalies, and suspicious
activity. Apply structured analysis techniques across multiple log sources.

> **AUTHORIZATION REQUIRED**: Only analyze logs from systems you are authorized
> to investigate. Handle log data according to your organization's data handling
> and privacy policies.

## Phase 1: Log Collection & Preparation

1. **Identify Available Log Sources**
   - Linux auth: `/var/log/auth.log`, `/var/log/secure`
   - Syslog: `/var/log/syslog`, `/var/log/messages`
   - Web: `/var/log/apache2/access.log`, `/var/log/nginx/access.log`
   - Application: `/var/log/<app>/`, journalctl output
   - Windows: Security/System/Application Event Logs
   - Network: Firewall logs, IDS/IPS alerts, NetFlow

2. **Normalize Timestamps** — Ensure consistent time format
   - Convert all logs to UTC for correlation
   - Identify timezone offsets in each source
   - Note any time synchronization issues (NTP drift)

## Phase 2: Authentication Log Analysis

3. **Failed Login Detection** — Identify brute-force attempts
   - `grep "Failed password" /var/log/auth.log | awk '{print $11}' | sort | uniq -c | sort -rn`
   - Look for: high failure counts per IP, password spraying patterns
   - Threshold: >10 failures from single IP in 5 minutes = suspicious

4. **Successful Login Anomalies** — Spot unauthorized access
   - `grep "Accepted" /var/log/auth.log | awk '{print $1,$2,$3,$9,$11}'`
   - Flag: logins at unusual hours, from unusual IPs/geolocations
   - Check for logins to service/disabled accounts
   - Correlate successful logins immediately following failed attempts

5. **Privilege Escalation Indicators**
   - `grep "sudo" /var/log/auth.log` — Sudo usage
   - `grep "su:" /var/log/auth.log` — User switching
   - `grep "session opened for user root" /var/log/auth.log`
   - Look for unauthorized privilege changes

## Phase 3: Web Server Log Analysis

6. **Request Pattern Analysis**
   - `awk '{print $1}' access.log | sort | uniq -c | sort -rn | head 20` — Top IPs
   - `awk '{print $7}' access.log | sort | uniq -c | sort -rn | head 20` — Top URLs
   - `awk '{print $9}' access.log | sort | uniq -c | sort -rn` — Status code distribution

7. **Attack Signature Detection**
   - SQLi: `grep -iE "(union|select|insert|update|delete|drop|--|;|'|%27)" access.log`
   - XSS: `grep -iE "(script|alert|onerror|onload|eval|javascript)" access.log`
   - Path traversal: `grep -E "(\.\./|\.\.\\\\|%2e%2e)" access.log`
   - Scanner fingerprints: `grep -iE "(nikto|sqlmap|nmap|masscan|gobuster)" access.log`

8. **Anomalous Behavior**
   - Large response sizes (data exfiltration)
   - High request rates from single IP (DDoS/scanning)
   - Requests to non-existent pages (directory brute-force)
   - Unusual User-Agent strings

## Phase 4: System & Network Log Analysis

9. **Process & Service Anomalies**
   - Unexpected service starts/stops
   - New cron jobs or scheduled tasks
   - Unusual outbound connections
   - `journalctl -u <service> --since "1 hour ago"`

10. **Network Anomaly Detection**
    - Firewall deny logs — repeated blocked connection attempts
    - DNS query logs — domain generation algorithm (DGA) patterns
    - Unusual ports, protocols, or data volumes
    - Beaconing patterns (regular interval connections to same destination)

## Phase 5: Correlation & Reporting

Present analysis as:
- **Executive summary** — Key findings in non-technical terms
- **Timeline of events** — Chronological sequence of suspicious activity
- **Indicators of compromise (IOCs)** — IPs, domains, user agents, file hashes
- **Attack classification** — Brute-force, injection, exfiltration, lateral movement
- **Affected systems/accounts** — Scope of compromise
- **Severity rating** — Critical/High/Medium/Low per finding
- **Recommendations** — Immediate containment and long-term hardening steps
