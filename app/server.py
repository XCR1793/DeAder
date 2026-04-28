import asyncio
import json
import mimetypes
import os
import re
import secrets
import time
import sys
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.ytdlp_compat import create_yt_dlp_compat_from_env


def _resource_root() -> Path:
    # When bundled via PyInstaller, static files are unpacked to sys._MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    # For the packaged EXE, store downloads next to the executable (persistent & writable).
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = _resource_root()
DATA_ROOT = _data_root()
WEB_DIR = ROOT / "web"
DOWNLOADS_DIR = DATA_ROOT / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

DEADER_TOKEN = os.getenv("DEADER_TOKEN")  # optional but strongly recommended
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("DEADER_MAX_JOBS") or "2")
CONCURRENT_FRAGMENTS = int(os.getenv("DEADER_CONCURRENT_FRAGMENTS") or "8")
USE_ARIA2C = (os.getenv("DEADER_USE_ARIA2C") or "").strip().lower() in {"1", "true", "yes", "y", "on"}

DOWNLOADS_PAUSED = False
ACTIVE_HTTP_REQUESTS = 0
ACTIVE_MEDIA_REQUESTS = 0


def _is_probably_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value.strip(), flags=re.IGNORECASE))


def _safe_id() -> str:
    # short, URL-safe id
    return secrets.token_urlsafe(10)


@dataclass
class Job:
    id: str
    url: str
    status: str  # queued | downloading | finished | error
    created_at: float
    updated_at: float
    finished_at: Optional[float] = None
    last_accessed_at: Optional[float] = None
    duration_seconds: Optional[float] = None
    progress: float = 0.0
    eta_seconds: Optional[int] = None
    speed: Optional[str] = None
    title: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None

    def ttl_seconds(self) -> Optional[float]:
        if self.status != "finished" or not self.duration_seconds:
            return None
        # expiry = max(1h, 2x duration) capped to 48h
        return min(48 * 3600.0, max(3600.0, 2.0 * float(self.duration_seconds)))


async def _cleanup_loop() -> None:
    while True:
        try:
            _cleanup_expired_downloads()
        except Exception:
            # best-effort cleanup; never crash the server
            pass
        await asyncio.sleep(300)  # every 5 minutes


def _cleanup_expired_downloads() -> None:
    now = time.time()
    for job_id, job in list(jobs.items()):
        if job.status != "finished" or not job.filename:
            continue
        ttl = job.ttl_seconds()
        if ttl is None:
            continue
        last_access = job.last_accessed_at or job.finished_at or job.updated_at or job.created_at
        if not last_access:
            continue
        if now - last_access < ttl:
            continue

        path = DOWNLOADS_DIR / job.filename
        meta = DOWNLOADS_DIR / f"{job_id}.json"
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        try:
            if meta.exists():
                meta.unlink()
        except Exception:
            pass

        # Mark as expired so API requests don't 404 mysteriously
        job.status = "error"
        job.error = "Expired and removed to free disk space."
        job.updated_at = now


jobs: Dict[str, Job] = {}
job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


app = FastAPI()
app.mount("/static", StaticFiles(directory=str(WEB_DIR), html=False), name="static")


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_cleanup_loop())


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not DEADER_TOKEN:
        return await call_next(request)

    # allow token via header (preferred) or query param (easy for iOS bookmarks)
    supplied = request.headers.get("x-auth-token") or request.query_params.get("token")
    if supplied != DEADER_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return await call_next(request)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    global ACTIVE_HTTP_REQUESTS, ACTIVE_MEDIA_REQUESTS
    ACTIVE_HTTP_REQUESTS += 1
    is_media = request.url.path.startswith("/media/")
    if is_media:
        ACTIVE_MEDIA_REQUESTS += 1
    try:
        return await call_next(request)
    finally:
        ACTIVE_HTTP_REQUESTS = max(0, ACTIVE_HTTP_REQUESTS - 1)
        if is_media:
            ACTIVE_MEDIA_REQUESTS = max(0, ACTIVE_MEDIA_REQUESTS - 1)


def _require_localhost(request: Request) -> None:
    host = (request.client.host if request.client else "") or ""
    if host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Localhost only")


@app.get("/api/metrics")
async def metrics(request: Request):
    _require_localhost(request)
    total = len(jobs)
    queued = sum(1 for j in jobs.values() if j.status == "queued")
    downloading = sum(1 for j in jobs.values() if j.status == "downloading")
    finished = sum(1 for j in jobs.values() if j.status == "finished")
    errors = sum(1 for j in jobs.values() if j.status == "error")
    return {
        "downloads_paused": DOWNLOADS_PAUSED,
        "jobs_total": total,
        "jobs_queued": queued,
        "jobs_downloading": downloading,
        "jobs_finished": finished,
        "jobs_error": errors,
        "active_http_requests": ACTIVE_HTTP_REQUESTS,
        "active_media_streams": ACTIVE_MEDIA_REQUESTS,
    }


@app.post("/api/admin/pause")
async def admin_pause(request: Request, payload: Dict[str, Any]):
    global DOWNLOADS_PAUSED
    _require_localhost(request)
    DOWNLOADS_PAUSED = bool(payload.get("paused"))
    return {"downloads_paused": DOWNLOADS_PAUSED}


@app.post("/api/admin/clear_downloads")
async def admin_clear_downloads(request: Request):
    _require_localhost(request)
    removed = 0
    for p in DOWNLOADS_DIR.glob("*"):
        if p.is_file():
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
    # mark finished jobs as expired if their file is gone
    now = time.time()
    for j in jobs.values():
        if j.status == "finished":
            j.status = "error"
            j.error = "Cleared by admin."
            j.updated_at = now
    return {"removed_files": removed}


@app.post("/api/admin/clear_cache")
async def admin_clear_cache(request: Request):
    _require_localhost(request)
    # Run cache purge using the same Python interpreter
    try:
        subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--rm-cache-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        pass
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index():
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
async def create_job(payload: Dict[str, Any]):
    if DOWNLOADS_PAUSED:
        raise HTTPException(status_code=503, detail="Downloads are paused.")
    url = (payload.get("url") or "").strip()
    if not url or not _is_probably_url(url):
        raise HTTPException(status_code=400, detail="Provide a valid http(s) URL.")

    job_id = _safe_id()
    now = time.time()
    job = Job(
        id=job_id,
        url=url,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    jobs[job_id] = job
    asyncio.create_task(_run_job(job_id))
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")

    out = asdict(job)
    if job.status == "finished" and job.filename:
        out["watch_url"] = f"/watch/{job.id}"
        out["media_url"] = f"/media/{job.id}"
    return out


@app.get("/watch/{job_id}", response_class=HTMLResponse)
async def watch(job_id: str):
    job = jobs.get(job_id)
    if not job or job.status != "finished" or not job.filename:
        raise HTTPException(status_code=404, detail="Not ready")

    job.last_accessed_at = time.time()
    job.updated_at = job.last_accessed_at

    token_qs = ""
    if DEADER_TOKEN:
        # keep navigation working when user uses query-token auth
        token = DEADER_TOKEN
        token_qs = f"?token={token}"

    title = (job.title or "Video").replace("<", "").replace(">", "")
    media_url = f"/media/{job.id}{token_qs}"
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      body {{ font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial, sans-serif; margin: 0; background: #0b0e14; color: #e7eaf0; }}
      header {{ padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.08); }}
      main {{ padding: 16px; }}
      .wrap {{ max-width: 900px; margin: 0 auto; }}
      video {{ width: 100%; max-height: 75vh; background: black; border-radius: 12px; }}
      a {{ color: #9cc2ff; text-decoration: none; }}
    </style>
  </head>
  <body>
    <header><div class="wrap"><strong>{title}</strong></div></header>
    <main>
      <div class="wrap">
        <video controls playsinline preload="metadata" src="{media_url}"></video>
        <div style="margin-top: 12px; opacity: 0.8;">
          <a href="/{token_qs.lstrip('?') if token_qs else ''}">Download another</a>
        </div>
      </div>
    </main>
  </body>
</html>"""
    )


@app.get("/media/{job_id}")
async def media(job_id: str):
    job = jobs.get(job_id)
    if not job or job.status != "finished" or not job.filename:
        raise HTTPException(status_code=404, detail="Not found")

    job.last_accessed_at = time.time()
    job.updated_at = job.last_accessed_at

    path = DOWNLOADS_DIR / job.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Missing file")

    mime, _ = mimetypes.guess_type(str(path))
    # iOS Safari is happiest with mp4/h264+aac; but still serve whatever we have.
    return FileResponse(
        path=str(path),
        media_type=mime or "application/octet-stream",
        filename=path.name,
    )


@app.get("/jobs/{job_id}")
async def legacy_redirect(job_id: str):
    return RedirectResponse(url=f"/watch/{job_id}")


async def _run_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return

    async with job_semaphore:
        job.status = "downloading"
        job.updated_at = time.time()

        outtmpl = str(DOWNLOADS_DIR / f"{job_id}.%(ext)s")

        def hook(d: Dict[str, Any]):
            j = jobs.get(job_id)
            if not j:
                return
            j.updated_at = time.time()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                if total:
                    j.progress = max(0.0, min(1.0, downloaded / total))
                j.eta_seconds = d.get("eta")
                j.speed = d.get("_speed_str")
            elif d.get("status") == "finished":
                j.progress = 1.0

        ydl_opts: Dict[str, Any] = {
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            # Speed/robustness: more parallel fragments often increases throughput on DASH/HLS.
            "concurrent_fragment_downloads": max(1, min(CONCURRENT_FRAGMENTS, 32)),
            "retries": 10,
            "fragment_retries": 10,
            "progress_hooks": [hook],
            # Prefer an iOS-friendly progressive mp4 when ffmpeg isn't installed.
            "format": "b[ext=mp4]/best",
        }

        if USE_ARIA2C:
            # aria2c can be significantly faster/more stable on some networks.
            # Requires aria2c installed and on PATH.
            ydl_opts["external_downloader"] = "aria2c"
            ydl_opts["external_downloader_args"] = [
                "-x",
                "16",
                "-s",
                "16",
                "-k",
                "1M",
            ]

        try:
            info = await asyncio.to_thread(_download_one, job.url, ydl_opts)
            job.title = info.get("title") or job.title
            dur = info.get("duration")
            if isinstance(dur, (int, float)) and dur > 0:
                job.duration_seconds = float(dur)

            # Resolve the final filename that yt-dlp produced.
            ext = info.get("ext")
            if ext:
                job.filename = f"{job_id}.{ext}"
            else:
                # fallback: scan downloads dir
                matches = list(DOWNLOADS_DIR.glob(f"{job_id}.*"))
                if not matches:
                    raise RuntimeError("Download finished but no output file found.")
                job.filename = matches[0].name

            job.status = "finished"
            job.finished_at = time.time()
            job.updated_at = job.finished_at
            job.last_accessed_at = job.finished_at

            # persist minimal metadata for debugging (optional)
            meta_path = DOWNLOADS_DIR / f"{job_id}.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "id": job_id,
                        "url": job.url,
                        "title": job.title,
                        "filename": job.filename,
                        "duration_seconds": job.duration_seconds,
                        "finished_at": job.finished_at,
                        "last_accessed_at": job.last_accessed_at,
                        "ttl_seconds": job.ttl_seconds(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            job.status = "error"
            job.error = str(e)
            job.updated_at = time.time()


def _download_one(url: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
    # Keep existing speed settings in server.py, but also apply network-compat options
    # from environment (player_client, po_token, impersonate, source_address).
    def hook(d: Dict[str, Any]):
        for h in ydl_opts.get("progress_hooks") or []:
            try:
                h(d)
            except Exception:
                pass

    ydl = create_yt_dlp_compat_from_env(output_template=ydl_opts["outtmpl"], progress_hook=hook)
    # Preserve these runtime options from the caller (job-specific tuning)
    for k in (
        "format",
        "concurrent_fragment_downloads",
        "retries",
        "fragment_retries",
        "external_downloader",
        "external_downloader_args",
    ):
        if k in ydl_opts:
            ydl.params[k] = ydl_opts[k]

    with ydl:
        return ydl.extract_info(url, download=True)

