from __future__ import annotations

import argparse

from .config import load_config
from .runner import run_relative_policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Relative Motion Query Tool policy node")
    parser.add_argument("--config", required=True, help="Path to relative pose policy YAML")
    args = parser.parse_args()
    return run_relative_policy(load_config(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
