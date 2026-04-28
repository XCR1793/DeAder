import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def _app_state_dir() -> Path:
    # Keep state out of the repo; safe for open-source.
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    d = Path(base) / "DeAder"
    d.mkdir(parents=True, exist_ok=True)
    return d


STATE_DIR = _app_state_dir()
LOCK_FILE = STATE_DIR / "deader.lock"
PID_FILE = STATE_DIR / "deader.pids"


def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _read_pids() -> tuple[Optional[int], Optional[int]]:
    """
    returns (tray_pid, server_pid)
    """
    try:
        raw = PID_FILE.read_text(encoding="utf-8").strip().splitlines()
        tray = int(raw[0]) if len(raw) > 0 and raw[0].strip().isdigit() else None
        server = int(raw[1]) if len(raw) > 1 and raw[1].strip().isdigit() else None
        return tray, server
    except Exception:
        return None, None


def _write_pids(tray_pid: int, server_pid: int) -> None:
    PID_FILE.write_text(f"{tray_pid}\n{server_pid}\n", encoding="utf-8")


def _taskkill(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )


def _acquire_single_instance(*, allow_multi: bool) -> Optional[object]:
    if allow_multi:
        return object()
    try:
        # Windows file lock: open and lock by exclusive create
        # If the file exists and is in use, Create will fail.
        return os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileExistsError:
        return None


def _release_single_instance(lock_handle: Optional[object]) -> None:
    if lock_handle is None or isinstance(lock_handle, object) and not isinstance(lock_handle, int):
        return
    try:
        os.close(lock_handle)
    except Exception:
        pass
    try:
        LOCK_FILE.unlink(missing_ok=True)  # py3.12+
    except Exception:
        pass


def _start_server(*, bind: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("DEADER_BIND", bind)
    env.setdefault("DEADER_PORT", str(port))

    creationflags = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server:app", "--host", bind, "--port", str(port)],
        cwd=str(Path(__file__).resolve().parent),
        env=env,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _open_browser(url: str) -> None:
    # Uses Windows shell association
    try:
        os.startfile(url)  # type: ignore[attr-defined]
    except Exception:
        pass


def _make_tray_icon():
    # Late import so non-Windows or missing deps fail gracefully at runtime
    import pystray
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, 58, 58], radius=12, fill=(156, 194, 255, 255))
    d.text((20, 18), "D", fill=(11, 14, 20, 255))

    return pystray.Icon("DeAder", img)


def main() -> int:
    ap = argparse.ArgumentParser(description="DeAder tray controller")
    ap.add_argument("--bind", default=os.getenv("DEADER_BIND") or "0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.getenv("DEADER_PORT") or "8787"))
    ap.add_argument("--multi", action="store_true", help="Allow multiple tray instances")
    ap.add_argument("--restart", action="store_true", help="Stop existing instance and start a new one")
    args = ap.parse_args()

    lock = _acquire_single_instance(allow_multi=args.multi)
    if lock is None:
        if args.restart:
            tray_pid, server_pid = _read_pids()
            if tray_pid:
                _taskkill(tray_pid)
            if server_pid:
                _taskkill(server_pid)
            time.sleep(1.0)
        else:
            # Already running; just open the UI and exit
            _open_browser(f"http://127.0.0.1:{args.port}")
            return 0

    try:
        # If something is already bound (e.g., old process), try to avoid confusion:
        if _is_port_open("127.0.0.1", args.port) and not args.multi:
            if args.restart:
                tray_pid, server_pid = _read_pids()
                if tray_pid:
                    _taskkill(tray_pid)
                if server_pid:
                    _taskkill(server_pid)
                time.sleep(1.0)
            else:
                _open_browser(f"http://127.0.0.1:{args.port}")
                return 0

        server = _start_server(bind=args.bind, port=args.port)
        _write_pids(os.getpid(), server.pid)

        icon = _make_tray_icon()

        def stop_server():
            try:
                server.terminate()
            except Exception:
                pass
            try:
                server.wait(timeout=4)
            except Exception:
                try:
                    server.kill()
                except Exception:
                    pass

        def on_open(_icon, _item):
            _open_browser(f"http://127.0.0.1:{args.port}")

        def on_restart(_icon, _item):
            stop_server()
            new_server = _start_server(bind=args.bind, port=args.port)
            nonlocal server
            server = new_server
            _write_pids(os.getpid(), server.pid)

        def on_quit(_icon, _item):
            stop_server()
            try:
                PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            icon.stop()

        import pystray

        icon.title = f"DeAder (port {args.port})"
        icon.menu = pystray.Menu(
            pystray.MenuItem("Open", on_open),
            pystray.MenuItem("Restart server", on_restart),
            pystray.MenuItem("Quit", on_quit),
        )

        # Quick feedback: open browser once it starts
        _open_browser(f"http://127.0.0.1:{args.port}")
        icon.run()
        return 0
    finally:
        _release_single_instance(lock)


if __name__ == "__main__":
    raise SystemExit(main())

