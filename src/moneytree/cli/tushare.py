from __future__ import annotations

import argparse
from pathlib import Path

from moneytree.data import save_market_data
from moneytree.data_sources import TushareDailyConfig, fetch_tushare_cn_daily_panel


def _parse_tickers(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch TuShare A-share daily data into the Money Tree panel contract."
    )
    parser.add_argument("--start-date", required=True, help="Start date, YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="End date, YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--output", required=True, help="Output parquet path.")
    parser.add_argument("--benchmark", default="000300.SH", help="Benchmark index code.")
    parser.add_argument(
        "--tickers",
        default="",
        help="Optional comma-separated TS codes. Empty means all names returned by TuShare daily.",
    )
    parser.add_argument(
        "--factor-family",
        action="append",
        default=[],
        choices=["alpha158", "alpha360"],
        help="Append local daily factor-family features. Repeatable.",
    )
    parser.add_argument("--env-file", default=".env", help="Env file containing the TuShare token.")
    parser.add_argument("--token", default="", help="Explicit TuShare token override.")
    parser.add_argument(
        "--complete-calendar",
        action="store_true",
        help="Reindex to trade-date x ticker and mark missing price rows as suspended.",
    )
    parser.add_argument(
        "--raw-features",
        action="store_true",
        help="Use raw prices instead of adjusted prices for local Alpha158/360 generation.",
    )
    parser.add_argument("--skip-daily-basic", action="store_true")
    parser.add_argument("--skip-adj-factor", action="store_true")
    parser.add_argument("--skip-limits", action="store_true")
    parser.add_argument("--skip-suspend", action="store_true")
    parser.add_argument("--skip-stock-basic", action="store_true")
    parser.add_argument(
        "--cache-dir",
        default="",
        help="Optional raw TuShare parquet cache directory, partitioned by API and trade date.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore existing raw cache files and rewrite them.",
    )
    parser.add_argument(
        "--refresh-recent-days",
        type=int,
        default=0,
        help="When caching, refresh the last N trade dates even if cache files exist.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = TushareDailyConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        benchmark=args.benchmark,
        tickers=_parse_tickers(args.tickers),
        factor_families=tuple(args.factor_family),
        env_file=args.env_file,
        token=args.token or None,
        include_daily_basic=not args.skip_daily_basic,
        include_adj_factor=not args.skip_adj_factor,
        include_limits=not args.skip_limits,
        include_suspend=not args.skip_suspend,
        include_stock_basic=not args.skip_stock_basic,
        complete_calendar=bool(args.complete_calendar),
        adjusted_features=not bool(args.raw_features),
        cache_dir=args.cache_dir or None,
        refresh_cache=bool(args.refresh_cache),
        refresh_recent_days=int(args.refresh_recent_days),
    )
    frame = fetch_tushare_cn_daily_panel(config)
    save_market_data(frame, Path(args.output))
    print(
        "Saved TuShare panel "
        f"rows={len(frame)} cols={len(frame.columns)} "
        f"start={frame.index.get_level_values('date').min().date()} "
        f"end={frame.index.get_level_values('date').max().date()} "
        f"path={args.output}"
    )


if __name__ == "__main__":
    main()
