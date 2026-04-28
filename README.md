# DeAder

DeAder is a small self-hosted web app for **“paste a link → download on your server → stream it on your phone”** (powered by `yt-dlp`).

It’s built for the common case: you’re on iOS Safari, you paste a link (like YouTube), and you want the resulting file to **play in-browser** without fiddly steps.

## What it does

- **Paste URL → server downloads** via `yt-dlp`
- **Auto-switches to a player page** that streams the downloaded file
- **iOS-friendly playback** (serves the file in a way Safari can stream)
- **LAN-friendly**: run on your PC and open from your phone on the same Wi‑Fi
- **Optional protection** with a server token
- **Optional network-compat knobs** (player client, PO token, TLS impersonation, source IP binding)
- **Optional automated network recovery** wrapper (VPN rotation + cache purge + retry)
- **Auto-cleanup**: removes old downloads after inactivity to free disk space

## Run (Windows / PowerShell)

```powershell
cd c:\Users\OwO\Desktop\Projects\DeAder
.\run.ps1
```

Then open `http://localhost:8787` on your PC.

## Run (Windows, double-click, no terminal window)

Double-click:

- `run-hidden.bat`

It will:

- Start DeAder
- Add a **system tray icon** that shows it’s running
- Open your browser to `http://localhost:8787`

Closing the tray icon via **Quit** stops DeAder.

### Single-instance behavior

By default, DeAder tray mode is **single-instance**:

- If you run it again, it will **not start a second copy**; it just opens the browser.

Optional switches:

- `run-hidden.bat --restart`: stop the existing instance and start a fresh one
- `run-hidden.bat --multi`: allow multiple instances (advanced)

## Use on iPhone (same Wi‑Fi / LAN)

1. Find your PC’s LAN IP:

```powershell
ipconfig
```

2. On iPhone Safari, open:
- `http://YOUR_PC_LAN_IP:8787`

If it doesn’t load, allow **Windows Firewall inbound TCP 8787**.

## Build a double-clickable EXE (Windows)

```powershell
cd c:\Users\OwO\Desktop\Projects\DeAder
.\build.ps1
```

Then double-click: `dist\DeAder.exe`

When run from the EXE, DeAder stores downloads in a `downloads/` folder next to the EXE.

## Security (highly recommended)

Set a token so your server isn’t an open “download anything” endpoint:

```powershell
$env:DEADER_TOKEN="some-long-random-string"
.\run.ps1
```

On iPhone, tap **Set token** once and paste that same token.

## Notes

- **ffmpeg**: if you install it on the server, `yt-dlp` can fetch higher quality formats. Without ffmpeg, DeAder prefers an iOS-friendly progressive MP4 when available.
- **Speed**: network-dependent. You can often improve throughput by increasing fragment concurrency:

```powershell
$env:DEADER_CONCURRENT_FRAGMENTS="16"
.\run.ps1
```

- **Optional**: install `aria2c` and enable it:

```powershell
$env:DEADER_USE_ARIA2C="true"
.\run.ps1
```

## Auto-cleanup (disk space)

To keep disk usage under control, DeAder tracks when a video was last played and **automatically deletes** it after:

- **At least 1 hour**, or
- **2× the video duration**,
- capped at **48 hours**

The countdown is based on **last access time** (watching/streaming).

## Network compatibility knobs (403/TLS issues)

These are read from environment variables and applied to the yt-dlp instance. They help in networks where requests fail with 403s or TLS fingerprint/cipher mismatches.

```powershell
# Try a different YouTube player client signature
$env:DEADER_PLAYER_CLIENT="web_safari"

# If you have a PO token (format is client+token, e.g. "web+…")
$env:DEADER_PO_TOKEN="web+PASTE_TOKEN_HERE"

# Use curl_cffi impersonation to match modern Chrome TLS fingerprint
$env:DEADER_IMPERSONATE="chrome-124:windows-10"

# Bind outgoing connections to a specific local IP (IPv4/IPv6)
$env:DEADER_SOURCE_ADDRESS="YOUR_LOCAL_IP"

.\run.ps1
```

## Automated network recovery (Mullvad rotation + retry)

If you’re seeing transient `403` or “confirm you’re not a bot” failures at volume, use the wrapper in `app/network_recovery.py` and wrap your yt-dlp call. It will:

- Rotate Mullvad (commands are configurable)
- Run `yt-dlp --rm-cache-dir`
- Delete `session_cookies.txt` if present
- Sleep 8 seconds
- Retry up to 3 rotations

## Open-source hygiene (important)

This repo is intended to be open-sourced. Some files commonly produced during testing can contain personal data (URLs, cookies, tokens).

- **Ignored by default**: `.env*`, `session_cookies*.txt`, `cookies*.txt`, build outputs (`dist/`, `build/`), logs, and `downloads/*.json` metadata.
- **Be careful with downloads**: downloaded media can be large, and metadata can contain the URLs/titles you pasted.


# Project Name
The Project Scope - Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut viverra interdum nisi. In hac habitasse platea dictumst. Integer tincidunt, felis a pellentesque scelerisque, turpis sapien lacinia lectus, eu ultricies nibh leo mollis metus. Nullam a velit condimentum, tempor felis sit amet, euismod lectus. Phasellus sed orci a lectus placerat lacinia sed ac magna. Pellentesque quis mollis dolor. Suspendisse vel imperdiet mauris, a aliquam urna. Ut mattis risus nec sem tincidunt, ac facilisis sem fringilla. Praesent placerat vehicula euismod. Suspendisse volutpat massa id massa facilisis porta. 

![Project_Image](.assets/Undaconstwuction.png)

## Features
* Some Mentionable Features that the Project focuses on

## [Hardware](/Hardware/README.md)
Hardware Overview - Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut viverra interdum nisi. In hac habitasse platea dictumst. Integer tincidunt, felis a pellentesque scelerisque, turpis sapien lacinia lectus, eu ultricies nibh leo mollis metus. Nullam a velit condimentum, tempor felis sit amet, euismod lectus. Phasellus sed orci a lectus placerat lacinia sed ac magna. Pellentesque quis mollis dolor. Suspendisse vel imperdiet mauris, a aliquam urna. Ut mattis risus nec sem tincidunt, ac facilisis sem fringilla. Praesent placerat vehicula euismod. Suspendisse volutpat massa id massa facilisis porta. 

## [Software](/Software/README.md)
Software Overview - Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut viverra interdum nisi. In hac habitasse platea dictumst. Integer tincidunt, felis a pellentesque scelerisque, turpis sapien lacinia lectus, eu ultricies nibh leo mollis metus. Nullam a velit condimentum, tempor felis sit amet, euismod lectus. Phasellus sed orci a lectus placerat lacinia sed ac magna. Pellentesque quis mollis dolor. Suspendisse vel imperdiet mauris, a aliquam urna. Ut mattis risus nec sem tincidunt, ac facilisis sem fringilla. Praesent placerat vehicula euismod. Suspendisse volutpat massa id massa facilisis porta. 

## [Embedded](/Embedded/README.md)
Embedded Overview - Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut viverra interdum nisi. In hac habitasse platea dictumst. Integer tincidunt, felis a pellentesque scelerisque, turpis sapien lacinia lectus, eu ultricies nibh leo mollis metus. Nullam a velit condimentum, tempor felis sit amet, euismod lectus. Phasellus sed orci a lectus placerat lacinia sed ac magna. Pellentesque quis mollis dolor. Suspendisse vel imperdiet mauris, a aliquam urna. Ut mattis risus nec sem tincidunt, ac facilisis sem fringilla. Praesent placerat vehicula euismod. Suspendisse volutpat massa id massa facilisis porta. 

## Roadmap
* Milestones: Things I've Completed/Achieved within the project
* Work In Progress: Things I'm Working on at the moment or havent completed yet
* Planned: Things that are planned for the future