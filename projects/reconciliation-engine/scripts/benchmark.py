"""Synthetic scale benchmark (no real data); reproduces the numbers in the README.

Usage:
    python scripts/benchmark.py --rows 100000 --workdir <directory outside the repo>

Generates N ops rows and N billing rows (every transaction unique, settled once,
all recorded in the same minute; 0.1% settled 5.00 higher), then times each
pandas stage, the SQL engine, and the full run (load, checks, report, CSVs)
with each engine. With the default options the data is the same (generator and
seed) as the benchmark used to review v1.0.0, so finding counts are comparable.

--unsettled-share and --spread-minutes make the duplicate-charge heuristic work
harder: some transactions never settle (legitimate orphans) and captures are
spread over the day instead of sharing one minute.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reconciliation import Config, __version__, run_reconciliation
from reconciliation.anomalies import run_detectors
from reconciliation.cleaning import clean_billing, clean_ops
from reconciliation.loaders import load_billing, load_ops
from reconciliation.matching import aggregate_billing, aggregate_ops, match_sources
from reconciliation.sql_engine import reconcile_sql


def _money(cents: np.ndarray) -> pd.Series:
    cents = pd.Series(cents)
    return (cents // 100).astype(str) + "." + (cents % 100).astype(str).str.zfill(2)


def generate(n: int, workdir: Path, unsettled_share: float, spread_minutes: int) -> Config:
    rng = np.random.default_rng(7)
    ids = [f"T{i:08d}" for i in range(n)]
    cents = rng.choice([50, 100, 200, 500, 1000], size=n) * 100 + rng.integers(0, 100, size=n)
    merchants = [f"Store {i}" for i in rng.integers(0, 5000, size=n)]
    channels = rng.choice(["OXXO", "SPEI", "CARD"], size=n)
    settled = cents.copy()
    settled[pd.Series(range(n)).sample(frac=0.001, random_state=1).index] += 500
    extra = np.random.default_rng(8)  # separate stream: defaults keep the v1.0.0 data
    recorded: object = "2025-03-01 10:00"
    if spread_minutes:
        offsets = pd.to_timedelta(extra.integers(0, spread_minutes, size=n), unit="m")
        recorded = (pd.Timestamp("2025-03-01 08:00") + offsets).strftime("%Y-%m-%d %H:%M")
    has_settlement = extra.random(n) >= unsettled_share
    workdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "transaction_id": ids,
            "merchant": merchants,
            "channel": channels,
            "amount": _money(cents),
            "currency": "MXN",
            "status": "captured",
            "recorded_at": recorded,
        }
    ).to_csv(workdir / "ops.csv", index=False)
    pd.DataFrame(
        {
            "statement_id": [f"S{i:08d}" for i in range(n)],
            "transaction_ref": ids,
            "settlement_amount": _money(settled),
            "currency": "MXN",
            "settled_at": "2025-03-02",
            "processor_fee": "1.00",
        }
    )[has_settlement].to_csv(workdir / "billing.csv", index=False)
    return Config(
        ops_path=workdir / "ops.csv",
        billing_path=workdir / "billing.csv",
        output_dir=workdir / "out",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=100_000, help="rows per source")
    parser.add_argument("--workdir", type=Path, required=True, help="where to write the CSVs")
    parser.add_argument("--repeats", type=int, default=3, help="runs per measurement")
    parser.add_argument(
        "--unsettled-share",
        type=float,
        default=0.0,
        help="fraction of transactions with no settlement row (default: 0)",
    )
    parser.add_argument(
        "--spread-minutes",
        type=int,
        default=0,
        help="spread recorded_at over this many minutes from 08:00, same day "
        "(default: 0, everything at 10:00)",
    )
    args = parser.parse_args()
    cfg = generate(args.rows, args.workdir, args.unsettled_share, args.spread_minutes)
    logging.disable(logging.WARNING)  # findings are counted below, not logged

    times: dict[str, list[float]] = {}

    def timed(name: str, fn, *fn_args):
        t0 = time.perf_counter()
        out = fn(*fn_args)
        times.setdefault(name, []).append(time.perf_counter() - t0)
        return out

    def load_both(cfg: Config):
        return load_ops(cfg), load_billing(cfg)

    def clean_both(ops_raw: pd.DataFrame, billing_raw: pd.DataFrame):
        return clean_ops(ops_raw)[0], clean_billing(billing_raw)[0]

    for _ in range(args.repeats):
        t0 = time.perf_counter()
        ops_raw, billing_raw = timed("load", load_both, cfg)
        ops, billing = timed("clean", clean_both, ops_raw, billing_raw)
        ops_agg = timed("aggregate_ops", aggregate_ops, ops)
        billing_agg = timed("aggregate_billing", aggregate_billing, billing)
        matched = timed("match", match_sources, ops_agg, billing_agg, cfg)
        findings = timed("detect", run_detectors, matched, ops, billing, cfg)
        times.setdefault("pandas total", []).append(time.perf_counter() - t0)
        _, sql_findings = timed("sql engine (match+rules)", reconcile_sql, ops, billing, cfg)
        for engine in ("pandas", "sql"):
            run_cfg = dataclasses.replace(cfg, engine=engine)
            timed(f"end-to-end ({engine})", run_reconciliation, run_cfg)

    print(
        f"reconciliation-engine {__version__} | pandas {pd.__version__} | "
        f"{args.rows:,} rows per source | unsettled share {args.unsettled_share} | "
        f"spread {args.spread_minutes} min | median of {args.repeats}"
    )
    for name, values in times.items():
        print(f"  {name:26s} {statistics.median(values):8.3f} s")
    for label, found in (("pandas", findings), ("sql", sql_findings)):
        counts = ", ".join(f"{k}={len(v):,}" for k, v in found.items() if len(v))
        print(f"  findings ({label}): {counts or 'none'}")


if __name__ == "__main__":
    main()
