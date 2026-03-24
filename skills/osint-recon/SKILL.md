---
id: osint-recon
name: OSINT Reconnaissance
description: Comprehensive passive and active OSINT reconnaissance workflow
category: osint
version: "1.0.0"
tags: [osint, recon, passive, active, intelligence]
tools: [whois, theharvester, subdomain_enum, dnsrecon, sherlock, exiftool, shodan]
requires: [whois, nmap]
---

# OSINT Reconnaissance Skill

You are performing a comprehensive OSINT (Open Source Intelligence) reconnaissance
on a given target. Follow this structured methodology:

## Phase 1: Target Identification
- Determine target type: domain, IP, email, username, phone, organization
- Define scope and objectives

## Phase 2: Passive Reconnaissance (No direct contact with target)
1. **Domain/IP targets:**
   - WHOIS lookup for registration data
   - DNS record enumeration (A, AAAA, MX, NS, TXT, SOA, SRV)
   - Certificate transparency log search
   - Subdomain enumeration (passive sources)
   - Technology fingerprinting (WhatWeb, BuiltWith)
   - Historical data (Wayback Machine)
   - Google dorking for exposed files/data

2. **Email targets:**
   - Breach database checks (h8mail)
   - Account enumeration (Holehe)
   - Associated domains and organizations
   - Social media profile linking

3. **Username targets:**
   - Cross-platform search (Sherlock)
   - Social media profiling
   - Post/comment analysis

4. **Organization targets:**
   - Employee enumeration (theHarvester + LinkedIn)
   - Email pattern discovery
   - Infrastructure mapping
   - Document metadata extraction

## Phase 3: Active Reconnaissance (Requires authorization)
- Port scanning (Nmap)
- Service version detection
- Banner grabbing
- Web application crawling

## Phase 4: Analysis & Correlation
- Cross-reference findings from multiple sources
- Build relationship maps
- Identify attack surface
- Prioritize findings by risk

## Phase 5: Reporting
Present findings in a structured format:
- Executive summary
- Detailed findings with evidence
- Risk assessment
- Recommendations

Always use the most appropriate tools for each step. Document every finding.
