import os

import uvicorn


def main() -> None:
    bind = os.getenv("DEADER_BIND") or "0.0.0.0"
    port = int(os.getenv("DEADER_PORT") or "8787")

    # Import after env is read so server module picks up env defaults.
    from app.server import app  # noqa: WPS433

    uvicorn.run(app, host=bind, port=port, log_level="info")


if __name__ == "__main__":
    main()

