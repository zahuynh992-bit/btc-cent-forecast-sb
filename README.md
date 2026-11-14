[![make.fun · btc-cent-forecast-01](https://make.fun/badge/btc-cent-forecast-01.svg)](https://make.fun/bounty/btc-cent-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=btc-cent-forecast-01)
[![rank](https://make.fun/badge/btc-cent-forecast-01/zahuynh992-bit/btc-cent-forecast-sb/rank.svg)](https://make.fun/bounty/btc-cent-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-cent-forecast-01)
[![reward](https://make.fun/badge/btc-cent-forecast-01/zahuynh992-bit/btc-cent-forecast-sb/reward.svg)](https://make.fun/bounty/btc-cent-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=btc-cent-forecast-01)

Entry for the make.fun bounty [btc-cent-forecast-01](https://make.fun/bounty/btc-cent-forecast-01).

# btc-cent-forecast-sb

An entry for the make.fun bounty `btc-cent-forecast-01`: forecast Bitcoin's US-dollar price
240 minutes after a checkpoint, from the 72 hours of one-minute closes leading up to it.

It is a damped mean-reversion forecaster: the guess is the last close plus 30% of its gap to
a 360-minute exponential moving average, with that shift capped at 2% of the last close. The
score is the mean absolute error in cents, so the target is the middle of the distribution of
where the price lands, not a bet on direction.

## Run it

    MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py

Each `<id>.in` in the input directory yields `<id>.out` holding
`{"forecasts":[{"case":"<id>","price":<number>}]}`. Python 3.13, standard library only, no
network. It runs a case in about 30 ms.

## Backtest

    python3 backtest.py

The six practice cases overlap, so `backtest.py` stitches them into one continuous minute
series and scores each model at origins every 15 minutes: 4,320 minutes of history in, the
close 240 minutes later out. It reports mean absolute error in cents for persistence (the
house baseline), the suggested `0.2/EMA720` model, and a grid of alternatives, overall and on
the first and second half of the origins separately.

`--input <dir>` points it at another directory of case files.

## Licence

MIT, see `LICENSE`.
