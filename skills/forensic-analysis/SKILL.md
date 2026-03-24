---
id: forensic-analysis
name: Digital Forensics
description: Digital forensics methodology including disk imaging, file recovery, and timeline analysis
category: forensics
version: "1.0.0"
tags: [forensics, disk, imaging, recovery, timeline, evidence]
tools: [dd, dcfldd, foremost, scalpel, volatility, autopsy, sleuthkit, exiftool, strings]
requires: [dd, strings]
---

# Digital Forensics Skill

You are performing a digital forensic investigation. Follow proper evidence handling
procedures to maintain chain of custody and admissibility.


## Phase 1: Evidence Preservation

1. **Document the Scene** — Record initial state before any interaction
   - Photograph/screenshot the system state
   - Record date, time, timezone, and running processes
   - Note network connections and mounted devices

2. **Disk Imaging** — Create forensic bit-for-bit copies
   - `dcfldd if=/dev/sda of=/evidence/disk.dd hash=sha256 hashlog=disk.hash`
   - Alternative: `dd if=/dev/sda of=/evidence/disk.dd bs=4096 conv=noerror,sync`
   - Always work on the copy, never the original
   - Verify integrity: `sha256sum /evidence/disk.dd`

3. **Memory Capture** — Dump volatile memory before shutdown
   - Linux: `dd if=/dev/mem of=/evidence/memory.dd`
   - Use LiME kernel module for complete memory dump
   - Windows: Use WinPMEM or FTK Imager for memory acquisition

## Phase 2: File System Analysis

4. **Mount Image Read-Only** — Examine without modification
   - `mount -o ro,loop,noexec /evidence/disk.dd /mnt/evidence`
   - Use `losetup` for partition offsets within full disk images
   - `mmls disk.dd` to identify partition layout

5. **File Recovery** — Recover deleted files
   - `foremost -i disk.dd -o /evidence/recovered/`
   - `scalpel -c /etc/scalpel/scalpel.conf -o /evidence/carved/ disk.dd`
   - `photorec disk.dd` for interactive file recovery
   - Check unallocated space and slack space

6. **File System Timeline** — Build activity timeline
   - `fls -r -m "/" disk.dd > timeline.body`
   - `mactime -b timeline.body -d > timeline.csv`
   - Analyze MAC times (Modified, Accessed, Changed, Born)
   - Look for timestamp anomalies indicating tampering

## Phase 3: Artifact Analysis

7. **Log Examination** — Analyze system and application logs
   - `/var/log/auth.log` — Authentication events
   - `/var/log/syslog` — System events
   - `/var/log/apache2/access.log` — Web server access
   - Windows Event Logs (Security, System, Application)
   - Parse with: `cat auth.log | grep -i "failed\|accepted\|session"`

8. **User Activity** — Trace user actions
   - Browser history: `~/.mozilla/firefox/*.default/places.sqlite`
   - Bash history: `~/.bash_history`
   - Recent files, downloads, USB device history
   - Windows: Prefetch, Shellbags, Jump Lists, MRU lists

9. **Metadata Extraction** — Pull file metadata
   - `exiftool <file>` — EXIF data from images, documents
   - `strings -a <file>` — Extract readable strings from binaries
   - Check for hidden data streams (NTFS ADS)

## Phase 4: Memory Forensics

10. **Memory Analysis with Volatility**
    - `volatility -f memory.dd imageinfo` — Identify OS profile
    - `volatility -f memory.dd --profile=<profile> pslist` — Process list
    - `volatility -f memory.dd --profile=<profile> netscan` — Network connections
    - `volatility -f memory.dd --profile=<profile> filescan` — Open files
    - `volatility -f memory.dd --profile=<profile> hashdump` — Extract password hashes
    - `volatility -f memory.dd --profile=<profile> malfind` — Find injected code

## Phase 5: Reporting

Present findings as a forensic report:
- **Case summary** — Incident description, scope, and objectives
- **Evidence inventory** — All evidence items with hash values
- **Timeline of events** — Chronological reconstruction of activity
- **Key findings** — Artifacts supporting or refuting the hypothesis
- **Indicators of compromise** — IPs, domains, file hashes, tools used
- **Conclusions** — Summary of what happened based on evidence
- **Chain of custody log** — Document all evidence handling
