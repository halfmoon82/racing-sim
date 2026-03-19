"""Concurrency & correctness test for racing-sim.

What it tests
- 4 students, each 10 submissions (total 40)
- concurrent submissions across students (thread pool)
- per-submission response contains 5-run best-of fields
- DB record matches returned job_id, and stored strategy_data matches what we sent
- Results are written to ~/Desktop/AI创新/测试结果/<run_id>/

Notes
- Uses localhost backend http://127.0.0.1:8000
- Assumes test-phase passwords are 1234. Script will force-reset selected students to 1234 in SQLite and clear Redis/DB sessions for idempotency.
"""

from __future__ import annotations

import concurrent.futures as cf
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import time
from typing import Any, Dict, List, Tuple

import requests

BASE = "http://127.0.0.1:8000"
DB_PATH = Path(__file__).resolve().parents[1] / "database" / "racing_sim.db"
OUT_ROOT = Path.home() / "Desktop" / "AI创新" / "测试结果"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def normalize_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize segments to match backend/Pydantic shape.

    Backend's Pydantic model includes optional keys (turn_id/steer_LR/steer_degree) that
    get materialized as null in DB even if omitted by the client. For a fair
    'strategy_match' check we normalize both sides to the same keyset.
    """
    out: List[Dict[str, Any]] = []
    for seg in segments:
        out.append(
            {
                "now_pos": float(seg.get("now_pos")),
                "strategy": seg.get("strategy"),
                "is_corner": bool(seg.get("is_corner", False)),
                "turn_id": seg.get("turn_id"),
                "steer_LR": seg.get("steer_LR"),
                "steer_degree": seg.get("steer_degree"),
            }
        )
    return out


def canonical_strategy_json(segments: List[Dict[str, Any]]) -> str:
    # stable representation for hashing/comparison
    norm = normalize_segments(segments)
    return json.dumps(norm, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def log(msg: str):
    print(msg, flush=True)


@dataclasses.dataclass
class Student:
    username: str
    user_id: int
    token: str


def http_post(path: str, payload: dict | None = None, token: str | None = None, timeout: int = 120):
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.post(f"{BASE}{path}", json=payload, headers=h, timeout=timeout)


def http_get(path: str, token: str | None = None, timeout: int = 30):
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE}{path}", headers=h, timeout=timeout)


def force_reset_students_to_1234(usernames: List[str]) -> Dict[str, int]:
    """Set password_hash to sha256(1234) for target students; return username->id"""
    pw_hash = sha256("1234")
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "SELECT id, username FROM users WHERE role='student' AND username IN (%s)" % (",".join(["?"] * len(usernames))),
        tuple(usernames),
    )
    rows = cur.fetchall()
    uid_map = {u: i for i, u in rows}
    if len(uid_map) != len(usernames):
        missing = [u for u in usernames if u not in uid_map]
        raise RuntimeError(f"Missing students in DB: {missing}")

    cur.execute(
        "UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE username IN (%s)" % (",".join(["?"] * len(usernames))),
        (pw_hash, *usernames),
    )

    # deactivate existing sessions
    cur.execute(
        "UPDATE sessions SET is_active=0 WHERE user_id IN (%s)" % (",".join(["?"] * len(uid_map))),
        tuple(uid_map.values()),
    )

    con.commit()
    con.close()

    # clear redis session locks
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        for uid in uid_map.values():
            r.delete(f"user_session:{uid}")
    except Exception as e:
        log(f"[WARN] Redis cleanup skipped: {e}")

    return uid_map


def force_clear_teacher_sessions(username: str = "teacher_01") -> int:
    """Clear teacher sessions to avoid 'Maximum sessions reached'. Return teacher user_id."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id FROM users WHERE role='teacher' AND username=?", (username,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Teacher not found in DB: {username}")
    teacher_id = int(row[0])

    cur.execute("UPDATE sessions SET is_active=0 WHERE user_id=?", (teacher_id,))
    con.commit()
    con.close()

    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        r.delete(f"user_sessions:{teacher_id}")
        # some earlier versions used user_session:<uid> even for teacher
        r.delete(f"user_session:{teacher_id}")
    except Exception as e:
        log(f"[WARN] Redis cleanup skipped for teacher: {e}")

    return teacher_id


def admin_login() -> str:
    r = http_post("/api/auth/login", {"username": "admin", "password": "admin123"}, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"admin_login failed: {r.status_code} {r.text}")
    return r.json()["token"]


def teacher_login() -> str:
    r = http_post("/api/auth/login", {"username": "teacher_01", "password": "1234"}, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"teacher_login failed: {r.status_code} {r.text}")
    return r.json()["token"]


def teacher_create_round(token: str, max_attempts: int = 20) -> int:
    r = http_post(
        "/api/teacher/rounds",
        {"name": "Round Concurrency Test", "max_attempts": max_attempts},
        token=token,
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"create_round failed: {r.status_code} {r.text}")

    # fetch dashboard to get round id
    d = http_get("/api/teacher/dashboard", token=token, timeout=10)
    if d.status_code != 200:
        raise RuntimeError(f"teacher_dashboard failed: {d.status_code} {d.text}")
    rid = d.json().get("current_round", {}).get("id")
    if not rid:
        raise RuntimeError("round_id not found")
    return int(rid)


def student_login(username: str) -> str:
    r = http_post("/api/auth/login", {"username": username, "password": "1234"}, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"{username} login failed: {r.status_code} {r.text}")
    return r.json()["token"]


def build_strategy(seed: int) -> List[Dict[str, Any]]:
    """Build a valid full-lap strategy reaching now_pos=2820.

    Must satisfy strict validation:
    - contains exactly 9 corner segments with turn_id sequence:
      turn1, turn2, turn4, turn6, turn7, turn8, turn10, turn12, turn13
    - each corner has steer_LR (L/R) + steer_degree
    - positions strictly increasing and final reaches 2820

    We vary strategies + steering slightly per seed to create distinguishable payloads.
    """
    random.seed(seed)

    corners = ['turn1', 'turn2', 'turn4', 'turn6', 'turn7', 'turn8', 'turn10', 'turn12', 'turn13']
    # pick 9 increasing corner positions (roughly spread across the lap)
    # keep some room at the end for finish
    corner_positions = [
        451.0,
        620.0,
        820.0,
        1050.0,
        1320.0,
        1580.0,
        1880.0,
        2240.0,
        2550.0,
    ]

    segs: List[Dict[str, Any]] = []
    # initial straight
    segs.append({"now_pos": 0.0, "strategy": "a", "is_corner": False})

    for pos, tid in zip(corner_positions, corners):
        # a straight segment before each corner (optional, helps variety)
        prev = segs[-1]["now_pos"]
        straight_pos = max(prev + 120.0, pos - 60.0)
        if straight_pos < pos:
            segs.append({
                "now_pos": float(straight_pos),
                "strategy": random.choice(["a", "b", "c"]),
                "is_corner": False,
            })

        # corner segment
        segs.append({
            "now_pos": float(pos),
            "strategy": random.choice(["a", "b", "c"]),
            "is_corner": True,
            "turn_id": tid,
            "steer_LR": random.choice(["L", "R"]),
            # keep degrees in a plausible range, but vary per seed
            "steer_degree": float(random.choice([5, 8, 10, 12, 15, 18, 20, 25, 30])),
        })

    # finish segments (non-corner)
    last = segs[-1]["now_pos"]
    if last < 2820.0:
        segs.append({"now_pos": float(min(last + 180.0, 2810.0)), "strategy": "a", "is_corner": False})
    segs.append({"now_pos": 2820.0, "strategy": "a", "is_corner": False})

    # ensure strictly increasing
    cleaned: List[Dict[str, Any]] = []
    prev = -1.0
    for s in segs:
        if s["now_pos"] <= prev:
            continue
        cleaned.append(s)
        prev = s["now_pos"]

    return cleaned


def db_get_record_by_job(job_id: str) -> sqlite3.Row | None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM records WHERE job_id=?", (job_id,))
    row = cur.fetchone()
    con.close()
    return row


def validate_5run_bestof(result: Dict[str, Any]) -> Tuple[bool, str]:
    # expected keys
    for k in ("best_run", "final_time", "all_runs", "is_dnf"):
        if k not in result:
            return False, f"missing {k}"
    all_runs = result.get("all_runs")
    if not isinstance(all_runs, list) or len(all_runs) != 5:
        return False, f"all_runs len != 5 ({type(all_runs)} {len(all_runs) if isinstance(all_runs,list) else 'n/a'})"

    # compute min time among non-dnf
    times = [r.get("time") for r in all_runs if r and not r.get("is_dnf") and isinstance(r.get("time"), (int, float))]
    if times:
        mn = min(times)
        ft = result.get("final_time")
        if not isinstance(ft, (int, float)):
            return False, "final_time not numeric"
        if abs(ft - mn) > 1e-6:
            return False, f"final_time != min(all_runs) ({ft} vs {mn})"
    return True, "ok"


def submit_once(student: Student, idx: int, out_dir: Path) -> Dict[str, Any]:
    seed = hash((student.username, idx, time.time_ns())) & 0xFFFFFFFF
    segments = build_strategy(seed)
    strategy_json = canonical_strategy_json(segments)
    strategy_hash = sha256(strategy_json)

    t0 = time.time()
    r = http_post("/api/student/submit", {"segments": segments}, token=student.token, timeout=180)
    dt = time.time() - t0

    entry: Dict[str, Any] = {
        "student": student.username,
        "user_id": student.user_id,
        "submission_idx": idx,
        "http_status": r.status_code,
        "elapsed_sec": round(dt, 3),
        "strategy_hash": strategy_hash,
    }

    if r.status_code != 200:
        entry["error_text"] = r.text
        return entry

    data = r.json()
    job_id = data.get("job_id")
    entry["job_id"] = job_id
    entry["attempt_number"] = data.get("attempt_number")

    result = data.get("result")
    entry["result"] = result

    # validate best-of-5 structure
    ok5, why5 = validate_5run_bestof(result or {})
    entry["bestof5_ok"] = ok5
    entry["bestof5_reason"] = why5

    # DB match
    row = db_get_record_by_job(job_id)
    if not row:
        entry["db_ok"] = False
        entry["db_reason"] = "record not found"
        return entry

    entry["db_ok"] = True
    entry["db_user_id"] = row["user_id"]
    entry["db_round_id"] = row["round_id"]
    entry["db_result_time"] = row["result_time"]

    # strategy_data match
    db_strategy_raw = row["strategy_data"]
    try:
        db_segments = json.loads(db_strategy_raw)
        db_strategy_canon = canonical_strategy_json(db_segments)
    except Exception:
        db_strategy_canon = db_strategy_raw

    entry["db_strategy_hash"] = sha256(db_strategy_canon)
    entry["strategy_match"] = entry["db_strategy_hash"] == strategy_hash

    # persist per-job artifact
    (out_dir / "jobs").mkdir(parents=True, exist_ok=True)
    with (out_dir / "jobs" / f"{job_id}.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "request_segments": segments,
                "response": data,
                "db": {
                    "user_id": row["user_id"],
                    "round_id": row["round_id"],
                    "attempt_number": row["attempt_number"],
                    "result_time": row["result_time"],
                    "is_dnf": row["is_dnf"],
                    "created_at": row["created_at"],
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Export the best-of-5 lap result details as a standalone CSV (what you asked for)
    try:
        res = data.get("result") or {}
        best_run = int(res.get("best_run") or 1)
        all_runs = res.get("all_runs") or []
        best = None
        if 1 <= best_run <= len(all_runs):
            best = all_runs[best_run - 1]
        elif all_runs:
            best = all_runs[0]

        details = (best or {}).get("details")
        if isinstance(details, list) and details:
            (out_dir / "lap_results").mkdir(parents=True, exist_ok=True)
            round_id = int(row["round_id"])
            attempt_no = int(row["attempt_number"])
            lap_time = row["result_time"]
            # format time for filename (avoid too many decimals / dots)
            lap_time_str = f"{float(lap_time):.4f}" if lap_time is not None else "DNF"
            filename = f"Lap-result-{student.username}-Round_{round_id}-{lap_time_str}-{attempt_no}.csv"

            # stable column order: common telemetry fields first, then the rest
            preferred = [
                "sec",
                "now_pos",
                "strategy",
                "current_speed km/h",
                "time(s)",
                "turn_id",
                "turn_timeloss",
                "car_status",
            ]
            cols = []
            for c in preferred:
                if any(c in r for r in details):
                    cols.append(c)
            # append any extra keys (e.g., base_time/penalty_time if ever present in rows)
            extra_keys = sorted({k for r in details for k in r.keys()} - set(cols))
            cols.extend(extra_keys)

            import csv

            with (out_dir / "lap_results" / filename).open("w", encoding="utf-8", newline="") as wf:
                w = csv.DictWriter(wf, fieldnames=cols)
                w.writeheader()
                for r in details:
                    w.writerow({k: r.get(k) for k in cols})
    except Exception as e:
        entry["lap_result_export_warn"] = str(e)

    return entry


def main():
    run_id = time.strftime("racing-sim-concurrency-%Y%m%d-%H%M%S")
    out_dir = OUT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # prepare students
    students_usernames = ["Student_01", "Student_02", "Student_03", "Student_04"]
    uid_map = force_reset_students_to_1234(students_usernames)

    # clear teacher sessions to make the test idempotent
    force_clear_teacher_sessions("teacher_01")

    teacher_token = teacher_login()
    round_id = teacher_create_round(teacher_token, max_attempts=20)

    students: List[Student] = []
    for u in students_usernames:
        token = student_login(u)
        students.append(Student(username=u, user_id=uid_map[u], token=token))

    plan: List[Tuple[Student, int]] = []
    for st in students:
        for i in range(10):
            plan.append((st, i + 1))

    random.shuffle(plan)

    results: List[Dict[str, Any]] = []
    log(f"Starting {len(plan)} submissions across {len(students)} students (round_id={round_id})...")

    # concurrency across students
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(submit_once, st, idx, out_dir) for (st, idx) in plan]
        for fut in cf.as_completed(futs):
            results.append(fut.result())
            done = len(results)
            if done % 5 == 0:
                log(f"...completed {done}/{len(plan)}")

    # summary
    ok_http = sum(1 for r in results if r.get("http_status") == 200)
    ok_match = sum(1 for r in results if r.get("strategy_match"))
    ok_bestof = sum(1 for r in results if r.get("bestof5_ok"))

    summary = {
        "run_id": run_id,
        "round_id": round_id,
        "students": students_usernames,
        "total_submissions": len(results),
        "http_200": ok_http,
        "strategy_match_ok": ok_match,
        "bestof5_ok": ok_bestof,
        "failures": [r for r in results if r.get("http_status") != 200 or not r.get("strategy_match") or not r.get("bestof5_ok")],
    }

    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # also write a concise CSV
    import csv

    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "student",
            "submission_idx",
            "http_status",
            "elapsed_sec",
            "job_id",
            "attempt_number",
            "db_round_id",
            "db_result_time",
            "bestof5_ok",
            "strategy_match",
        ])
        for r in sorted(results, key=lambda x: (x.get("student", ""), x.get("submission_idx", 0))):
            w.writerow([
                r.get("student"),
                r.get("submission_idx"),
                r.get("http_status"),
                r.get("elapsed_sec"),
                r.get("job_id"),
                r.get("attempt_number"),
                r.get("db_round_id"),
                r.get("db_result_time"),
                r.get("bestof5_ok"),
                r.get("strategy_match"),
            ])

    log("DONE")
    log(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
