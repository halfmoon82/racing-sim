# Racing-sim UAT Plan (finish-derived + synthetic)

## Objective
Validate end-to-end behavior from **frontend inputs** to **API outputs** and **UI rendering**.
Pass/Fail is determined by comparing **actual response** vs **expected response** (schema + semantic rules).

Constraints:
- Do **not** modify physics engine code/params.
- Use finish-derived strategies to guarantee at least some non-DNF results.

## Test Data Sources
- Finish dataset: `file_12---1d638fc0-4148-4e00-9237-4e65408f0b91.xlsx` (sheet `Finish_LAP_result2_205`).
- Extracted top finish strategies (CSV, ready for `/api/student/submit-csv`):
  - `uat/finish_strategies/finish_lap90.csv` (best total_time)
  - `.../finish_lap42.csv`
  - `.../finish_lap85.csv`
  - `.../finish_lap33.csv`
  - `.../finish_lap62.csv`
  - `.../finish_lap39.csv`
  - `.../finish_lap82.csv`
  - `.../finish_lap86.csv`
  - `.../finish_lap43.csv`
  - `.../finish_lap40.csv`

## Core APIs Under Test
- `POST /api/auth/login`
- `GET /api/student/status` (leaderboard + current round info)
- `GET /api/student/history`
- `POST /api/student/submit` (JSON segments)
- `POST /api/student/submit-csv` (CSV upload)
- `GET /api/teacher/dashboard`
- (Optional) `GET /api/teacher/export` (if used in UI)

## Semantic Expectations (shared)
- A **DNF** run MUST satisfy: `is_dnf=true` AND `final_time=null` AND `result_time` stored as NULL.
- A **Finish** run MUST satisfy: `is_dnf=false` AND `final_time` is number > 0 AND `result_time` stored non-NULL.
- History MUST show **all** attempts (DNF included) within retention window.
- Leaderboard MUST only rank students with **non-NULL finish times** (ignore DNF + NULL times).
- Teacher dashboard `best_time` must match the same criterion as leaderboard (min non-NULL finish time).

## Positive Flows
### P1. Student login → submit-csv (finish) → status leaderboard updates
Input:
- Login: valid student creds.
- Upload `finish_lap90.csv`.
Expected:
- submit response: 200, JSON includes `job_id`, `attempt_number`, `result` with `final_time` number, `is_dnf=false`.
- student/status: leaderboard includes this student with `time==final_time` (or <= if best run differs).
- student/history: includes a record with same attempt_number and non-NULL `result_time`.

### P2. Multiple finish submissions produce monotonic used_attempts and best_time min
Input:
- Upload 3 different finish csvs sequentially.
Expected:
- attempt_number increments.
- history count increases by 3.
- best time in leaderboard equals min of those finishes.

### P3. Teacher dashboard/API sees same best_time as student leaderboard
Input:
- Teacher login (seeded users in DB): `teacher_01` / `1234`.
Expected:
- For each student: `best_time` equals min(non-NULL result_time where is_dnf=0).

### P4. Teacher UI (Race Control / Driver Monitor) shows Best Lap
Steps (UI):
- Login as teacher (`teacher_01`/`1234`).
- Open “车手监控墙 | Driver Monitor”.
Expected:
- Student 01 row shows attempts like `13 / 20`.
- Best Lap shows a non-empty value like `135.52s` (not `-`).
- The value should match the student leaderboard best time (same semantics: min non-NULL finish time).

## Negative Flows
### N1. Login invalid password
Expected:
- 401/403 with detail explaining auth failure.

### N2. Submit without auth
Expected:
- 401.

### N3. CSV missing required columns / malformed headers
Input:
- Remove `now_pos` column.
Expected:
- 400 with validation error.

### N4. CSV contains unknown turn_id / missing 9 corners
Expected:
- 400 (or 200 with DNF, depending on backend rules) — define expected once confirmed.

### N5. Exceed max_attempts
Expected:
- 403 "Out of Laps / 配额耗尽".

### N6. Cockpit Occupied
Expected:
- 403 "Cockpit Occupied / 驾驶舱已被占用" (and operator can clear redis user_session + sessions table).

## Synthetic Strategy Generation (for robustness)
Create additional strategies by mutating a finish CSV:
- small steer_degree perturbation ±(0.5..2.0) degrees
- swap a/b segments in non-corner rows
- keep all 9 turn_id rows intact
Expectation:
- mixture of finish + DNF results; system must remain stable and consistent (no 500).

## Pass Criteria
- All Positive flows P1-P3 pass.
- Negative flows return the expected error codes and stable error JSON.
- No 500s during batch UAT.
