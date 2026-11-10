"""Entry point: ``python -m leond`` or the ``leon`` command."""

from __future__ import annotations

import sys

from leond.config import ConfigError, load, save_template


def main() -> int:
    try:
        save_template()
        cfg = load()
    except ConfigError as exc:
        print(f"LEON cannot start: {exc}", file=sys.stderr)
        return 2

    from leond.dock import run

    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
