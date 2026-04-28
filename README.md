# DeAder

DeAder is a small self-hosted web app for **"paste a link → server downloads → phone streams it in the browser"**, powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).

It's built for the everyday case: you're on iOS Safari, you paste a YouTube/etc. link on your phone, and you want the resulting file to **play in-browser** without fiddly steps.

---

## Features

- **Paste URL → server downloads** via `yt-dlp`
- **Auto-redirects to a player page** that streams the file (HTTP range requests, iOS-friendly)
- **LAN-friendly**: run on your PC, watch on your phone over Wi-Fi
- **One-click Windows launcher** (`DeAder.bat`) with a desktop window + system tray icon
- **Optional token** auth so the server isn't an open download endpoint
- **Auto-cleanup**: removes old downloads after inactivity to free disk space
- **Network compatibility knobs**: player client, PO token, TLS impersonation, source IP binding
- **Optional automated recovery**: VPN rotation + cache purge + retry on `403` / bot-check failures

---

## Quick start (Windows)

Just double-click **`DeAder.bat`**.

It will:

1. Create a `.venv` and install dependencies the first time (hidden, no popups)
2. Open a small **DeAder control window** with a startup progress bar
3. Add a **system tray icon** (bonus, may live in the hidden overflow `^`)
4. Once the server is fully ready, **open your browser to your LAN URL** (e.g. `http://192.168.1.20:8787`)

The control window has buttons for **Open**, **Restart**, **Pause / Resume**, **Clear Downloads**, **Clear Cache**, and **Quit**. Closing it (X) just hides it; use **Quit** to fully stop the server.

### Single-instance behavior

By default `DeAder.bat` is single-instance — running it again just opens the browser to the existing server.

| Switch | Effect |
| --- | --- |
| `DeAder.bat` | Start, or focus existing instance |
| `DeAder.bat --restart` | Stop the existing instance, then start fresh |
| `DeAder.bat --multi` | Allow multiple instances (advanced) |

### Tray / window metrics (privacy-safe)

Counts only — no URLs, titles, or client IPs are shown:

- jobs queued / downloading / finished / error
- active HTTP requests
- active media streams

---

## Use on iPhone / Android (same Wi-Fi)

1. On your **PC**, find your LAN IP (the launcher prints it in the control window):

   ```powershell
   ipconfig
   ```

   Look for the `IPv4 Address` of your Wi-Fi/Ethernet adapter (e.g. `192.168.1.20` or `10.0.0.164`).

2. On your **phone**, open Safari/Chrome and go to:

   ```
   http://YOUR_PC_LAN_IP:8787
   ```

3. Paste a video URL → wait → it auto-redirects to a player page that streams from your PC.

---

## Phone says "request timed out"? (LAN troubleshooting)

This is almost always **one of three things**. Fix in this order:

### 1. Network must be set to "Private", not "Public"

Windows blocks inbound LAN traffic on **Public** networks by default. Check:

```powershell
Get-NetConnectionProfile | Select-Object Name,InterfaceAlias,NetworkCategory
```

If your home Wi-Fi shows `Public`, change it (run **PowerShell as Administrator**):

```powershell
Set-NetConnectionProfile -Name "YOUR_WIFI_NAME" -NetworkCategory Private
```

> Only do this on networks you trust (home, not coffee shops).

### 2. Firewall must allow inbound TCP 8787

In **PowerShell as Administrator**:

```powershell
New-NetFirewallRule -DisplayName "DeAder" -Direction Inbound -Action Allow `
  -Protocol TCP -LocalPort 8787 -Profile Private,Domain
```

To verify:

```powershell
Get-NetFirewallRule -DisplayName "DeAder" | Format-Table DisplayName,Enabled,Profile,Action
```

### 3. Same network, no VPN split-brain

- The phone and PC must be on the **same Wi-Fi**.
- A VPN on the PC (e.g. Mullvad) usually doesn't break LAN, but a VPN on the **phone** routes traffic through the internet instead of the LAN — disable it for testing.
- Mobile hotspots / "guest" Wi-Fi modes often isolate clients from each other; switch to your normal Wi-Fi.

After fixing, on your PC you can sanity-check that the port is listening on all interfaces:

```powershell
netstat -ano | findstr ":8787"
# Should show:  TCP    0.0.0.0:8787    0.0.0.0:0    LISTENING
```

---

## Security (recommended)

By default, DeAder will download anything posted to it. Lock it down with a token:

```powershell
$env:DEADER_TOKEN="some-long-random-string"
.\DeAder.bat
```

In the web UI, tap **Set token** once and paste the same string. The token is sent as `x-auth-token` (or `?token=...`) on every request.

---

## Run without the launcher (advanced)

If you'd rather run the server directly (visible terminal, easy logs):

```powershell
cd <repo>
.\run.ps1
```

Then open `http://localhost:8787` on the PC, or `http://YOUR_PC_LAN_IP:8787` from another device.

## Build a portable EXE

```powershell
.\build.ps1
```

Output: `dist\DeAder.exe`. When run from the EXE, downloads are stored in a `downloads/` folder next to the EXE.

---

## Speed tips

- **`ffmpeg`** on the server unlocks higher-quality formats. Without it, DeAder prefers an iOS-friendly progressive MP4.
- **Increase fragment concurrency**:

  ```powershell
  $env:DEADER_CONCURRENT_FRAGMENTS="16"
  ```

- **Use `aria2c`** (install separately, then enable):

  ```powershell
  $env:DEADER_USE_ARIA2C="true"
  ```

---

## Auto-cleanup (disk space)

Each downloaded file gets a TTL based on **last access time**:

- minimum **1 hour**
- or **2× the video duration**
- capped at **48 hours**

A background task runs every 5 minutes and removes anything past its TTL.

---

## Network compatibility knobs (403 / TLS issues)

All read from environment variables, applied to the `yt-dlp` instance.

```powershell
# Different YouTube player client signature
$env:DEADER_PLAYER_CLIENT="web_safari"

# PO token (format: client+token, e.g. "web+...")
$env:DEADER_PO_TOKEN="web+PASTE_TOKEN_HERE"

# curl_cffi impersonation (modern Chrome TLS fingerprint)
$env:DEADER_IMPERSONATE="chrome-124:windows-10"

# Bind outgoing connections to a specific local IP (IPv4/IPv6)
$env:DEADER_SOURCE_ADDRESS="YOUR_LOCAL_IP"
```

## Automated network recovery (Mullvad rotation + retry)

For transient `403` or "confirm you're not a bot" failures, the circuit breaker in `app/network_recovery.py` will:

- Rotate Mullvad exit (commands configurable)
- Run `yt-dlp --rm-cache-dir`
- Delete `session_cookies.txt` if present
- Sleep 8 seconds
- Retry up to 3 rotations

---

## Configuration reference

| Env var | Default | What it does |
| --- | --- | --- |
| `DEADER_TOKEN` | _(empty)_ | Required header `x-auth-token` if set |
| `DEADER_BIND` | `0.0.0.0` | Listen address |
| `DEADER_PORT` | `8787` | Listen port |
| `DEADER_MAX_JOBS` | `3` | Max simultaneous downloads |
| `DEADER_CONCURRENT_FRAGMENTS` | `8` | yt-dlp parallel fragments |
| `DEADER_USE_ARIA2C` | `false` | Use `aria2c` as external downloader |
| `DEADER_PLAYER_CLIENT` | _(empty)_ | yt-dlp `extractor_args.youtube.player_client` |
| `DEADER_PO_TOKEN` | _(empty)_ | yt-dlp `extractor_args.youtube.po_token` |
| `DEADER_IMPERSONATE` | _(empty)_ | curl_cffi target (e.g. `chrome-124:windows-10`) |
| `DEADER_SOURCE_ADDRESS` | _(empty)_ | Bind outbound to a local IP |

---

## Open-source hygiene

The repo is meant to be public, but normal use produces files that may contain personal data (URLs, cookies, tokens). The `.gitignore` already excludes:

- `.env*`, `session_cookies*.txt`, `cookies*.txt`
- build outputs (`dist/`, `build/`, `*.spec`)
- logs (`*.log`)
- `downloads/*.json` metadata, `downloads/*.part`, `downloads/*.ytdl`

Be careful before committing anything inside `downloads/` — file names and metadata reveal the URLs/titles you've fetched.

---

## License

See `LICENSE` (if present) for terms. This project bundles `yt-dlp`, which is itself an Unlicense-licensed project.
