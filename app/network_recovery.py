import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence, TypeVar

T = TypeVar("T")


DEFAULT_ERROR_SUBSTRINGS: tuple[str, ...] = (
    "Sign in to confirm you’re not a bot",
    "Sign in to confirm you're not a bot",
    "403: Forbidden",
    "403 Forbidden",
)


@dataclass(frozen=True)
class RecoveryCommands:
    """
    Keep these modular so you can swap VPN providers later.
    """

    vpn_rotate: Sequence[Sequence[str]] = (
        ("mullvad", "relay", "set", "location", "any"),
        ("mullvad", "connect"),
    )
    rm_ytdlp_cache: Sequence[str] = ("yt-dlp", "--rm-cache-dir")


class NetworkRecoveryCircuitBreaker:
    def __init__(
        self,
        *,
        max_rotations: int = 3,
        sleep_seconds: float = 8.0,
        error_substrings: Iterable[str] = DEFAULT_ERROR_SUBSTRINGS,
        commands: RecoveryCommands | None = None,
        cookies_path: Path | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.max_rotations = max(0, int(max_rotations))
        self.sleep_seconds = float(sleep_seconds)
        self.error_substrings = tuple(error_substrings)
        self.commands = commands or RecoveryCommands()
        self.cookies_path = cookies_path or Path("session_cookies.txt")
        self.cwd = cwd

    def should_refresh(self, err_text: str) -> bool:
        if not err_text:
            return False
        return any(s in err_text for s in self.error_substrings)

    def refresh_network_identity(self) -> None:
        """
        1) Rotate Mullvad exit node (or other provider commands)
        2) Purge yt-dlp cache dir
        3) Delete local cookies file (session_cookies.txt by default)
        4) Sleep to allow handshake/DNS propagation
        """

        # 2) Purge yt-dlp cache first (cheap and sometimes enough)
        self._run(self.commands.rm_ytdlp_cache, check=False)

        # 3) Delete local session cookies, if present
        try:
            if self.cookies_path.exists():
                self.cookies_path.unlink()
        except Exception:
            # Don't fail recovery purely because cookie cleanup failed
            pass

        # 2) Then rotate VPN identity
        for cmd in self.commands.vpn_rotate:
            self._run(cmd, check=True)

        # 4) Let VPN/DNS settle
        time.sleep(self.sleep_seconds)

    def run(self, task: Callable[[], T]) -> T:
        """
        Wrap your existing yt-dlp execution logic:

            breaker = NetworkRecoveryCircuitBreaker()
            result = breaker.run(lambda: ydl.extract_info(url, download=True))
        """

        last_exc: Optional[BaseException] = None
        for attempt in range(self.max_rotations + 1):
            try:
                return task()
            except Exception as e:
                last_exc = e
                msg = str(e)
                if attempt >= self.max_rotations or not self.should_refresh(msg):
                    raise
                self.refresh_network_identity()

        # unreachable, but keeps type-checkers happy
        assert last_exc is not None
        raise last_exc

    def _run(self, cmd: Sequence[str], *, check: bool) -> None:
        subprocess.run(
            list(cmd),
            cwd=str(self.cwd) if self.cwd else None,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=check,
        )

