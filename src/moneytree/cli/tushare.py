from __future__ import annotations

import argparse
from pathlib import Path

from moneytree.data import DEFAULT_PARQUET_COMPRESSION
from moneytree.data import save_market_data
from moneytree.data_sources import TushareDailyConfig, fetch_tushare_cn_daily_panel
from moneytree.data_sources.tushare import TUSHARE_PROXY_MODES, TUSHARE_SANITY_CHECK_MODES


def _parse_tickers(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch TuShare A-share daily data into the Money Trees panel contract."
    )
    parser.add_argument("--start-date", required=True, help="Start date, YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="End date, YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--output", required=True, help="Output parquet path.")
    parser.add_argument(
        "--compression",
        default=DEFAULT_PARQUET_COMPRESSION,
        help="Output parquet compression codec. Default: zstd.",
    )
    parser.add_argument(
        "--compression-level",
        type=_positive_int,
        default=None,
        help="Output parquet compression level. Defaults to 3 for zstd.",
    )
    parser.add_argument(
        "--row-group-size",
        type=_positive_int,
        default=None,
        help="Optional output parquet row group size in rows.",
    )
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
    parser.add_argument(
        "--factor-dtype",
        default="float32",
        choices=["float32", "float64"],
        help="Dtype for generated alpha factor columns in the output parquet.",
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
        "--cache-compression",
        default=DEFAULT_PARQUET_COMPRESSION,
        help="Raw TuShare cache parquet compression codec. Default: zstd.",
    )
    parser.add_argument(
        "--cache-compression-level",
        type=_positive_int,
        default=None,
        help="Raw TuShare cache parquet compression level. Defaults to 3 for zstd.",
    )
    parser.add_argument(
        "--cache-row-group-size",
        type=_positive_int,
        default=None,
        help="Optional raw TuShare cache parquet row group size in rows.",
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
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print TuShare fetch and factor-generation progress to stderr.",
    )
    parser.add_argument(
        "--progress-every",
        type=_positive_int,
        default=50,
        help="When --progress is set, print one line every N trade dates.",
    )
    parser.add_argument(
        "--proxy-mode",
        default="direct",
        choices=TUSHARE_PROXY_MODES,
        help=(
            "TuShare proxy mode. 'direct' ignores shell proxy env vars; "
            "'env' uses them; 'proxy' uses --proxy-url. Default: direct."
        ),
    )
    parser.add_argument(
        "--proxy-url",
        default="",
        help="Explicit TuShare proxy URL, for example http://127.0.0.1:10810.",
    )
    parser.add_argument(
        "--no-fallback-direct",
        action="store_true",
        help="Disable one direct retry when env/proxy mode fails with a proxy error.",
    )
    parser.add_argument(
        "--sanity-check",
        default="warn",
        choices=TUSHARE_SANITY_CHECK_MODES,
        help="Post-standardization TuShare panel sanity check mode. Default: warn.",
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
        show_progress=bool(args.progress),
        progress_every=int(args.progress_every),
        factor_dtype=args.factor_dtype,
        proxy_mode="proxy" if args.proxy_url and args.proxy_mode == "direct" else args.proxy_mode,
        proxy_url=args.proxy_url or None,
        fallback_direct=not bool(args.no_fallback_direct),
        sanity_check=args.sanity_check,
        cache_compression=args.cache_compression,
        cache_compression_level=args.cache_compression_level,
        cache_row_group_size=args.cache_row_group_size,
    )
    frame = fetch_tushare_cn_daily_panel(config)
    save_market_data(
        frame,
        Path(args.output),
        compression=args.compression,
        compression_level=args.compression_level,
        row_group_size=args.row_group_size,
    )
    print(
        "Saved TuShare panel "
        f"rows={len(frame)} cols={len(frame.columns)} "
        f"start={frame.index.get_level_values('date').min().date()} "
        f"end={frame.index.get_level_values('date').max().date()} "
        f"path={args.output}"
    )


if __name__ == "__main__":
    main()
