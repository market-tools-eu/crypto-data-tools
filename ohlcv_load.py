#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ohlcv_load.py
#
# Чтение сохранённых котировок и пересборка в старший таймфрейм.
#
# Загрузчик терпим к формату: понимает и списки [время, o, h, l, c, v],
# и словари с ключами time/open/high/low/close, и вложенную структуру
# вида {"BTC/USDT": {"1m": [...]}}. Время принимается в секундах или
# миллисекундах — определяется автоматически.

import json


def _norm_candle(x):
    """Одна свеча -> dict(ts, o, h, l, c, v)."""
    if isinstance(x, dict):
        ts = x.get("ts", x.get("time", x.get("timestamp",
             x.get("t", x.get("open_time")))))
        o = x.get("o", x.get("open"))
        h = x.get("h", x.get("high"))
        l = x.get("l", x.get("low"))
        c = x.get("c", x.get("close"))
        v = x.get("v", x.get("volume", 0))
    else:
        ts, o, h, l, c = x[0], x[1], x[2], x[3], x[4]
        v = x[5] if len(x) > 5 else 0
    ts = int(ts)
    if ts < 10 ** 12:                 # секунды -> миллисекунды
        ts *= 1000
    return {"ts": ts, "o": float(o), "h": float(h), "l": float(l),
            "c": float(c), "v": float(v)}


def load_history(path):
    """Читает файл котировок. Возвращает {инструмент: [свечи]}."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], dict):
        raw = raw["data"]
    if not isinstance(raw, dict):
        raise SystemExit("Ожидался словарь {инструмент: свечи}.")

    out = {}
    for sym, val in raw.items():
        if isinstance(val, dict):
            for key in ("1m", "1", "m1", "candles", "klines"):
                if key in val:
                    val = val[key]
                    break
            else:
                val = list(val.values())[0]
        if not val:
            continue
        try:
            candles = [_norm_candle(x) for x in val]
        except Exception as e:
            print("  пропущено %s: %s" % (sym, e))
            continue
        candles.sort(key=lambda c: c["ts"])
        out[sym] = candles
    return out


def resample(candles, minutes):
    """Пересборка в старший таймфрейм. Неполный последний бар отбрасывается."""
    bucket = minutes * 60 * 1000
    out, cur = [], None
    for c in candles:
        b = c["ts"] - c["ts"] % bucket
        if cur is None or cur["ts"] != b:
            if cur:
                out.append(cur)
            cur = {"ts": b, "o": c["o"], "h": c["h"], "l": c["l"],
                   "c": c["c"], "v": c["v"]}
        else:
            cur["h"] = max(cur["h"], c["h"])
            cur["l"] = min(cur["l"], c["l"])
            cur["c"] = c["c"]
            cur["v"] += c["v"]
    if cur:
        out.append(cur)
    return out
