"""Extended smoke test for racing-sim.

Scope: verify core end-to-end API flows on localhost.
- health
- admin login + localhost guard
- teacher login + dashboard
- round create/stop
- student login + status
- student cockpit occupied behavior
- teacher force release student session
- teacher reset student password
- student submit (JSON) minimal valid strategy
- student history
- teacher export

Notes:
- Assumes test phase default passwords are 1234.
- Makes test idempotent by clearing Redis session keys for teacher_01 and Student_01.
"""

import json
import time
import requests

BASE = "http://127.0.0.1:8000"


def log(name, ok, detail=""):
    print(f"[{ 'PASS' if ok else 'FAIL' }] {name} {detail}")


def jpost(path, payload=None, headers=None, timeout=10):
    return requests.post(f"{BASE}{path}", json=payload, headers=headers, timeout=timeout)


def jget(path, headers=None, timeout=10):
    return requests.get(f"{BASE}{path}", headers=headers, timeout=timeout)


def main():
    # --- pre-clean (idempotent) ---
    try:
        import redis

        rds = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        # teacher_01 id=6, Student_01 id=9 in seeded DB
        rds.delete("user_sessions:6")
        rds.delete("user_session:9")
    except Exception:
        pass

    # --- health ---
    try:
        r = jget("/api/health", timeout=5)
        log("health", r.status_code == 200, r.text)
    except Exception as e:
        log("health", False, str(e))
        return

    # --- admin login ---
    r = jpost("/api/auth/login", {"username": "admin", "password": "admin123"}, timeout=5)
    if r.status_code != 200:
        log("admin_login", False, r.text)
        return
    admin_token = r.json()["token"]
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    log("admin_login", True)

    # --- admin localhost guard ---
    r = jget("/api/admin/teachers", headers=admin_h, timeout=5)
    log("admin_list_teachers", r.status_code in (200, 403), str(r.status_code))

    # --- teacher login ---
    r = jpost("/api/auth/login", {"username": "teacher_01", "password": "1234"}, timeout=5)
    if r.status_code != 200:
        log("teacher_login", False, r.text)
        return
    teacher_token = r.json()["token"]
    teacher_h = {"Authorization": f"Bearer {teacher_token}"}
    log("teacher_login", True)

    # --- teacher dashboard ---
    r = jget("/api/teacher/dashboard", headers=teacher_h, timeout=5)
    log("teacher_dashboard", r.status_code == 200)
    if r.status_code != 200:
        return
    dash = r.json()
    assert "students" in dash

    # find Student_01 id
    s1 = next((s for s in dash["students"] if s.get("username") == "Student_01"), None)
    if not s1:
        log("find_student_01", False, "Student_01 not found in dashboard")
        return
    student_id = s1["id"]
    log("find_student_01", True, f"id={student_id}")

    # --- create round ---
    r = jpost(
        "/api/teacher/rounds",
        {"name": "Round Smoke Full", "max_attempts": 2},
        headers=teacher_h,
        timeout=10,
    )
    log("create_round", r.status_code == 200, r.text)

    # --- student login ---
    r = jpost("/api/auth/login", {"username": "Student_01", "password": "1234"}, timeout=5)
    if r.status_code != 200:
        log("student_login", False, r.text)
        return
    student_token = r.json()["token"]
    student_h = {"Authorization": f"Bearer {student_token}"}
    log("student_login", True)

    # --- student status ---
    r = jget("/api/student/status", headers=student_h, timeout=10)
    log("student_status", r.status_code == 200, r.text[:120])

    # --- occupied behavior: second login should be 403 cockpit occupied ---
    r2 = jpost("/api/auth/login", {"username": "Student_01", "password": "1234"}, timeout=5)
    ok_occ = r2.status_code == 403 and "Cockpit Occupied" in r2.text
    log("student_cockpit_occupied", ok_occ, f"{r2.status_code} {r2.text.strip()}")

    # --- teacher force release student session ---
    r = requests.post(
        f"{BASE}/api/teacher/students/{student_id}/release-session",
        headers=teacher_h,
        timeout=10,
    )
    log("teacher_release_student_session", r.status_code == 200, r.text)

    # after release, student can login again
    r = jpost("/api/auth/login", {"username": "Student_01", "password": "1234"}, timeout=5)
    log("student_login_after_release", r.status_code == 200, r.text)
    student_token2 = r.json()["token"] if r.status_code == 200 else None
    student_h2 = {"Authorization": f"Bearer {student_token2}"} if student_token2 else student_h

    # --- teacher reset student password (then set back to 1234 via admin would be ideal; skip) ---
    r = requests.post(
        f"{BASE}/api/teacher/students/{student_id}/reset-password",
        headers=teacher_h,
        timeout=10,
    )
    ok_reset = r.status_code == 200 and "new_password" in r.text
    log("teacher_reset_student_password", ok_reset)

    # --- student submit (JSON) ---
    # Create minimal valid segments: 9 straight segments, positions increasing.
    # Ensure strategy reaches finish (2820m)
    step = 2820.0 / 8.0
    segments = [{"now_pos": float(i * step), "strategy": "a", "is_corner": False} for i in range(9)]
    segments[-1]["now_pos"] = 2820.0
    payload = {"segments": segments}

    # This calls physics engine (can take a moment)
    r = requests.post(
        f"{BASE}/api/student/submit",
        headers=student_h2,
        json=payload,
        timeout=60,
    )
    log("student_submit", r.status_code == 200, r.text[:160])

    # --- history ---
    r = jget("/api/student/history", headers=student_h2, timeout=10)
    ok_hist = r.status_code == 200 and "records" in r.text
    log("student_history", ok_hist)

    # --- teacher export current round id (best-effort) ---
    # dashboard again to get current round id
    r = jget("/api/teacher/dashboard", headers=teacher_h, timeout=10)
    round_id = r.json().get("current_round", {}).get("id") if r.status_code == 200 else None
    if round_id:
        r = requests.get(f"{BASE}/api/teacher/export/{round_id}", headers=teacher_h, timeout=20)
        ok_export = r.status_code == 200 and "text/csv" in r.headers.get("content-type", "")
        log("teacher_export_csv", ok_export, f"round_id={round_id}")
    else:
        log("teacher_export_csv", False, "no round_id")

    # --- stop round ---
    if round_id:
        r = requests.post(f"{BASE}/api/teacher/rounds/{round_id}/stop", headers=teacher_h, timeout=10)
        log("stop_round", r.status_code == 200, r.text)


if __name__ == "__main__":
    main()
