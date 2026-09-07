#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# event_logger.py
#
# Пассивный журнал событий с отслеживанием исходов.
#
# Записывает событие в CSV в момент, когда оно обнаружено, и на
# последующих проходах дописывает, чем оно закончилось. Полезно, когда
# нужно честно накопить статистику по живым данным: запись делается до
# того, как исход известен, поэтому подогнать её невозможно.
#
# Особенности:
#   - не вмешивается в работу вызывающей программы: весь вызов обёрнут
#     так, что любая внутренняя ошибка гасится;
#   - дедупликация: одно открытое событие на объект;
#   - сводка по накопленному одной командой.
#
# Подключение:
#     import event_logger
#     event_logger.log_event(key="BTC/USDT", side="UP",
#                            entry=100.0, stop=98.0, target=104.0,
#                            note="описание")
#     event_logger.update_outcomes("BTC/USDT", low=97.5, high=101.0)
#
# Сводка:
#     python event_logger.py

import csv
import os
from datetime import datetime, timezone

LOG_FILE = "events_log.csv"

FIELDS = ["время", "объект", "сторона", "вход", "стоп", "цель",
          "стоп_проц", "примечание", "исход", "время_исхода", "R"]

TARGET_R = 2.0            # во сколько R оценивается достигнутая цель


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _read_all():
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _write_all(rows):
    with open(LOG_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _already_open(rows, key):
    for r in rows:
        if r["объект"] == key and r["исход"] == "OPEN":
            return True
    return False


def update_outcomes(key, low, high):
    """Отмечает исход открытых записей по фактическому ходу цены."""
    try:
        rows = _read_all()
        changed = False
        for r in rows:
            if r["объект"] != key or r["исход"] != "OPEN":
                continue
            try:
                entry = float(r["вход"])
                stop = float(r["стоп"])
                target = float(r["цель"])
            except (ValueError, KeyError):
                continue
            long_side = r["сторона"] == "UP"
            hit_stop = low <= stop if long_side else high >= stop
            hit_tp = high >= target if long_side else low <= target
            if hit_stop:
                r["исход"], r["R"] = "STOP", "-1.00"
            elif hit_tp:
                r["исход"], r["R"] = "TARGET", "%.2f" % TARGET_R
            else:
                continue
            r["время_исхода"] = _now()
            changed = True
        if changed:
            _write_all(rows)
    except Exception:
        pass


def log_event(key, side, entry, stop, target, note=""):
    """Записывает новое событие, если по этому объекту нет открытого."""
    try:
        rows = _read_all()
        if _already_open(rows, key):
            return
        entry, stop, target = float(entry), float(stop), float(target)
        risk = abs(entry - stop)
        rows.append({
            "время": _now(), "объект": key, "сторона": side,
            "вход": "%.8g" % entry, "стоп": "%.8g" % stop,
            "цель": "%.8g" % target,
            "стоп_проц": "%.2f" % (risk / entry * 100) if entry else "",
            "примечание": note,
            "исход": "OPEN", "время_исхода": "", "R": "",
        })
        _write_all(rows)
    except Exception:
        pass


def summary():
    """Сводка по накопленному."""
    rows = _read_all()
    if not rows:
        print("Записей пока нет. Файл: %s" % LOG_FILE)
        return
    done = [r for r in rows if r["исход"] in ("STOP", "TARGET")]
    print("всего записей: %d, закрыто %d, открыто %d\n"
          % (len(rows), len(done), len(rows) - len(done)))
    if not done:
        return
    tot = sum(float(r["R"]) for r in done if r["R"])
    wins = sum(1 for r in done if r["исход"] == "TARGET")
    print("доля достигнутых целей: %.1f%%" % (wins / len(done) * 100))
    print("суммарно: %+.2fR | в среднем: %+.3fR" % (tot, tot / len(done)))
    for d in ("UP", "DOWN"):
        dd = [r for r in done if r["сторона"] == d]
        if dd:
            t = sum(float(r["R"]) for r in dd if r["R"])
            print("  %-5s %d записей | %+.2fR" % (d, len(dd), t))


if __name__ == "__main__":
    summary()
