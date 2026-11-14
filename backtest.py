#!/usr/bin/env python3
"""Rolling-origin backtest for btc-cent-forecast-01.

The six practice cases (p00..p05, four hours apart) each hold 4320 one-minute closes
ending at their checkpoint.  They overlap, so they stitch into one continuous series of
5520 minutes (2026-11-07T06:01Z .. 2026-11-11T06:00Z).  This script rebuilds that series
and replays the real task at many origins:

    origin i  ->  the 4320 closes ending at i (exactly what a case file holds)
                  target = the close 240 minutes later, at i + 240

so each origin sees only the window a real case would give it and nothing leaks forward.

Models compared (all guesses are last + a shift capped at 2% of last):
  persistence   guess = last close (the house baseline)
  baseline      guess = last + 0.2 * (EMA720 - last), the suggested starting model
  grid          guess = last + PULL * (EMA(span) - last), PULL and span swept, PULL < 0 too
  blend         guess = last + PULL * (w*EMA(a) + (1-w)*EMA(b) - last)
  momentum      guess = baseline shift + M * (last - close k minutes ago)

Each model's mean absolute error is reported in cents over every origin, over the 4 h
spaced origins (the spacing the real checkpoints have), and over the first and second
half of each set separately, so a model that only wins on one half is visible as such.
The five practice cases whose target is on the stitched series are scored on their own
too, as an out-of-sample check against the house's published 44521.576667 cents.

Run:  python3 backtest.py [--input DIR]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone

HORIZON = 240
WINDOW = 4320
STEP = 15
CAP = 0.02
SPANS = (240, 360, 720, 1440, 2880)
MOM_KS = (5, 15, 60, 240)
DEFAULT_INPUT = "/workspace/makefun/kits/btc-cent-forecast-01-kit/input"


# ---------------------------------------------------------------- data

def minute_of(iso: str) -> int:
    """Absolute minute index of an ISO 8601 UTC timestamp."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp()) // 60


def clean(prices):
    """Keep only finite positive numbers, as the entrypoint does."""
    out = []
    for p in prices:
        if isinstance(p, bool) or not isinstance(p, (int, float)):
            continue
        p = float(p)
        if p == p and p > 0 and p != float("inf"):
            out.append(p)
    return out


def stitch(input_dir: str):
    """Return (base_minute, series, cases) for the continuous series built from every *.in."""
    by_minute: dict[int, float] = {}
    cases = []
    for path in sorted(glob.glob(input_dir + "/*.in")):
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        market = doc["markets"][0]
        prices = clean(market.get("prices") or [])
        if doc.get("at"):
            base = minute_of(doc["at"]) - (len(prices) - 1)
        else:
            base = minute_of(market["start"])
        cases.append((doc.get("case", path.rsplit("/", 1)[-1]), base, prices))
        for k, p in enumerate(prices):
            m = base + k
            if m in by_minute and by_minute[m] != p:
                raise SystemExit(f"overlap disagreement at minute {m}")
            by_minute[m] = p
    if not by_minute:
        raise SystemExit(f"no cases found in {input_dir}")
    lo, hi = min(by_minute), max(by_minute)
    missing = [m for m in range(lo, hi + 1) if m not in by_minute]
    if missing:
        raise SystemExit(f"{len(missing)} missing minutes, first {missing[0]}")
    return lo, [by_minute[m] for m in range(lo, hi + 1)], cases


# ---------------------------------------------------------------- features

def ema_finals(prices, spans):
    """Final EMA for each span, alpha = 2/(span+1), seeded with the first price."""
    alphas = [2.0 / (s + 1.0) for s in spans]
    state = [prices[0]] * len(spans)
    for p in prices:
        for j, a in enumerate(alphas):
            state[j] += a * (p - state[j])
    return state


def features_table(series, origins):
    """One (last, emas, moms, target) tuple per origin, computed once for every model."""
    rows = []
    for i in origins:
        window = series[i - WINDOW + 1 : i + 1]
        last = window[-1]
        emas = dict(zip(SPANS, ema_finals(window, SPANS)))
        moms = {k: last - window[-1 - k] for k in MOM_KS if k < len(window)}
        rows.append((last, emas, moms, series[i + HORIZON]))
    return rows


# ---------------------------------------------------------------- models

def shift(last, anchor, pull):
    s = pull * (anchor - last)
    cap = CAP * last
    return last + max(-cap, min(cap, s))


def m_persistence(last, emas, moms):
    return last


def m_baseline(last, emas, moms):
    return shift(last, emas[720], 0.2)


def make_grid(pull, span):
    def f(last, emas, moms):
        return shift(last, emas[span], pull)
    return f


def make_blend(pull, a, b, w):
    def f(last, emas, moms):
        return shift(last, w * emas[a] + (1.0 - w) * emas[b], pull)
    return f


def make_momentum(pull, span, k, m):
    def f(last, emas, moms):
        s = shift(last, emas[span], pull) - last + m * moms.get(k, 0.0)
        cap = CAP * last
        return last + max(-cap, min(cap, s))
    return f


# ---------------------------------------------------------------- scoring

def score(model, table):
    return [abs(model(last, emas, moms) - target) * 100.0 for last, emas, moms, target in table]


def mae(errs):
    return sum(errs) / len(errs) if errs else float("nan")


def halves(errs):
    mid = len(errs) // 2
    return mae(errs[:mid]), mae(errs[mid:])


def build_models():
    models = [("persistence", m_persistence), ("baseline PULL=0.2 EMA720", m_baseline)]
    pulls = [round(-0.2 + 0.1 * k, 2) for k in range(0, 15)]  # -0.2 .. 1.2
    for span in SPANS:
        for pull in pulls:
            models.append((f"grid pull={pull:+.1f} span={span}", make_grid(pull, span)))
    for pull in (0.2, 0.3, 0.4, 0.5, 0.7, 0.9):
        for a, b in ((240, 720), (240, 1440), (720, 1440), (720, 2880), (360, 1440), (1440, 2880)):
            for w in (0.25, 0.5, 0.75):
                models.append((f"blend pull={pull:.1f} a={a} b={b} w={w:.2f}",
                               make_blend(pull, a, b, w)))
    for pull in (0.2, 0.3, 0.5, 0.7):
        for k in MOM_KS:
            for m in (-0.5, -0.25, 0.25, 0.5):
                models.append((f"momentum pull={pull:.1f} span=720 k={k} m={m:+.2f}",
                               make_momentum(pull, 720, k, m)))
    return models


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    args = ap.parse_args()

    base_min, series, cases = stitch(args.input)
    n = len(series)
    print(f"stitched {n} minutes ({n / 1440:.2f} days) from {cases[0][0]}..{cases[-1][0]}, "
          f"price {min(series):.2f}..{max(series):.2f}")

    # Origins aligned on the first full window, every STEP minutes.
    origins = list(range(WINDOW - 1, n - HORIZON, STEP))
    origins4 = origins[:: HORIZON // STEP]  # every 240 min: the real checkpoint spacing
    print(f"origins: {len(origins)} every {STEP} min, of which {len(origins4)} are 240 min apart; "
          f"each holds {WINDOW} minutes and targets +{HORIZON}")
    print()

    practice = []
    for name, cbase, prices in cases:
        i = cbase + len(prices) - 1 - base_min
        if i in set(origins) or (WINDOW - 1 <= i <= n - 1 - HORIZON):
            practice.append((name, i))
    scoreable = [p for p in practice if WINDOW - 1 <= p[1] <= n - 1 - HORIZON]
    print(f"practice-case origins scoreable: {[p[0] for p in scoreable]}")
    print()

    print("building the feature table (this is the slow part) ...")
    table = features_table(series, origins)
    idx = {i: k for k, i in enumerate(origins)}
    table4 = [table[idx[i]] for i in origins4]
    table_p = [table[idx[i]] for _, i in scoreable]
    print("done")
    print()

    rows = []
    for label, model in build_models():
        e = score(model, table)
        e4 = score(model, table4)
        lo, hi = halves(e)
        lo4, hi4 = halves(e4)
        rows.append((label, mae(e), lo, hi, mae(e4), lo4, hi4, mae(score(model, table_p))))

    rows.sort(key=lambda r: r[4])

    def show(r):
        label, allmae, lo, hi, a4, l4, h4, prac = r
        print(f"{label:40s} {allmae:10.2f} {lo:9.2f} {hi:9.2f} {a4:10.2f} {l4:9.2f} {h4:9.2f} {prac:10.2f}")

    hdr = (f"{'model':40s} {'all15':>10s} {'f15':>9s} {'s15':>9s} "
           f"{'all4h':>10s} {'f4h':>9s} {'s4h':>9s} {'practice':>10s}")
    print("top 30 by 4 h-origin MAE")
    print(hdr)
    print("-" * len(hdr))
    for r in rows[:30]:
        show(r)
    print()

    br = next(r for r in rows if r[0].startswith("baseline"))
    pr = next(r for r in rows if r[0] == "persistence")
    print("reference rows")
    print(hdr)
    show(br)
    show(pr)
    print()

    for setname, ai, li, hi_i in (("15 min", 1, 2, 3), ("4 h", 4, 5, 6)):
        print(f"candidates beating the baseline on overall AND both halves ({setname} origins):")
        found = False
        for r in rows:
            if r[0].startswith(("persistence", "baseline")):
                continue
            if r[ai] < br[ai] and r[li] < br[li] and r[hi_i] < br[hi_i]:
                found = True
                show(r)
        if not found:
            print("  none")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
