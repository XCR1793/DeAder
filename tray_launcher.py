"""
DeAder launcher.

UI design:
  • A tkinter window is the primary visible UI (progress bar + status + buttons).
  • A pystray system-tray icon runs alongside as a bonus (best-effort; Windows
    sometimes hides tray icons in the ^ overflow).
  • Closing the X just minimizes/hides the window. To exit, click "Quit".

Startup flow:
  1) Show tkinter window IMMEDIATELY with a progress bar.
  2) Start the server in the background.
  3) Update progress while polling /api/metrics.
  4) ONLY when ready, open the browser at the LAN URL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import threading
import urllib.request
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk

import pystray
from PIL import Image, ImageDraw


# ---------- state paths ----------

def _state_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    d = Path(base) / "DeAder"
    d.mkdir(parents=True, exist_ok=True)
    return d


STATE = _state_dir()
LOCK = STATE / "deader.lock"
PIDS = STATE / "deader.pids"
LOG = STATE / "tray.log"


def log(msg: str) -> None:
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        LOG.open("a", encoding="utf-8").write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ---------- network helpers ----------

def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip != "127.0.0.1":
                return ip
        finally:
            s.close()
    except Exception:
        pass

    try:
        ps = (
            "$ips = Get-NetIPAddress -AddressFamily IPv4 | "
            "Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' } | "
            "Select-Object IPAddress,InterfaceAlias,PrefixOrigin; "
            "$pref = $ips | Where-Object { $_.InterfaceAlias -match 'Wi-?Fi|Ethernet' } | Select-Object -First 1; "
            "if (-not $pref) { $pref = $ips | Where-Object { $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 }; "
            "if (-not $pref) { $pref = $ips | Select-Object -First 1 }; "
            "if ($pref) { $pref.IPAddress }"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True, encoding="utf-8", errors="ignore",
        ).strip()
        if out and out != "127.0.0.1":
            return out
    except Exception:
        pass

    try:
        out = subprocess.check_output(["ipconfig"], text=True, encoding="utf-8", errors="ignore")
        for ip in re.findall(r"IPv4 Address[^\:]*:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", out):
            if ip != "127.0.0.1" and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def fetch_json(url: str, method: str = "GET", body: Optional[dict] = None, timeout: float = 1.0) -> Optional[dict]:
    try:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"content-type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def open_browser(url: str) -> None:
    try:
        os.startfile(url)  # type: ignore[attr-defined]
    except Exception:
        pass


# ---------- single-instance ----------

def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}"],
            text=True, encoding="utf-8", errors="ignore",
        )
        return str(pid) in out
    except Exception:
        return False


def read_pids() -> tuple[Optional[int], Optional[int]]:
    try:
        raw = PIDS.read_text(encoding="utf-8").strip().splitlines()
        tray = int(raw[0]) if len(raw) > 0 and raw[0].strip().isdigit() else None
        srv = int(raw[1]) if len(raw) > 1 and raw[1].strip().isdigit() else None
        return tray, srv
    except Exception:
        return None, None


def write_pids(tray_pid: int, server_pid: int) -> None:
    try:
        PIDS.write_text(f"{tray_pid}\n{server_pid}\n", encoding="utf-8")
    except Exception:
        pass


def kill_pid(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, check=False)


def acquire_lock(*, allow_multi: bool, force_restart: bool) -> Optional[object]:
    if allow_multi:
        return "multi"

    tray_pid, srv_pid = read_pids()
    if LOCK.exists() and (not tray_pid or not _pid_alive(tray_pid)):
        log(f"removing stale lock (tray_pid={tray_pid})")
        try:
            LOCK.unlink(missing_ok=True)
        except Exception:
            pass
        if srv_pid and _pid_alive(srv_pid):
            kill_pid(srv_pid)

    if force_restart:
        if tray_pid and _pid_alive(tray_pid):
            kill_pid(tray_pid)
        if srv_pid and _pid_alive(srv_pid):
            kill_pid(srv_pid)
        try:
            LOCK.unlink(missing_ok=True)
        except Exception:
            pass
        time.sleep(1.0)

    try:
        return os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        return None


def release_lock(handle: Optional[object]) -> None:
    if handle is None or handle == "multi":
        return
    try:
        os.close(int(handle))
    except Exception:
        pass
    try:
        LOCK.unlink(missing_ok=True)
    except Exception:
        pass


# ---------- server ----------

def start_server_proc(*, bind: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("DEADER_BIND", bind)
    env.setdefault("DEADER_PORT", str(port))
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server:app", "--host", bind, "--port", str(port)],
        cwd=str(Path(__file__).resolve().parent),
        env=env,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------- tray icon ----------

def render_icon(pct: int, *, ready: bool) -> Image.Image:
    pct = max(0, min(100, int(pct)))
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = (140, 220, 170, 255) if ready else (156, 194, 255, 255)
    d.rounded_rectangle([6, 6, 58, 58], radius=12, fill=base)
    d.text((20, 14), "D", fill=(11, 14, 20, 255))
    if not ready:
        x0, y0, x1, y1 = 14, 44, 50, 52
        d.rounded_rectangle([x0, y0, x1, y1], radius=4, fill=(11, 14, 20, 60))
        fill_w = int((x1 - x0) * (pct / 100.0))
        if fill_w > 0:
            d.rounded_rectangle([x0, y0, x0 + fill_w, y1], radius=4, fill=(11, 14, 20, 220))
    return img


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default=os.getenv("DEADER_BIND") or "0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.getenv("DEADER_PORT") or "8787"))
    ap.add_argument("--multi", action="store_true")
    ap.add_argument("--restart", action="store_true")
    args = ap.parse_args()

    lan_ip = get_lan_ip()
    lan_url = f"http://{lan_ip}:{args.port}"
    admin = f"http://127.0.0.1:{args.port}"
    log(f"start bind={args.bind} port={args.port} lan_ip={lan_ip} multi={args.multi} restart={args.restart}")

    lock = acquire_lock(allow_multi=args.multi, force_restart=args.restart)
    if lock is None:
        log("another instance is running; opening LAN URL via existing one")
        deadline = time.time() + 10
        while time.time() < deadline:
            if fetch_json(f"{admin}/api/metrics", timeout=0.5):
                break
            time.sleep(0.25)
        open_browser(lan_url)
        return 0

    state = {"pct": 0, "ready": False}
    server_holder: dict[str, Optional[subprocess.Popen]] = {"proc": None}

    # ---------- tkinter window (primary UI) ----------
    root = tk.Tk()
    root.title("DeAder")
    root.geometry("380x230")
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
        root.after(800, lambda: root.attributes("-topmost", False))
    except Exception:
        pass

    title_lbl = ttk.Label(root, text="Starting DeAder…", font=("Segoe UI", 12, "bold"))
    title_lbl.pack(pady=(14, 4))

    url_lbl = ttk.Label(root, text=f"URL: {lan_url}")
    url_lbl.pack()

    bar = ttk.Progressbar(root, orient="horizontal", length=320, mode="determinate", maximum=100)
    bar.pack(pady=(8, 4))

    status_lbl = ttk.Label(root, text="Initializing…")
    status_lbl.pack()

    btn_row1 = ttk.Frame(root)
    btn_row1.pack(pady=(10, 2))
    btn_row2 = ttk.Frame(root)
    btn_row2.pack(pady=(2, 2))
    btn_row3 = ttk.Frame(root)
    btn_row3.pack(pady=(2, 6))

    # ---------- pystray icon (bonus) ----------
    tray_icon: Optional[pystray.Icon] = None
    try:
        tray_icon = pystray.Icon("DeAder", render_icon(0, ready=False), title="DeAder (starting…)")
    except Exception:
        tray_icon = None

    def refresh_ui():
        try:
            bar["value"] = state["pct"]
            if state["ready"]:
                title_lbl.configure(text="DeAder is running")
                status_lbl.configure(text="Ready. Tap a button or open in your browser.")
            else:
                title_lbl.configure(text="Starting DeAder…")
                status_lbl.configure(text=f"Loading… {state['pct']}%")
        except Exception:
            pass
        if tray_icon is not None:
            try:
                tray_icon.icon = render_icon(state["pct"], ready=state["ready"])
                tray_icon.title = (
                    f"DeAder (port {args.port})" if state["ready"]
                    else f"DeAder (starting… {state['pct']}%)"
                )
            except Exception:
                pass

    # ---------- server lifecycle ----------
    def stop_server():
        proc = server_holder["proc"]
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=4)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        server_holder["proc"] = None
        state["ready"] = False
        state["pct"] = 0
        refresh_ui()
        log("server stopped")

    def start_and_wait(*, open_after: bool) -> None:
        state["ready"] = False
        state["pct"] = 1
        refresh_ui()

        proc = start_server_proc(bind=args.bind, port=args.port)
        server_holder["proc"] = proc
        write_pids(os.getpid(), proc.pid)
        log(f"server started pid={proc.pid}")

        start = time.time()
        timeout = 30.0
        while time.time() - start < timeout:
            if proc.poll() is not None:
                state["ready"] = False
                state["pct"] = 0
                title_lbl.configure(text="Server crashed during startup")
                refresh_ui()
                log("server crashed during startup")
                return

            elapsed = time.time() - start
            state["pct"] = max(state["pct"], min(99, int((elapsed / timeout) * 99) + 1))
            refresh_ui()

            if fetch_json(f"{admin}/api/metrics", timeout=0.5):
                state["ready"] = True
                state["pct"] = 100
                refresh_ui()
                log("server ready")
                if open_after:
                    open_browser(lan_url)
                    log(f"opened {lan_url}")
                return

            time.sleep(0.25)

        title_lbl.configure(text="Startup timeout")
        log("startup timeout")

    # ---------- buttons ----------
    def do_open():
        if state["ready"]:
            open_browser(lan_url)

    def do_restart():
        stop_server()
        threading.Thread(target=start_and_wait, kwargs={"open_after": False}, daemon=True).start()

    def do_stop():
        stop_server()

    def do_pause():
        fetch_json(f"{admin}/api/admin/pause", method="POST", body={"paused": True})

    def do_resume():
        fetch_json(f"{admin}/api/admin/pause", method="POST", body={"paused": False})

    def do_clear_dl():
        fetch_json(f"{admin}/api/admin/clear_downloads", method="POST")

    def do_clear_cache():
        fetch_json(f"{admin}/api/admin/clear_cache", method="POST")

    def do_quit():
        stop_server()
        try:
            PIDS.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            if tray_icon is not None:
                tray_icon.stop()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

    def do_hide():
        try:
            root.withdraw()
        except Exception:
            pass

    def show_window():
        try:
            root.deiconify()
            root.lift()
            root.attributes("-topmost", True)
            root.after(400, lambda: root.attributes("-topmost", False))
        except Exception:
            pass

    ttk.Button(btn_row1, text="Open", width=10, command=do_open).pack(side="left", padx=4)
    ttk.Button(btn_row1, text="Restart", width=10, command=do_restart).pack(side="left", padx=4)
    ttk.Button(btn_row1, text="Stop", width=10, command=do_stop).pack(side="left", padx=4)

    ttk.Button(btn_row2, text="Pause", width=10, command=do_pause).pack(side="left", padx=4)
    ttk.Button(btn_row2, text="Resume", width=10, command=do_resume).pack(side="left", padx=4)
    ttk.Button(btn_row2, text="Hide", width=10, command=do_hide).pack(side="left", padx=4)

    ttk.Button(btn_row3, text="Clear DL", width=10, command=do_clear_dl).pack(side="left", padx=4)
    ttk.Button(btn_row3, text="Clear Cache", width=10, command=do_clear_cache).pack(side="left", padx=4)
    ttk.Button(btn_row3, text="Quit", width=10, command=do_quit).pack(side="left", padx=4)

    # X button = hide (keeps server + tray running)
    root.protocol("WM_DELETE_WINDOW", do_hide)

    # ---------- pystray menu ----------
    if tray_icon is not None:
        def tray_open(_i, _it):
            do_open()

        def tray_show(_i, _it):
            root.after(0, show_window)

        def tray_restart(_i, _it):
            do_restart()

        def tray_stop(_i, _it):
            do_stop()

        def tray_pause(_i, _it):
            do_pause()

        def tray_resume(_i, _it):
            do_resume()

        def tray_clear_dl(_i, _it):
            do_clear_dl()

        def tray_clear_cache(_i, _it):
            do_clear_cache()

        def tray_quit(_i, _it):
            root.after(0, do_quit)

        tray_icon.menu = pystray.Menu(
            pystray.MenuItem(lambda _it: f"URL: {lan_url}", tray_open),
            pystray.MenuItem(
                lambda _it: ("Status: ready" if state["ready"] else f"Status: starting… {state['pct']}%"),
                None, enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show window", tray_show, default=True),
            pystray.MenuItem("Open browser", tray_open),
            pystray.MenuItem("Restart server", tray_restart),
            pystray.MenuItem("Stop server", tray_stop),
            pystray.MenuItem("Pause downloads", tray_pause),
            pystray.MenuItem("Resume downloads", tray_resume),
            pystray.MenuItem("Clear downloads", tray_clear_dl),
            pystray.MenuItem("Clear yt-dlp cache", tray_clear_cache),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", tray_quit),
        )

    # ---------- run server bring-up in a thread ----------
    threading.Thread(target=start_and_wait, kwargs={"open_after": True}, daemon=True).start()

    # ---------- run pystray icon in a daemon thread (best-effort) ----------
    if tray_icon is not None:
        def _run_tray():
            try:
                tray_icon.run()
            except Exception as e:
                log(f"tray run error: {e}")

        threading.Thread(target=_run_tray, daemon=True).start()

    refresh_ui()

    try:
        root.mainloop()
        return 0
    finally:
        try:
            if tray_icon is not None:
                tray_icon.stop()
        except Exception:
            pass
        release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
