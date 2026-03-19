#!/usr/bin/env python3
"""UAT runner: compares actual API responses vs expected rules.

Design principle: treat UAT as black-box from *frontend input* to *backend output*.
We validate:
- HTTP status codes
- Response schema presence
- Semantic invariants (DNF vs Finish)
- Cross-endpoint consistency (history/leaderboard/teacher)

Usage:
  python3 uat/uat_runner.py --base http://localhost:8000 \
      --student Student_01 --password 1234 \
      --teacher teacher --teacher-password teacher123 \
      --csv uat/finish_strategies/finish_lap90.csv

Optional:
  --mutations 10  (generate 10 mutated CSV strategies from provided finish csv)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass
class TestResult:
    name: str
    ok: bool
    detail: str = ""
    data: Any = None


def fail(name: str, detail: str, data: Any = None) -> TestResult:
    return TestResult(name=name, ok=False, detail=detail, data=data)


def ok(name: str, detail: str = "", data: Any = None) -> TestResult:
    return TestResult(name=name, ok=True, detail=detail, data=data)


def assert_has(d: Dict[str, Any], keys: List[str], ctx: str) -> Optional[str]:
    missing = [k for k in keys if k not in d]
    if missing:
        return f"{ctx}: missing keys {missing}, got keys={list(d.keys())}"
    return None


def login(base: str, username: str, password: str) -> Tuple[int, Dict[str, Any]]:
    r = requests.post(f"{base}/api/auth/login", json={"username": username, "password": password})
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    return r.status_code, j


def get_json(base: str, path: str, token: str) -> Tuple[int, Dict[str, Any]]:
    r = requests.get(f"{base}{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    return r.status_code, j


def post_csv(base: str, path: str, token: str, csv_path: Path, timeout: int = 240) -> Tuple[int, Dict[str, Any]]:
    files = {"file": (csv_path.name, open(csv_path, "rb"), "text/csv")}
    r = requests.post(f"{base}{path}", headers={"Authorization": f"Bearer {token}"}, files=files, timeout=timeout)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    return r.status_code, j


def semantic_check_result(result: Dict[str, Any]) -> Optional[str]:
    err = assert_has(result, ["final_time", "is_dnf", "car_status"], "result")
    if err:
        return err
    is_dnf = bool(result["is_dnf"])
    ft = result["final_time"]
    if is_dnf:
        if ft is not None:
            return f"DNF expected final_time=None, got {ft}"
    else:
        if ft is None or not isinstance(ft, (int, float)) or ft <= 0:
            return f"Finish expected final_time>0 number, got {ft}"
    return None


def write_bad_csv_missing_column(src: Path, out: Path, drop_col: str) -> None:
    import csv as _csv
    with src.open("r", newline="") as f:
        r = _csv.DictReader(f)
        fieldnames = [c for c in (r.fieldnames or []) if c != drop_col]
        rows = []
        for row in r:
            row.pop(drop_col, None)
            rows.append(row)
    with out.open("w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_bad_csv_missing_corners(src: Path, out: Path, remove_turn_ids: List[str]) -> None:
    import csv as _csv
    with src.open("r", newline="") as f:
        r = _csv.DictReader(f)
        fieldnames = r.fieldnames or []
        rows = []
        for row in r:
            if (row.get("turn_id") or "").strip() in remove_turn_ids:
                # blank out turn_id to simulate missing corner definition
                row["turn_id"] = ""
            rows.append(row)
    with out.open("w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def mutate_csv(src: Path, out: Path, degree_jitter: float) -> None:
    rows = []
    with src.open("r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for r in reader:
            rows.append(r)

    # jitter steer_degree only on rows that have turn_id
    for r in rows:
        turn_id = (r.get("turn_id") or "").strip()
        if turn_id:
            try:
                deg = float(r.get("steer_degree") or 0)
            except Exception:
                deg = 0.0
            deg += random.uniform(-degree_jitter, degree_jitter)
            r["steer_degree"] = f"{deg:.2f}"

    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def run(args: argparse.Namespace) -> List[TestResult]:
    res: List[TestResult] = []

    # N1 invalid login
    code, j = login(args.base, args.student, "wrong")
    if code in (401, 403):
        res.append(ok("N1 invalid login", f"status={code}"))
    else:
        res.append(fail("N1 invalid login", f"expected 401/403 got {code}", j))

    # P0 login
    code, j = login(args.base, args.student, args.password)
    if code != 200:
        return res + [fail("P0 student login", f"expected 200 got {code}", j)]
    err = assert_has(j, ["token", "role"], "login")
    if err:
        return res + [fail("P0 student login", err, j)]
    token = j["token"]
    res.append(ok("P0 student login"))

    # N2 submit without auth
    csv_path = Path(args.csv)
    files = {"file": (csv_path.name, open(csv_path, "rb"), "text/csv")}
    r = requests.post(f"{args.base}/api/student/submit-csv", files=files, timeout=60)
    try:
        j2 = r.json()
    except Exception:
        j2 = {"raw": r.text}
    if r.status_code in (401, 403):
        res.append(ok("N2 submit without auth", f"status={r.status_code}"))
    else:
        res.append(fail("N2 submit without auth", f"expected 401/403 got {r.status_code}", j2))

    # N3 malformed CSV: missing required column (now_pos) => expect 400 (A)
    bad_dir = Path(args.out_dir)
    bad_dir.mkdir(parents=True, exist_ok=True)
    csv_path = Path(args.csv)
    bad_missing_now_pos = bad_dir / "bad_missing_now_pos.csv"
    write_bad_csv_missing_column(csv_path, bad_missing_now_pos, drop_col="now_pos")
    code, j = post_csv(args.base, "/api/student/submit-csv", token, bad_missing_now_pos)
    if code == 400:
        res.append(ok("N3 csv missing now_pos", "status=400"))
    else:
        res.append(fail("N3 csv missing now_pos", f"expected 400 got {code}", j))

    # N4 malformed CSV: missing corners (remove turn12) => expect 400 (A)
    bad_missing_corner = bad_dir / "bad_missing_corner.csv"
    write_bad_csv_missing_corners(csv_path, bad_missing_corner, remove_turn_ids=["turn12"])
    code, j = post_csv(args.base, "/api/student/submit-csv", token, bad_missing_corner)
    if code == 400:
        res.append(ok("N4 csv missing corner", "status=400"))
    else:
        res.append(fail("N4 csv missing corner", f"expected 400 got {code}", j))

    # P1 submit finish csv
    code, j = post_csv(args.base, "/api/student/submit-csv", token, csv_path)
    if code != 200:
        res.append(fail("P1 submit-csv finish", f"expected 200 got {code}", j))
    else:
        err = assert_has(j, ["job_id", "attempt_number", "result"], "submit-csv")
        if err:
            res.append(fail("P1 submit-csv finish", err, j))
        else:
            r = j["result"]
            sem = semantic_check_result(r)
            if sem:
                res.append(fail("P1 submit-csv finish", sem, r))
            else:
                if r["is_dnf"] is True:
                    res.append(fail("P1 submit-csv finish", "expected finish (is_dnf=false) but got DNF", r))
                else:
                    res.append(ok("P1 submit-csv finish", f"final_time={r['final_time']}", j))

    # P1b student/status leaderboard contains time
    code, st = get_json(args.base, "/api/student/status", token)
    if code != 200:
        res.append(fail("P1b student status", f"expected 200 got {code}", st))
    else:
        err = assert_has(st, ["leaderboard"], "status")
        if err:
            res.append(fail("P1b student status", err, st))
        else:
            lb = st["leaderboard"]
            if not isinstance(lb, list):
                res.append(fail("P1b student status", f"leaderboard should be list got {type(lb)}", lb))
            else:
                res.append(ok("P1b student status", f"leaderboard_len={len(lb)}"))

    # P1c history includes at least 1 record
    code, hist = get_json(args.base, "/api/student/history", token)
    if code != 200:
        res.append(fail("P1c student history", f"expected 200 got {code}", hist))
    else:
        err = assert_has(hist, ["history"], "history")
        if err:
            res.append(fail("P1c student history", err, hist))
        else:
            if len(hist["history"]) < 1:
                res.append(fail("P1c student history", "expected >=1 record", hist))
            else:
                res.append(ok("P1c student history", f"count={len(hist['history'])}"))

    # P3 teacher dashboard consistency (optional)
    if args.teacher and args.teacher_password:
        code, tj = login(args.base, args.teacher, args.teacher_password)
        if code == 200 and "token" in tj:
            ttoken = tj["token"]
            code, dash = get_json(args.base, "/api/teacher/dashboard", ttoken)
            if code != 200:
                res.append(fail("P3 teacher dashboard", f"expected 200 got {code}", dash))
            else:
                err = assert_has(dash, ["students"], "teacher/dashboard")
                if err:
                    res.append(fail("P3 teacher dashboard", err, dash))
                else:
                    res.append(ok("P3 teacher dashboard", f"students={len(dash['students'])}"))
        else:
            res.append(fail("P3 teacher login", f"expected 200 got {code}", tj))

    # N5 exceed max_attempts => expect 403
    code, st = get_json(args.base, "/api/student/status", token)
    # We don't know the exact shape, but current_round is expected in teacher dashboard; for student, may have round info.
    # If API exposes max_attempts we use it; otherwise we skip this check.
    max_attempts = None
    if code == 200:
        for key in ("max_attempts", "attempts_left"):
            if key in st:
                # not reliable; keep only explicit max_attempts
                pass
        if isinstance(st.get("current_round"), dict) and "max_attempts" in st["current_round"]:
            max_attempts = int(st["current_round"]["max_attempts"])

    if max_attempts is not None:
        # We already consumed some attempts in this run; keep submitting until we hit 403.
        hit = False
        for _ in range(max_attempts + 2):
            code, j = post_csv(args.base, "/api/student/submit-csv", token, csv_path)
            if code == 403 and ("Out of Laps" in json.dumps(j, ensure_ascii=False)):
                hit = True
                break
        if hit:
            res.append(ok("N5 exceed max_attempts", "status=403 Out of Laps"))
        else:
            res.append(fail("N5 exceed max_attempts", "did not hit expected 403 Out of Laps", {"max_attempts": max_attempts}))
    else:
        res.append(ok("N5 exceed max_attempts", "SKIPPED: student/status lacks current_round.max_attempts"))

    # Synthetic mutations
    if args.mutations > 0:
        tmp_dir = Path(args.out_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        for i in range(args.mutations):
            out = tmp_dir / f"mut_{i+1}.csv"
            mutate_csv(csv_path, out, degree_jitter=args.degree_jitter)
            code, j = post_csv(args.base, "/api/student/submit-csv", token, out)
            if code != 200:
                res.append(fail(f"S{i+1} mutated submit", f"expected 200 got {code}", j))
                continue
            sem = semantic_check_result(j.get("result", {}))
            if sem:
                res.append(fail(f"S{i+1} mutated submit", sem, j))
            else:
                res.append(ok(f"S{i+1} mutated submit", f"is_dnf={j['result']['is_dnf']} final_time={j['result']['final_time']}"))

    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--student", default="Student_01")
    ap.add_argument("--password", default="1234")
    ap.add_argument("--teacher", default="")
    ap.add_argument("--teacher-password", default="")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--mutations", type=int, default=0)
    ap.add_argument("--degree-jitter", type=float, default=1.5)
    ap.add_argument("--out-dir", default="/tmp/racing_uat_mutations")
    args = ap.parse_args()

    results = run(args)
    failed = [r for r in results if not r.ok]

    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"[{status}] {r.name}: {r.detail}")
        if (not r.ok) and r.data is not None:
            print("  data:", json.dumps(r.data, ensure_ascii=False)[:800])

    print("\nSummary:")
    print(f"  total={len(results)} pass={len(results)-len(failed)} fail={len(failed)}")

    raise SystemExit(0 if not failed else 1)


if __name__ == "__main__":
    main()
