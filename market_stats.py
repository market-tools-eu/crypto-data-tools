#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# market_stats.py
#
# Три замера распределений по историческим котировкам.
# Только частоты, без каких-либо торговых рекомендаций.
#
#   1. Сезонность: в какие часы UTC и в какие дни недели чаще
#      формируется максимум и минимум дня.
#   2. Серии: после N зелёных свечей подряд — какова вероятность,
#      что следующая красная (возврат к среднему).
#   3. Пробой вчерашних High/Low: если цена прокалывает вчерашний
#      максимум, как часто она закрепляется выше, а как часто
#      возвращается внутрь предыдущего диапазона.
#
# Заглядывания вперёд нет: каждый замер смотрит вперёд только от
# закрытой свечи и только на то, что случилось после неё.
#
# Запуск:
#   python market_stats.py data.json
#   python market_stats.py data.json streak_tf=4h
#   python market_stats.py data1.json data2.json

import sys
from collections import defaultdict

import ohlcv_load as L

P = {
    "streak_tf": "4h",     # ТФ для подсчёта серий: 1h | 4h | 1d
    "max_streak": 5,       # до какой длины серии считаем
    "break_confirm": 2,    # свечей на подтверждение пробоя (часовых)
    "min_count": 30,       # реже этого не показываем
}

TF_MIN = {"1h": 60, "4h": 240, "1d": 1440}
DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def hour_of(ts):
    return int(ts // 3600000) % 24


def dow_of(ts):
    return int(ts // 86400000 + 4) % 7      # 1970-01-01 — четверг


# ------------------------------------------------- 1. сезонность


def seasonality(h1, acc):
    """Когда формируется максимум и минимум дня."""
    day = defaultdict(list)
    for c in h1:
        day[c["ts"] // 86400000].append(c)

    for d, bars in sorted(day.items()):
        if len(bars) < 20:
            continue                        # неполные сутки не считаем
        hi = max(bars, key=lambda x: x["h"])
        lo = min(bars, key=lambda x: x["l"])
        acc["hi_hour"][hour_of(hi["ts"])] += 1
        acc["lo_hour"][hour_of(lo["ts"])] += 1
        acc["days"] += 1

        # каким вышел день целиком
        ch = (bars[-1]["c"] - bars[0]["o"]) / bars[0]["o"] * 100 if bars[0]["o"] else 0
        w = DOW[dow_of(bars[0]["ts"])]
        acc["dow_n"][w] += 1
        if ch > 0:
            acc["dow_up"][w] += 1
        acc["dow_move"][w] += abs(ch)


# ------------------------------------------------- 2. серии


def streaks(c, acc, p):
    """После N одинаковых свечей подряд — какая следующая."""
    run, run_dir = 0, None
    for i in range(len(c) - 1):
        up = c[i]["c"] > c[i]["o"]
        d = "up" if up else "down"
        if d == run_dir:
            run += 1
        else:
            run_dir, run = d, 1
        if run < 1 or run > p["max_streak"]:
            continue
        nxt_up = c[i + 1]["c"] > c[i + 1]["o"]
        key = (run_dir, run)
        acc["streak_n"][key] += 1
        if nxt_up != up:                    # следующая противоположная
            acc["streak_rev"][key] += 1


# ------------------------------------------------- 3. пробой вчерашних уровней


def prev_day_breaks(h1, acc, p):
    """
    Истинный пробой или снятие ликвидности.
    Истинный  — после прокола свеча ЗАКРЫЛАСЬ за уровнем и следующие
                break_confirm свечей тоже закрылись за ним.
    Ложный    — цена вернулась внутрь вчерашнего диапазона.
    """
    day = defaultdict(list)
    for c in h1:
        day[c["ts"] // 86400000].append(c)
    keys = sorted(day)

    for n in range(1, len(keys)):
        prev, cur = day[keys[n - 1]], day[keys[n]]
        if len(prev) < 20 or len(cur) < 10:
            continue
        ph = max(x["h"] for x in prev)
        pl = min(x["l"] for x in prev)

        # --- пробой вверх
        for i, c in enumerate(cur):
            if c["h"] <= ph:
                continue
            acc["up_break"] += 1
            tail = cur[i:i + p["break_confirm"] + 1]
            if len(tail) > p["break_confirm"] and all(x["c"] > ph for x in tail):
                acc["up_true"] += 1
            else:
                acc["up_false"] += 1
                acc["up_false_hour"][hour_of(c["ts"])] += 1
            break

        # --- пробой вниз
        for i, c in enumerate(cur):
            if c["l"] >= pl:
                continue
            acc["dn_break"] += 1
            tail = cur[i:i + p["break_confirm"] + 1]
            if len(tail) > p["break_confirm"] and all(x["c"] < pl for x in tail):
                acc["dn_true"] += 1
            else:
                acc["dn_false"] += 1
                acc["dn_false_hour"][hour_of(c["ts"])] += 1
            break

        acc["day_pairs"] += 1


# ------------------------------------------------- отчёт


def main():
    args = sys.argv[1:]
    files = [a for a in args if a.endswith(".json") and "=" not in a]
    if not files:
        raise SystemExit("Укажи файл: python market_stats.py data.json")
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            if k in P:
                P[k] = v if isinstance(P[k], str) else type(P[k])(v)

    acc = {
        "hi_hour": defaultdict(int), "lo_hour": defaultdict(int), "days": 0,
        "dow_n": defaultdict(int), "dow_up": defaultdict(int),
        "dow_move": defaultdict(float),
        "streak_n": defaultdict(int), "streak_rev": defaultdict(int),
        "up_break": 0, "up_true": 0, "up_false": 0,
        "dn_break": 0, "dn_true": 0, "dn_false": 0,
        "up_false_hour": defaultdict(int), "dn_false_hour": defaultdict(int),
        "day_pairs": 0,
    }

    coins = 0
    for path in files:
        hist = L.load_history(path)
        for sym, m1 in sorted(hist.items()):
            h1 = L.resample(m1, 60)
            if len(h1) < 200:
                continue
            coins += 1
            seasonality(h1, acc)
            prev_day_breaks(h1, acc, P)
            streaks(L.resample(m1, TF_MIN[P["streak_tf"]]), acc, P)

    if not acc["days"]:
        print("Данных не хватило.")
        return

    print("монет: %d | суток: %d\n" % (coins, acc["days"]))

    # --- 1
    print("=" * 58)
    print("1. КОГДА ФОРМИРУЕТСЯ МАКСИМУМ И МИНИМУМ ДНЯ (UTC)")
    print("=" * 58)
    print("%-8s %10s %10s" % ("час", "максимум", "минимум"))
    base = 100 / 24
    for h in range(24):
        ph = acc["hi_hour"][h] / acc["days"] * 100
        pl = acc["lo_hour"][h] / acc["days"] * 100
        mark = ""
        if ph > base * 1.3 or pl > base * 1.3:
            mark = "  <--"
        print("%02d:00   %9.1f%% %9.1f%%%s" % (h, ph, pl, mark))
    print("(если бы равномерно — по %.1f%% на час)" % base)

    print("\n%-6s %8s %9s %10s" % ("день", "суток", "рост", "ср. ход"))
    for w in DOW:
        n = acc["dow_n"][w]
        if not n:
            continue
        print("%-6s %8d %8.1f%% %9.2f%%"
              % (w, n, acc["dow_up"][w] / n * 100, acc["dow_move"][w] / n))

    # --- 2
    print("\n" + "=" * 58)
    print("2. СЕРИИ СВЕЧЕЙ НА %s: развернётся ли следующая" % P["streak_tf"].upper())
    print("=" * 58)
    print("%-22s %8s %12s" % ("серия", "раз", "разворот"))
    for d in ("up", "down"):
        for n in range(1, P["max_streak"] + 1):
            cnt = acc["streak_n"][(d, n)]
            if cnt < P["min_count"]:
                continue
            rev = acc["streak_rev"][(d, n)] / cnt * 100
            name = "%d %s подряд" % (n, "зелёных" if d == "up" else "красных")
            print("%-22s %8d %11.1f%%" % (name, cnt, rev))
    print("(50%% = серии ничего не значат)")

    # --- 3
    print("\n" + "=" * 58)
    print("3. ПРОБОЙ ВЧЕРАШНИХ HIGH/LOW")
    print("=" * 58)
    for nm, br, tr, fl in (("вверх", "up_break", "up_true", "up_false"),
                           ("вниз", "dn_break", "dn_true", "dn_false")):
        n = acc[br]
        if not n:
            continue
        print("%s: проколов %d из %d дней (%.0f%%)"
              % (nm, n, acc["day_pairs"], n / acc["day_pairs"] * 100))
        print("   истинных %d (%.1f%%) | ложных %d (%.1f%%)"
              % (acc[tr], acc[tr] / n * 100, acc[fl], acc[fl] / n * 100))

    tot_f = acc["up_false"] + acc["dn_false"]
    tot_b = acc["up_break"] + acc["dn_break"]
    if tot_b:
        print("\nвсего ложных пробоев: %.1f%%" % (tot_f / tot_b * 100))
        print("50%% означало бы, что пробои и возвраты равновероятны.")

    hrs = sorted(((v, k) for k, v in acc["up_false_hour"].items()), reverse=True)[:5]
    if hrs:
        print("\nчасы UTC с самыми частыми ложными пробоями вверх:")
        print("   " + ", ".join("%02d:00 (%d)" % (k, v) for v, k in hrs))


if __name__ == "__main__":
    main()
