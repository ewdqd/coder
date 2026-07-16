"""Desktop Pet AI Backend - Entry point

Usage:
    python backend/__main__.py --port 9876
    python backend/__main__.py --host 0.0.0.0 --port 9876
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def main() -> None:
    # Ensure backend/ is on sys.path for core.* and agent.* imports
    _backend_dir = Path(__file__).resolve().parent
    if str(_backend_dir) not in sys.path:
        sys.path.insert(0, str(_backend_dir))

    parser = argparse.ArgumentParser(description="Desktop Pet AI Backend")
    parser.add_argument("--host", default="", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="Bind port (default: 9876)")
    parser.add_argument("--config", default="", help="Path to config.yaml")
    args = parser.parse_args()

    # Load config
    config_path = Path(args.config) if args.config else _backend_dir / "config.yaml"
    config: dict = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    server_cfg = config.get("server", {})
    host = args.host or server_cfg.get("host", "127.0.0.1")
    port = args.port or server_cfg.get("port", 9876)

    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
