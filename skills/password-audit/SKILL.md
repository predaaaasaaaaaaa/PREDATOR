---
id: password-audit
name: Password Audit
description: Password strength auditing, hash identification, and cracking methodology
category: pentesting
version: "1.0.0"
tags: [password, audit, hash, cracking, brute-force]
tools: [hashcat, john, hydra, hash-identifier, crunch]
requires: [john]
---

# Password Audit Skill

You are performing a password security audit on provided credentials, hashes,
or authentication endpoints. Follow a structured cracking and analysis methodology. Password audit, hash identification, cracking techniques, rule-based mutations, brute-force patterns, online service authentication, reporting findings...etc.


## Phase 1: Hash Identification & Analysis

1. **Hash Type Detection** — Identify the hash algorithm
   - Analyze hash length and format (MD5=32 hex, SHA1=40 hex, SHA256=64 hex)
   - `hash-identifier` or `hashid` for automated identification
   - Check for salting patterns (e.g., `$6$salt$hash` for SHA-512 crypt)
   - Common formats: NTLM, bcrypt ($2b$), MD5crypt ($1$), SHA-512crypt ($6$)

2. **Hash Extraction** — Extract hashes from various sources
   - `/etc/shadow` for Linux password hashes
   - SAM/SYSTEM files for Windows NTLM hashes
   - Database dumps, configuration files
   - `unshadow /etc/passwd /etc/shadow > combined.txt`

## Phase 2: Dictionary Attacks

3. **Wordlist Selection** — Choose appropriate wordlists
   - `rockyou.txt` — Standard first-pass wordlist
   - `SecLists/Passwords/` — Specialized password lists
   - Custom wordlists from OSINT (company name, employee names, dates)

4. **John the Ripper** — Dictionary attack
   - `john --wordlist=/usr/share/wordlists/rockyou.txt hashes.txt`
   - `john --show hashes.txt` to display cracked passwords
   - Format-specific: `john --format=raw-md5 --wordlist=rockyou.txt hashes.txt`

5. **Hashcat** — GPU-accelerated cracking
   - `hashcat -m 0 -a 0 hashes.txt /usr/share/wordlists/rockyou.txt` (MD5)
   - `hashcat -m 1000 -a 0 hashes.txt rockyou.txt` (NTLM)
   - Mode reference: 0=MD5, 100=SHA1, 1000=NTLM, 1800=SHA-512crypt, 3200=bcrypt

## Phase 3: Rule-Based & Hybrid Attacks

6. **Rule-Based Mutations** — Apply transformation rules
   - `john --wordlist=rockyou.txt --rules=best64 hashes.txt`
   - `hashcat -m 0 -a 0 hashes.txt rockyou.txt -r best64.rule`
   - Common rules: capitalize, l33t speak, append numbers/years, toggle case

7. **Mask/Brute-Force Attacks** — Pattern-based cracking
   - `hashcat -m 0 -a 3 hashes.txt ?u?l?l?l?l?d?d?d` (Ullllddd pattern)
   - `hashcat -m 0 -a 3 hashes.txt ?a?a?a?a?a?a` (6-char all charsets)
   - Mask charsets: ?l=lower, ?u=upper, ?d=digit, ?s=special, ?a=all

## Phase 4: Online Brute-Force (Service Authentication)

8. **Hydra** — Network service brute-force
   - `hydra -l admin -P rockyou.txt <target> ssh`
   - `hydra -l admin -P rockyou.txt <target> http-post-form "/login:user=^USER^&pass=^PASS^:Invalid"`
   - `hydra -L users.txt -P passwords.txt <target> ftp`
   - Always respect lockout policies; use slow rate with `-t 4`

## Phase 5: Analysis & Reporting

Present findings as:
- **Cracked vs uncracked** — Percentage and count
- **Weakness analysis** — Common patterns (dictionary words, short length, no complexity)
- **Policy violations** — Passwords not meeting minimum requirements
- **Top patterns** — Most common base words, suffixes, structures
- **Recommendations** — Minimum length, complexity, MFA enforcement, bcrypt migration
