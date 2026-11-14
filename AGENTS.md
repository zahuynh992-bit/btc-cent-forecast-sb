# btc-cent-forecast-sb

Python 3.13, standard library only. Entry for make.fun bounty `btc-cent-forecast-01`: read the
4,320 one-minute BTC/USDC closes up to a checkpoint, write the price 240 minutes later.
Scored as mean absolute error in cents (lower better); persistence (last close) is the house
baseline and a prize needs a score strictly below it.

## Status

Updated 2026-11-15. Entrypoint works and is committed (`c5ac6f1`). Open: nothing needed to
submit; the model's margin over the suggested baseline is small and is documented in
`main.py`'s docstring.

## Run

    MAKEFUN_INPUT_DIR=/workspace/makefun/kits/btc-cent-forecast-01-kit/input \
    MAKEFUN_OUTPUT_DIR=/tmp/sb-out python3 main.py

    python3 backtest.py    # rolling-origin comparison of every model, ~1 min

`main.py` reads every `*.in` in the input dir and writes `<case>.out` per case; the grader runs
it one case at a time with only that case in `/input` and caps a run at 8 s (it takes ~30 ms).

## Map

- `main.py`: `clean()` drops non-finite/non-positive prices, `forecast()` is the model,
  `main()` walks the case files. Constants at the top: `PULL=0.3`, `SPAN=360`, `CAP=0.02`.
- `backtest.py`: stitches the six overlapping practice cases into one 5,520-minute series by
  their `at` timestamps, then scores models at origins every 15 minutes (4,320 back, +240
  forward). Reports MAE overall and on the first and second half of origins.

## Decisions

- Model: `last + 0.3 * (EMA360 - last)`, shift capped at ±2% of last. Chosen because it was
  the only candidate of the swept grid that beat the suggested `0.2/EMA720` baseline on the
  overall figure and on both halves of the origins (49,447 vs 49,600 cents over 65 origins).
- Practice: only 5,520 minutes exist, so there are ~5 independent 4-hour windows; treat any
  sub-1% difference between models as noise, not signal.
