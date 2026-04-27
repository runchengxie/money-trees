from __future__ import annotations

from moneytree.cli.dolphindb_alphas import (
    DEFAULT_ALPHA101_FUNCTION,
    DEFAULT_ALPHA191_FUNCTION,
    GenerationResult,
    build_parser,
    load_dolphindb_client,
    main,
    run_generation,
)

__all__ = [
    "DEFAULT_ALPHA101_FUNCTION",
    "DEFAULT_ALPHA191_FUNCTION",
    "GenerationResult",
    "build_parser",
    "load_dolphindb_client",
    "main",
    "run_generation",
]


if __name__ == "__main__":
    raise SystemExit(main())
