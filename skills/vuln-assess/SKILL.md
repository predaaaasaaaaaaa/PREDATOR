---
id: vuln-assess
name: Vulnerability Assessment
description: Comprehensive vulnerability scanning and analysis
category: pentesting
version: "1.0.0"
tags: [vulnerability, scanning, assessment, cve]
tools: [nmap, nikto, nuclei, searchsploit]
requires: [nmap]
---

# Vulnerability Assessment Skill

Perform a structured vulnerability assessment:

1. **Service Discovery** — Port scan with version detection (nmap -sV)
2. **Web Scanning** — Run Nikto against web servers
3. **Template Scanning** — Run Nuclei with vulnerability templates
4. **CVE Lookup** — Search for CVEs matching discovered service versions
5. **Exploit Search** — Check Exploit-DB via searchsploit
6. **Risk Rating** — Classify findings as Critical/High/Medium/Low
7. **Reporting** — Present structured findings with remediation steps

Always verify findings before reporting. Minimize false positives.
