import os
from typing import Any, Dict, Optional

from yt_dlp import YoutubeDL


def create_yt_dlp_compat(
    *,
    output_template: str,
    progress_hook,
    player_client: Optional[str] = None,
    po_token: Optional[str] = None,
    impersonate: Optional[str] = None,
    source_address: Optional[str] = None,
    concurrent_fragment_downloads: int = 8,
    use_aria2c: bool = False,
) -> YoutubeDL:
    """
    Create a yt-dlp instance with "compatibility" networking knobs:

    - YouTube player client selection via extractor_args (e.g. web_safari)
    - External PO token support (youtube:po_token=CLIENT+TOKEN)
    - TLS/browser impersonation via curl_cffi (ydl_opts['impersonate'])
    - Bind outgoing requests to a specific local IP (ydl_opts['source_address'])
    """

    extractor_args: Dict[str, Dict[str, str]] = {"youtube": {}}
    if player_client:
        extractor_args["youtube"]["player_client"] = player_client
    if po_token:
        # yt-dlp expects format like "web+TOKEN" depending on client.
        extractor_args["youtube"]["po_token"] = po_token

    ydl_opts: Dict[str, Any] = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": max(1, min(int(concurrent_fragment_downloads), 32)),
        "progress_hooks": [progress_hook] if progress_hook else [],
        "extractor_args": extractor_args,
        # Prefer an iOS-friendly progressive mp4 when ffmpeg isn't installed.
        "format": "b[ext=mp4]/best",
    }

    if source_address:
        ydl_opts["source_address"] = source_address

    if impersonate:
        # Requires curl_cffi installed. In modern yt-dlp this can be passed as string.
        # Example: "chrome-124:windows-10"
        ydl_opts["impersonate"] = impersonate

    if use_aria2c:
        ydl_opts["external_downloader"] = "aria2c"
        ydl_opts["external_downloader_args"] = ["-x", "16", "-s", "16", "-k", "1M"]

    return YoutubeDL(ydl_opts)


def create_yt_dlp_compat_from_env(*, output_template: str, progress_hook) -> YoutubeDL:
    """
    Same as create_yt_dlp_compat(), but reads config from environment variables:

    - DEADER_PLAYER_CLIENT: e.g. "web_safari"
    - DEADER_PO_TOKEN: e.g. "web+<token>" (see yt-dlp PO token guide)
    - DEADER_IMPERSONATE: e.g. "chrome-124:windows-10"
    - DEADER_SOURCE_ADDRESS: e.g. "192.168.1.50" or an IPv6 address from your range
    - DEADER_CONCURRENT_FRAGMENTS: e.g. "16"
    - DEADER_USE_ARIA2C: "true"/"false"
    """

    player_client = (os.getenv("DEADER_PLAYER_CLIENT") or "").strip() or None
    po_token = (os.getenv("DEADER_PO_TOKEN") or "").strip() or None
    impersonate = (os.getenv("DEADER_IMPERSONATE") or "").strip() or None
    source_address = (os.getenv("DEADER_SOURCE_ADDRESS") or "").strip() or None

    try:
        concurrent = int((os.getenv("DEADER_CONCURRENT_FRAGMENTS") or "").strip() or "8")
    except ValueError:
        concurrent = 8

    use_aria2c = (os.getenv("DEADER_USE_ARIA2C") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }

    return create_yt_dlp_compat(
        output_template=output_template,
        progress_hook=progress_hook,
        player_client=player_client,
        po_token=po_token,
        impersonate=impersonate,
        source_address=source_address,
        concurrent_fragment_downloads=concurrent,
        use_aria2c=use_aria2c,
    )

