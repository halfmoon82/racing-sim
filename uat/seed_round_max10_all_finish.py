#!/usr/bin/env python3
"""Seed a new active round (max_attempts=10) and submit strategies so every student has >=1 finish.

- Uses teacher_01 to create a new round.
- For each Student_01..Student_10, submits CSV strategies derived from finish dataset.
- Retries with different finish_lap CSVs until a non-DNF result appears or attempts are exhausted.
- Does NOT stop the round at the end.

Run:
  python3 uat/seed_round_max10_all_finish.py
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import List, Tuple

import requests

BASE = os.environ.get("BASE_URL", "http://localhost:8000")
TEACHER_USER = os.environ.get("TEACHER_USER", "teacher_01")
TEACHER_PASS = os.environ.get("TEACHER_PASS", "1234")
STUDENT_PASS = os.environ.get("STUDENT_PASS", "1234")

FINISH_DIR = Path(__file__).resolve().parent / "finish_strategies"
FINISH_CSVS = sorted(FINISH_DIR.glob("finish_lap*.csv"))

if not FINISH_CSVS:
    raise SystemExit(f"No finish strategies found under {FINISH_DIR}")


def login(username: str, password: str) -> Tuple[int, dict]:
    r = requests.post(f"{BASE}/api/auth/login", json={"username": username, "password": password}, timeout=30)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    return r.status_code, j


def logout(token: str) -> None:
    try:
        requests.post(f"{BASE}/api/auth/logout", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    except Exception:
        pass


def teacher_create_round(token: str, name: str, max_attempts: int = 10) -> dict:
    r = requests.post(
        f"{BASE}/api/teacher/rounds",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "max_attempts": max_attempts},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def teacher_dashboard(token: str) -> dict:
    r = requests.get(f"{BASE}/api/teacher/dashboard", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def submit_csv(token: str, csv_path: Path) -> Tuple[int, dict]:
    files = {"file": (csv_path.name, open(csv_path, "rb"), "text/csv")}
    r = requests.post(
        f"{BASE}/api/student/submit-csv",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        timeout=240,
    )
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    return r.status_code, j


def main():
    print("== create round max_attempts=10 ==")

    code, j = login(TEACHER_USER, TEACHER_PASS)
    if code != 200:
        raise SystemExit(f"Teacher login failed: {code} {j}")
    ttoken = j["token"]

    dash_before = teacher_dashboard(ttoken)
    next_no = int(dash_before["current_round"]["number"]) + 1 if dash_before.get("current_round") else 1
    name = f"Round {next_no}"

    created = teacher_create_round(ttoken, name=name, max_attempts=10)
    dash_after = teacher_dashboard(ttoken)
    round_id = dash_after["current_round"]["id"]
    print(f"Round created: id={round_id}, number={dash_after['current_round']['number']}, max_attempts={dash_after['current_round']['max_attempts']}")

    # seed students
    students = [f"Student_{i:02d}" for i in range(1, 11)]
    results = {}

    for s in students:
        print(f"\n== {s} ==")
        code, j = login(s, STUDENT_PASS)
        if code != 200:
            results[s] = {"ok": False, "reason": f"login failed {code}", "detail": j}
            print("  login FAIL", code, j)
            continue
        token = j["token"]

        # Try up to 10 submissions to get a finish
        got_finish = False
        attempts = 0
        pool = FINISH_CSVS.copy()
        random.shuffle(pool)
        while attempts < 10 and pool:
            csvp = pool.pop(0)
            attempts += 1
            scode, sj = submit_csv(token, csvp)
            if scode != 200:
                print(f"  submit {attempts} FAIL status={scode} csv={csvp.name} resp={str(sj)[:200]}")
                continue
            r = sj.get("result", {})
            is_dnf = bool(r.get("is_dnf"))
            ft = r.get("final_time")
            print(f"  submit {attempts} ok csv={csvp.name} is_dnf={is_dnf} final_time={ft}")
            if not is_dnf and ft is not None:
                got_finish = True
                break

        results[s] = {"ok": got_finish, "attempts_used": attempts}
        # logout to free cockpit/session
        logout(token)

    print("\n== summary ==")
    all_ok = True
    for s, r in results.items():
        mark = "OK" if r.get("ok") else "FAIL"
        if not r.get("ok"):
            all_ok = False
        print(f"{s}: {mark} attempts_used={r.get('attempts_used')}")

    print("\nNOTE: round left ACTIVE (not stopped).")
    raise SystemExit(0 if all_ok else 2)


if __name__ == "__main__":
    main()
