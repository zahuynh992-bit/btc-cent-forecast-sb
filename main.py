#!/usr/bin/env python3
"""btc-cent-forecast-01: a damped mean-reversion forecaster for BTC/USDC, 240 minutes ahead.

The task: given the 4320 one-minute closes up to a checkpoint, guess the close 240 minutes
later.  The score is the mean absolute error in cents, so the guess wants to be the middle
of where the price is likely to be, not a direction bet.

MODEL (chosen by backtest.py)

    gap   = EMA360(last 4320 closes, alpha = 2/361, seeded with the first close) - last
    shift = 0.3 * gap, clipped to +/- 2% of last
    guess = last + shift

Mean reversion is real here and quite strong: across the 65 rolling origins below, the
next 240-minute percentage move correlates 0.62 with the EMA720 gap, with an OLS slope of
about 1.0.  A full pull toward the average would be far too aggressive for a point
forecast (the path wanders), so the shift is damped and capped.

BACKTEST (backtest.py; the six practice cases stitched into one 5520-minute series, rolled
every 15 minutes, each origin holding exactly the 4320-minute window a real case holds and
targeting the close 240 minutes later; 65 origins, mean absolute error in cents)

    model                                all       first half   second half
    persistence (house baseline)     51816.90      58447.43      45387.29
    last + 0.2*(EMA720 - last)       49600.21      61299.07      38255.85   <- suggested start
    last + 0.3*(EMA360 - last)       49447.15      61149.81      38099.11   <- chosen

The suggested 0.2/EMA720 baseline beats persistence overall but loses on the first half of
the origins.  Of every candidate swept (pull -0.2..1.2, EMA span 240..2880, two-EMA blends,
short momentum), exactly one beat that baseline on the overall figure AND on both halves:
pull 0.3 with an EMA span of 360, by 0.3%.  That is the switch this entry makes.  It is a
narrow margin, so it is stated plainly rather than dressed up: on the five practice-shaped
origins (the 4-hour-spaced ones, the spacing the scored checkpoints have) persistence
itself scores 47054.66, the 0.2/EMA720 baseline 48160.99 and this model 48295.79, and a
six-fold cross-validation of the grid picks a different cell each time.  The pull is real
in sign and small in size, which is why it is damped to 0.3 and capped at 2%: the model
gives up a little if mean reversion is absent and gains a little when it is there.

DETERMINISM: no randomness, no clock, no network, no environment beyond the two directory
variables.  Two runs on the same case write the same bytes.

Run locally:
    MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

from __future__ import annotations

import json
import math
import os
import sys

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"

PULL = 0.3           # share of the gap to the EMA the forecast closes
SPAN = 360           # EMA span in minutes
CAP = 0.02           # the shift never exceeds 2% of the last close
MIN_PRICE = 0.00001  # one unit of the grid's 5 decimals
MAX_PRICE = 9999999.99999


def clean(prices):
    """The finite, positive closes of a series, in order.

    Anything that is not a real number, not finite, or not positive is dropped: the rules
    say to ignore those, and a NaN would poison every mean downstream.
    """
    out = []
    if not isinstance(prices, list):
        return out
    for p in prices:
        if isinstance(p, bool) or not isinstance(p, (int, float)):
            continue
        p = float(p)
        if math.isfinite(p) and p > 0.0:
            out.append(p)
    return out


def ema(prices, span):
    """Exponential moving average over the whole series, seeded with its first price."""
    if not prices:
        return None
    alpha = 2.0 / (span + 1.0)
    state = prices[0]
    for p in prices:
        state += alpha * (p - state)
    return state


def forecast(prices):
    """The guess for one market: its cleaned closes in, the price 240 minutes later out."""
    series = clean(prices)
    if not series:
        # No usable price at all: any guess is a shot in the dark, so keep the output valid
        # and the run deterministic rather than crashing the case.
        return MIN_PRICE
    last = series[-1]
    anchor = ema(series, SPAN)
    if anchor is None:
        guess = last
    else:
        shift = PULL * (anchor - last)
        cap = CAP * last
        if shift > cap:
            shift = cap
        elif shift < -cap:
            shift = -cap
        guess = last + shift
    # Keep the answer on the price grid's 5 decimals and inside the scorer's (0, 10^7).
    guess = min(MAX_PRICE, max(MIN_PRICE, guess))
    # f"{x:.5f}" rather than round(), so a tiny value is written as 0.00001 and never as
    # 1e-05: the number is the same, but a plain decimal cannot trip a strict parser.
    return float(f"{guess:.5f}")


def case_price(doc):
    """The forecast for one case document, from its single btc-usdc market."""
    markets = doc.get("markets") or []
    if not markets:
        raise ValueError("case has no markets")
    market = markets[0]
    return forecast(market.get("prices") or [])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    in_dir = argv[0] if len(argv) > 0 else INPUT_DIR
    out_dir = argv[1] if len(argv) > 1 else OUTPUT_DIR

    try:
        names = sorted(n for n in os.listdir(in_dir) if n.endswith(".in"))
    except OSError as exc:
        print(f"cannot read {in_dir}: {exc}", file=sys.stderr)
        return 1

    os.makedirs(out_dir, exist_ok=True)
    for name in names:
        case_id = name[: -len(".in")]
        with open(os.path.join(in_dir, name), "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        # The case's own id wins over the file name: the output must name the case.
        case_id = doc.get("case") or case_id
        price = case_price(doc)
        # Written by hand rather than through json.dumps for the one number, so a tiny
        # forecast stays "0.00001" and is never "1e-05": valid either way, but a plain
        # decimal is what the format's example shows, and no parser can misread it.
        line = '{"forecasts":[{"case":%s,"price":%.5f}]}' % (json.dumps(case_id), price)
        with open(os.path.join(out_dir, case_id + ".out"), "w", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
