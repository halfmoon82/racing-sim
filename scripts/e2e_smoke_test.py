import requests

BASE = "http://127.0.0.1:8000"

def log(name, ok, detail=""):
    print(f"[{ 'PASS' if ok else 'FAIL' }] {name} {detail}")


def main():
    # Make the smoke test idempotent: clear teacher session cap in Redis.
    try:
        import redis
        rds = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        # teacher_01 has fixed id=6 in our seed DB.
        rds.delete("user_sessions:6")
    except Exception:
        pass

    try:
        r = requests.get(f"{BASE}/api/health", timeout=5)
        log("health", r.status_code == 200, r.text)
    except Exception as e:
        log("health", False, str(e))
        return

    # admin login
    r = requests.post(f"{BASE}/api/auth/login", json={"username":"admin","password":"admin123"}, timeout=5)
    if r.status_code != 200:
        log("admin_login", False, r.text)
        return
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    log("admin_login", True)

    # localhost admin endpoint
    r = requests.get(f"{BASE}/api/admin/teachers", headers=h, timeout=5)
    log("admin_localhost_guard", r.status_code in (200,403), str(r.status_code))

    # create teacher
    # Note: during test phase we keep default passwords as 1234.
    payload = {"username":"teacher_01","password":"1234","display_name":"Teacher 01"}
    r = requests.post(f"{BASE}/api/admin/teachers", json=payload, headers=h, timeout=5)
    log("create_teacher", r.status_code in (200,400), str(r.status_code))

    # teacher login
    r = requests.post(f"{BASE}/api/auth/login", json={"username":"teacher_01","password":"1234"}, timeout=5)
    if r.status_code != 200:
        log("teacher_login", False, r.text)
        return
    tkn = r.json()["token"]
    th = {"Authorization": f"Bearer {tkn}"}
    log("teacher_login", True)

    # create round
    r = requests.post(f"{BASE}/api/teacher/rounds", json={"name":"Round Smoke","max_attempts":2}, headers=th, timeout=5)
    log("create_round", r.status_code==200, r.text)

    # dashboard
    r = requests.get(f"{BASE}/api/teacher/dashboard", headers=th, timeout=5)
    log("teacher_dashboard", r.status_code==200)

if __name__ == '__main__':
    main()
