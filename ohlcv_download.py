#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ohlcv_download.py
#
# Выгрузка исторических свечей с биржи за произвольный период через ccxt.
#
# Отличия от простого fetch_ohlcv:
#   - период задаётся датами, а не «последние N дней»;
#   - постраничная догрузка с обработкой обрывов связи и повтором;
#   - таймфрейм выбирается аргументом: для дневных задач минутки не нужны,
#     год по 13 инструментам это 340 МБ в 1m против 6 МБ в 1h;
#   - компактное хранение: свечи списками, а не словарями — файл выходит
#     примерно вчетверо меньше.
#
# Запуск:
#   python ohlcv_download.py 2025-01-01 2025-04-01
#   python ohlcv_download.py 2025-01-01 2025-04-01 tf=1h out=data.json
#   python ohlcv_download.py 2025-01-01 2025-04-01 BTC/USDT ETH/USDT

import json
import sys
import time
from datetime import datetime, timezone

import ccxt

DEFAULT_OUT = "ohlcv.json"

# Инструменты по умолчанию.
SYMBOLS = [
    "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "NEAR/USDT", "OP/USDT",
]

FETCH_LIMIT = 1000


def to_ms(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def make_exchange():
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "future", "adjustForTimeDifference": True},
    })
    exchange.load_markets()
    return exchange


def fetch_candles(exchange, symbol, start_ms, end_ms, tf="1m"):
    step = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
            "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}[tf]
    since = start_ms
    out, seen = [], set()

    while since < end_ms:
        try:
            raw = exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=FETCH_LIMIT)
        except Exception as error:
            print("    ошибка запроса (%s) — пауза 5с и ещё попытка" % error)
            time.sleep(5)
            continue

        if not raw:
            break

        for ts, o, h, l, c, v in raw:
            if ts in seen or ts >= end_ms:
                continue
            seen.add(ts)
            out.append([int(ts), float(o), float(h), float(l), float(c),
                        float(v) if v is not None else 0.0])

        last = raw[-1][0]
        if last <= since:
            break
        since = last + step
        print("    %d свечей..." % len(out), end="\r")

    out.sort(key=lambda c: c[0])
    return out


def main():
    args = sys.argv[1:]
    dates = [a for a in args if len(a) == 10 and a.count("-") == 2]
    if len(dates) < 2:
        raise SystemExit("Нужны две даты: python ohlcv_download.py 2026-03-01 2026-04-01")

    start_ms, end_ms = to_ms(dates[0]), to_ms(dates[1])
    if end_ms <= start_ms:
        raise SystemExit("Вторая дата должна быть позже первой.")

    out_file = DEFAULT_OUT
    tf = "1m"
    for a in args:
        if a.startswith("out="):
            out_file = a[4:]
        if a.startswith("tf="):
            tf = a[3:]
    if tf not in ("1m", "5m", "15m", "1h", "4h", "1d"):
        raise SystemExit("tf должен быть одним из: 1m, 5m, 15m, 1h, 4h, 1d")

    wanted = [a for a in args if "/" in a] or SYMBOLS

    days = (end_ms - start_ms) / 86_400_000
    print("период: %s → %s (%.0f дней), монет: %d, ТФ: %s, файл: %s\n"
          % (dates[0], dates[1], days, len(wanted), tf, out_file))

    exchange = make_exchange()
    data = {}

    for symbol in wanted:
        print("%s: качаю %s..." % (symbol, tf))
        one_m = fetch_candles(exchange, symbol, start_ms, end_ms, tf)
        if not one_m:
            print("    пусто — пропускаю (монеты могло не быть на бирже в этот период)")
            continue
        data[symbol] = one_m
        first = datetime.fromtimestamp(one_m[0][0] / 1000, timezone.utc).strftime("%Y-%m-%d")
        last = datetime.fromtimestamp(one_m[-1][0] / 1000, timezone.utc).strftime("%Y-%m-%d")
        print("    готово: %d свечей, %s → %s" % (len(one_m), first, last))

    if not data:
        raise SystemExit("Ничего не скачалось — проверь даты и названия монет.")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    import os
    size_mb = round(os.path.getsize(out_file) / 1024 / 1024, 1)
    print("\nСохранено в %s (%s МБ), монет: %d" % (out_file, size_mb, len(data)))
    print("Теперь: python backtest_fvg.py %s" % out_file)


if __name__ == "__main__":
    main()
