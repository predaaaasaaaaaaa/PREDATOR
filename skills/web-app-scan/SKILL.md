---
id: web-app-scan
name: Web Application Scanning
description: Web application vulnerability scanning for SQLi, XSS, CSRF, and OWASP Top 10
category: pentesting
version: "1.0.0"
tags: [web, application, sqli, xss, csrf, owasp, scanning]
tools: [nikto, nuclei, sqlmap, nmap, curl, wfuzz, gobuster]
requires: [nikto, curl]
---

# Web Application Scanning Skill

You are performing a comprehensive web application vulnerability assessment against
an authorized target. Follow the OWASP Testing Guide methodology.


## Phase 1: Reconnaissance & Mapping

1. **Technology Fingerprinting** — Identify web server, framework, CMS, and language
   - `curl -sI <target>` to inspect response headers
   - `nmap -sV -p 80,443,8080,8443 <target>` for service versions
   - Inspect `X-Powered-By`, `Server`, `X-AspNet-Version` headers

2. **Directory & File Discovery** — Brute-force hidden paths
   - `gobuster dir -u <target> -w /usr/share/wordlists/dirb/common.txt`
   - `wfuzz -c -z file,/usr/share/wordlists/dirb/common.txt --hc 404 <target>/FUZZ`
   - Look for admin panels, backup files (.bak, .old, .swp), config files

3. **Crawling & Sitemap** — Map the application surface
   - Extract links, forms, parameters, and endpoints
   - Identify input vectors (GET/POST parameters, cookies, headers)

## Phase 2: Automated Scanning

4. **Nikto Scan** — General web server vulnerability check
   - `nikto -h <target> -output nikto_results.txt`
   - Review for misconfigurations, default files, known vulnerabilities

5. **Nuclei Templates** — Run targeted vulnerability templates
   - `nuclei -u <target> -t cves/ -t vulnerabilities/ -t misconfigurations/`
   - Focus on critical and high severity findings

## Phase 3: Injection Testing

6. **SQL Injection** — Test all input parameters
   - `sqlmap -u "<target>/page?id=1" --batch --level=3 --risk=2`
   - Test POST forms: `sqlmap -u <target>/login --data="user=a&pass=b" --batch`
   - Check for blind, time-based, error-based, and UNION injection

7. **Cross-Site Scripting (XSS)** — Reflected, stored, and DOM-based
   - Inject test payloads: `<script>alert(1)</script>`, `"><img src=x onerror=alert(1)>`
   - Test all reflected parameters and stored input fields
   - Check for CSP headers and XSS protection bypasses

8. **Cross-Site Request Forgery (CSRF)** — Check state-changing operations
   - Verify anti-CSRF tokens on all forms
   - Check SameSite cookie attributes
   - Test token predictability and reuse

## Phase 4: Authentication & Authorization

9. **Authentication Testing**
   - Default credentials check
   - Brute-force protection verification
   - Session management analysis (cookie flags, expiration, randomness)
   - Password reset flow vulnerabilities

10. **Authorization Testing**
    - IDOR (Insecure Direct Object Reference) testing
    - Horizontal and vertical privilege escalation
    - Access control bypass attempts

## Phase 5: Analysis & Reporting

Present findings organized by severity:
- **Critical**: RCE, SQLi with data extraction, authentication bypass
- **High**: Stored XSS, CSRF on sensitive actions, IDOR
- **Medium**: Reflected XSS, information disclosure, missing security headers
- **Low**: Cookie flags, verbose errors, minor misconfigurations

Include proof-of-concept payloads and remediation guidance for each finding.
