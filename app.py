from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from flask import (
    Flask,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "timesheet.db"
DEFAULT_CALENDAR_SLOT_MINUTES = 30
DEFAULT_CALENDAR_SLOT_HEIGHT = 24

CHARGE_COLOR_CLASSES = [
    "charge-color-0",
    "charge-color-1",
    "charge-color-2",
    "charge-color-3",
    "charge-color-4",
    "charge-color-5",
    "charge-color-6",
    "charge-color-7",
    "charge-color-8",
    "charge-color-9",
]


def minutes_to_label(total_minutes: int) -> str:
    minutes = int(total_minutes)
    hours, mins = divmod(minutes, 60)
    return f"{hours:02d}:{mins:02d}"


def minutes_to_ampm(total_minutes: int) -> str:
    minutes = int(total_minutes)
    hours, mins = divmod(minutes, 60)
    suffix = "AM" if hours < 12 else "PM"
    hour12 = hours % 12 or 12
    return f"{hour12}:{mins:02d} {suffix}"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="change-me",
        DATABASE=str(DATABASE_PATH),
    )

    app.jinja_env.filters["minutes_to_label"] = minutes_to_label
    app.jinja_env.filters["minutes_to_ampm"] = minutes_to_ampm

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    @app.before_request
    def load_logged_in_user() -> None:
        g.db = get_db()
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            g.user = get_user_by_id(user_id)

    @app.teardown_appcontext
    def close_db(exception: Optional[BaseException]) -> None:  # pragma: no cover - teardown
        db = g.pop("db", None)
        if db is not None:
            db.close()

    register_routes(app)
    with app.app_context():
        init_db()
    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def init_db() -> None:
    conn = sqlite3.connect(current_app.config["DATABASE"])
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS charge_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_number TEXT NOT NULL,
                task_number TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, project_number, task_number),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS time_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                charge_code_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                activity_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(charge_code_id) REFERENCES charge_codes(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
        try:
            conn.execute("ALTER TABLE charge_codes ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    return g.db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def register_routes(app: Flask) -> None:
    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            name = request.form.get("name", "").strip()
            password = request.form.get("password", "")

            error = None
            if not email:
                error = "Email is required."
            elif not name:
                error = "Name is required."
            elif not password:
                error = "Password is required."
            elif user_exists(email):
                error = "Email already registered."

            if error:
                flash(error, "error")
            else:
                password_hash = generate_password_hash(password)
                now = datetime.utcnow().isoformat(timespec="seconds")
                g.db.execute(
                    "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (email, name, password_hash, now),
                )
                g.db.commit()
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            error = None

            user = g.db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                error = "Invalid email or password."

            if error:
                flash(error, "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    def dashboard():
        if g.user is None:
            return redirect(url_for("login"))

        anchor = request.args.get("date")
        try:
            anchor_date = datetime.strptime(anchor, "%Y-%m-%d").date() if anchor else date.today()
        except ValueError:
            anchor_date = date.today()

        week_start, week_end = calculate_week_bounds(anchor_date)
        entries = fetch_time_entries(g.user["id"], week_start, week_end)

        raw_codes = list_charge_codes(g.user["id"])
        color_count = len(CHARGE_COLOR_CLASSES) or 1
        charge_color_map: Dict[int, str] = {}
        active_charge_codes = []
        for index, row in enumerate(raw_codes):
            color_class = CHARGE_COLOR_CLASSES[index % color_count]
            charge_color_map[row["id"]] = color_class
            if row["is_active"]:
                active_charge_codes.append(
                    {
                        "id": row["id"],
                        "project_number": row["project_number"],
                        "task_number": row["task_number"],
                        "description": row["description"],
                        "color_class": color_class,
                    }
                )

        display_start_minutes = 7 * 60
        display_end_minutes = 18 * 60
        slot_minutes = DEFAULT_CALENDAR_SLOT_MINUTES
        grouped = group_entries_for_calendar(
            entries,
            charge_color_map,
            window_start=display_start_minutes,
            window_end=display_end_minutes,
        )
        overview = build_week_overview(entries, week_start, week_end)
        week_days = [week_start + timedelta(days=i) for i in range(7)]
        prev_week = week_start - timedelta(days=7)
        next_week = week_start + timedelta(days=7)
        today = date.today()
        time_slots = list(range(display_start_minutes, display_end_minutes, slot_minutes))
        slot_count = len(time_slots)

        return render_template(
            "dashboard.html",
            user=g.user,
            week_start=week_start,
            week_end=week_end,
            calendar_entries=grouped,
            overview=overview,
            charge_codes=active_charge_codes,
            week_days=week_days,
            anchor_date=anchor_date,
            prev_week=prev_week,
            next_week=next_week,
            today=today,
            time_slots=time_slots,
            calendar_slot_minutes=slot_minutes,
            slot_count=slot_count,
            slot_height=DEFAULT_CALENDAR_SLOT_HEIGHT,
            display_start_minutes=display_start_minutes,
        )

    @app.route("/charge-codes", methods=["GET", "POST"])
    def charge_codes():
        if g.user is None:
            return redirect(url_for("login"))

        if request.method == "POST":
            action = request.form.get("action", "create")
            if action == "toggle":
                try:
                    code_id = int(request.form.get("code_id", ""))
                    new_status = int(request.form.get("set_active", "1"))
                except ValueError:
                    flash("Invalid request.", "error")
                else:
                    g.db.execute(
                        "UPDATE charge_codes SET is_active = ? WHERE id = ? AND user_id = ?",
                        (1 if new_status else 0, code_id, g.user["id"]),
                    )
                    g.db.commit()
                    flash("Charge code status updated.", "success")
                return redirect(url_for("charge_codes"))

            project_number = request.form.get("project_number", "").strip()
            task_number = request.form.get("task_number", "").strip()
            description = request.form.get("description", "").strip()
            is_active = 1 if request.form.get("is_active") else 0

            error = None
            if not project_number:
                error = "Project number is required."
            elif not task_number:
                error = "Task number is required."
            elif not description:
                error = "Description is required."
            elif charge_code_exists(g.user["id"], project_number, task_number):
                error = "Charge code already exists."

            if error:
                flash(error, "error")
            else:
                g.db.execute(
                    """
                    INSERT INTO charge_codes (user_id, project_number, task_number, description, is_active)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (g.user["id"], project_number, task_number, description, is_active),
                )
                g.db.commit()
                flash("Charge code added.", "success")
                return redirect(url_for("charge_codes"))

        codes = list_charge_codes(g.user["id"])
        return render_template("charge_codes.html", charge_codes=codes)

    @app.route("/api/charge_codes", methods=["GET"])
    def api_charge_codes():
        if g.user is None:
            return jsonify({"error": "Not authenticated"}), 401
        rows = list_charge_codes(g.user["id"])
        payload = [
            {
                "id": row["id"],
                "project_number": row["project_number"],
                "task_number": row["task_number"],
                "description": row["description"],
                "is_active": row["is_active"],
            }
            for row in rows
        ]
        return jsonify(payload)

    @app.route("/entries/save", methods=["POST"])
    def save_entry():
        if g.user is None:
            return redirect(url_for("login"))

        entry_id_raw = request.form.get("entry_id", "").strip()
        entry_id = int(entry_id_raw) if entry_id_raw else None
        existing = None
        if entry_id is not None:
            existing = fetch_time_entry(entry_id, g.user["id"])
            if existing is None:
                flash("Entry not found.", "error")
                return redirect(url_for("dashboard"))

        error, cleaned = prepare_time_entry_payload(g.user["id"], request.form, existing)
        if error:
            flash(error, "error")
            return redirect(_dashboard_redirect_target(request.form.get("anchor_date")))

        now = datetime.utcnow().isoformat(timespec="seconds")
        if existing is None:
            cur = g.db.execute(
                """
                INSERT INTO time_entries
                (user_id, charge_code_id, entry_date, start_time, end_time, duration_minutes, activity_text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    cleaned["charge_code_id"],
                    cleaned["entry_date"].isoformat(),
                    cleaned["start_time"].strftime("%H:%M"),
                    cleaned["end_time"].strftime("%H:%M"),
                    cleaned["duration_minutes"],
                    cleaned["activity_text"],
                    now,
                    now,
                ),
            )
            g.db.commit()
            flash("Entry added.", "success")
        else:
            g.db.execute(
                """
                UPDATE time_entries
                SET charge_code_id = ?, entry_date = ?, start_time = ?, end_time = ?, duration_minutes = ?, activity_text = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    cleaned["charge_code_id"],
                    cleaned["entry_date"].isoformat(),
                    cleaned["start_time"].strftime("%H:%M"),
                    cleaned["end_time"].strftime("%H:%M"),
                    cleaned["duration_minutes"],
                    cleaned["activity_text"],
                    now,
                    entry_id,
                    g.user["id"],
                ),
            )
            g.db.commit()
            flash("Entry updated.", "success")

        return redirect(_dashboard_redirect_target(request.form.get("anchor_date")))

    @app.route("/entries/<int:entry_id>/delete", methods=["POST"])
    def delete_entry(entry_id: int):
        if g.user is None:
            return redirect(url_for("login"))

        g.db.execute(
            "DELETE FROM time_entries WHERE id = ? AND user_id = ?",
            (entry_id, g.user["id"]),
        )
        g.db.commit()
        flash("Entry deleted.", "success")
        return redirect(_dashboard_redirect_target(request.form.get("anchor_date")))

    @app.route("/api/time_entries", methods=["GET"])
    def api_time_entries():
        if g.user is None:
            return jsonify({"error": "Not authenticated"}), 401

        start = request.args.get("start")
        end = request.args.get("end")
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date() if start else date.today()
            end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else start_date
        except ValueError:
            return jsonify({"error": "Invalid date range"}), 400

        entries = fetch_time_entries(g.user["id"], start_date, end_date)
        return jsonify([asdict(entry) for entry in entries])

    @app.route("/api/time_entries", methods=["POST"])
    def create_time_entry():
        if g.user is None:
            return jsonify({"error": "Not authenticated"}), 401

        data = request.json or {}
        error, cleaned = prepare_time_entry_payload(g.user["id"], data)
        if error:
            return jsonify({"error": error}), 400

        now = datetime.utcnow().isoformat(timespec="seconds")
        cur = g.db.execute(
            """
            INSERT INTO time_entries
            (user_id, charge_code_id, entry_date, start_time, end_time, duration_minutes, activity_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                g.user["id"],
                cleaned["charge_code_id"],
                cleaned["entry_date"].isoformat(),
                cleaned["start_time"].strftime("%H:%M"),
                cleaned["end_time"].strftime("%H:%M"),
                cleaned["duration_minutes"],
                cleaned["activity_text"],
                now,
                now,
            ),
        )
        g.db.commit()
        entry_id = cur.lastrowid
        entry = fetch_time_entry(entry_id, g.user["id"])
        return jsonify(asdict(entry)), 201

    @app.route("/api/time_entries/<int:entry_id>", methods=["PUT"])
    def update_time_entry(entry_id: int):
        if g.user is None:
            return jsonify({"error": "Not authenticated"}), 401

        existing = fetch_time_entry(entry_id, g.user["id"])
        if existing is None:
            return jsonify({"error": "Entry not found"}), 404

        data = request.json or {}
        error, cleaned = prepare_time_entry_payload(g.user["id"], data, existing)
        if error:
            return jsonify({"error": error}), 400

        now = datetime.utcnow().isoformat(timespec="seconds")
        g.db.execute(
            """
            UPDATE time_entries
            SET charge_code_id = ?, entry_date = ?, start_time = ?, end_time = ?, duration_minutes = ?, activity_text = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                cleaned["charge_code_id"],
                cleaned["entry_date"].isoformat(),
                cleaned["start_time"].strftime("%H:%M"),
                cleaned["end_time"].strftime("%H:%M"),
                cleaned["duration_minutes"],
                cleaned["activity_text"],
                now,
                entry_id,
                g.user["id"],
            ),
        )
        g.db.commit()
        updated = fetch_time_entry(entry_id, g.user["id"])
        return jsonify(asdict(updated))

    @app.route("/api/time_entries/<int:entry_id>", methods=["DELETE"])
    def delete_time_entry(entry_id: int):
        if g.user is None:
            return jsonify({"error": "Not authenticated"}), 401

        g.db.execute(
            "DELETE FROM time_entries WHERE id = ? AND user_id = ?",
            (entry_id, g.user["id"]),
        )
        g.db.commit()
        return jsonify({"status": "ok"})


@dataclass
class EntryDTO:
    id: int
    charge_code_id: int
    charge_code_label: str
    entry_date: str
    start_time: str
    end_time: str
    duration_minutes: int
    activity_text: str


def user_exists(email: str) -> bool:
    row = g.db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
    return row is not None


def fetch_time_entry(entry_id: int, user_id: int) -> Optional[EntryDTO]:
    row = g.db.execute(
        """
        SELECT te.*, cc.project_number, cc.task_number, cc.description
        FROM time_entries te
        JOIN charge_codes cc ON cc.id = te.charge_code_id
        WHERE te.id = ? AND te.user_id = ?
        """,
        (entry_id, user_id),
    ).fetchone()
    if row is None:
        return None
    label = f"{row['project_number']}-{row['task_number']} {row['description']}"
    return EntryDTO(
        id=row["id"],
        charge_code_id=row["charge_code_id"],
        charge_code_label=label,
        entry_date=row["entry_date"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        duration_minutes=row["duration_minutes"],
        activity_text=row["activity_text"],
    )


def fetch_time_entries(user_id: int, start: date, end: date) -> List[EntryDTO]:
    rows = g.db.execute(
        """
        SELECT te.*, cc.project_number, cc.task_number, cc.description
        FROM time_entries te
        JOIN charge_codes cc ON cc.id = te.charge_code_id
        WHERE te.user_id = ? AND te.entry_date BETWEEN ? AND ?
        ORDER BY te.entry_date ASC, te.start_time ASC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    entries = []
    for row in rows:
        label = f"{row['project_number']}-{row['task_number']} {row['description']}"
        entries.append(
            EntryDTO(
                id=row["id"],
                charge_code_id=row["charge_code_id"],
                charge_code_label=label,
                entry_date=row["entry_date"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                duration_minutes=row["duration_minutes"],
                activity_text=row["activity_text"],
            )
        )
    return entries


def list_charge_codes(user_id: int):
    rows = g.db.execute(
        """
        SELECT id, project_number, task_number, description, is_active
        FROM charge_codes
        WHERE user_id = ?
        ORDER BY project_number, task_number
        """,
        (user_id,),
    ).fetchall()
    return rows


def owns_charge_code(user_id: int, charge_code_id: int) -> bool:
    row = g.db.execute(
        "SELECT 1 FROM charge_codes WHERE id = ? AND user_id = ?",
        (charge_code_id, user_id),
    ).fetchone()
    return row is not None


def charge_code_exists(user_id: int, project_number: str, task_number: str) -> bool:
    row = g.db.execute(
        """
        SELECT 1 FROM charge_codes
        WHERE user_id = ? AND project_number = ? AND task_number = ?
        """,
        (user_id, project_number, task_number),
    ).fetchone()
    return row is not None


def prepare_time_entry_payload(
    user_id: int, payload: Mapping[str, object], existing: Optional[EntryDTO] = None
) -> Tuple[Optional[str], Optional[Dict[str, object]]]:
    def _value(key: str, default: Optional[str] = None) -> Optional[str]:
        value = payload.get(key)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return default
        return value.strip() if isinstance(value, str) else value

    try:
        charge_code_raw = _value(
            "charge_code_id",
            str(existing.charge_code_id) if existing else None,
        )
        entry_date_raw = _value(
            "entry_date",
            existing.entry_date if existing else None,
        )
        start_time_raw = _value(
            "start_time",
            existing.start_time if existing else None,
        )
        end_time_raw = _value(
            "end_time",
            existing.end_time if existing else None,
        )
        activity_text = _value(
            "activity_text",
            existing.activity_text if existing else "",
        )
        if charge_code_raw is None or entry_date_raw is None or start_time_raw is None or end_time_raw is None:
            return "Missing required fields.", None

        charge_code_id = int(str(charge_code_raw))
        entry_date = datetime.strptime(entry_date_raw, "%Y-%m-%d").date()
        start_time = parse_time_str(start_time_raw)
        end_time = parse_time_str(end_time_raw)
    except (TypeError, ValueError):
        return "Invalid payload.", None

    if start_time >= end_time:
        return "Start time must be before end time.", None
    if not isinstance(activity_text, str):
        activity_text = str(activity_text)
    activity_text = activity_text.strip()
    if not activity_text:
        return "Activity text is required.", None
    if not owns_charge_code(user_id, charge_code_id):
        return "Invalid charge code.", None

    duration_minutes = difference_in_minutes(start_time, end_time)
    cleaned = {
        "charge_code_id": charge_code_id,
        "entry_date": entry_date,
        "start_time": start_time,
        "end_time": end_time,
        "duration_minutes": duration_minutes,
        "activity_text": activity_text,
    }
    return None, cleaned


def _dashboard_redirect_target(anchor_date: Optional[str]) -> str:
    if anchor_date:
        try:
            datetime.strptime(anchor_date, "%Y-%m-%d")
            return url_for("dashboard", date=anchor_date)
        except ValueError:
            pass
    return url_for("dashboard")


def parse_time_str(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def difference_in_minutes(start: time, end: time) -> int:
    delta = datetime.combine(date.today(), end) - datetime.combine(date.today(), start)
    return int(delta.total_seconds() // 60)


def time_to_minutes(value: str) -> int:
    parsed = parse_time_str(value)
    return parsed.hour * 60 + parsed.minute


def calculate_week_bounds(anchor: date) -> Tuple[date, date]:
    days_back = (anchor.weekday() - 3) % 7
    start = anchor - timedelta(days=days_back)
    end = start + timedelta(days=6)
    return start, end


def group_entries_for_calendar(
    entries: List[EntryDTO],
    color_lookup: Optional[Dict[int, str]] = None,
    window_start: int = 0,
    window_end: int = 24 * 60,
) -> Dict[str, List[Dict[str, object]]]:
    color_lookup = color_lookup or {}
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for entry in entries:
        day_entries = grouped.setdefault(entry.entry_date, [])
        start_minutes = time_to_minutes(entry.start_time)
        entry_end = start_minutes + entry.duration_minutes
        if entry_end <= window_start or start_minutes >= window_end:
            continue
        clamped_start = max(start_minutes, window_start)
        clamped_end = min(entry_end, window_end)
        relative_start = clamped_start - window_start
        relative_duration = max(clamped_end - clamped_start, 1)
        day_entries.append(
            {
                "id": entry.id,
                "entry_date": entry.entry_date,
                "charge_code_id": entry.charge_code_id,
                "start_time": entry.start_time,
                "end_time": entry.end_time,
                "activity_text": entry.activity_text,
                "charge_code_label": entry.charge_code_label,
                "duration_minutes": entry.duration_minutes,
                "start_minutes": start_minutes,
                "end_minutes": entry_end,
                "relative_start_minutes": relative_start,
                "relative_duration_minutes": relative_duration,
                "color_class": color_lookup.get(entry.charge_code_id, "charge-color-default"),
            }
        )
    return grouped


def build_week_overview(entries: List[EntryDTO], week_start: date, week_end: date):
    overview: Dict[str, Dict[str, Dict[str, object]]] = {}
    days = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
    day_totals = {day: 0.0 for day in days}

    for entry in entries:
        label = entry.charge_code_label
        per_charge = overview.setdefault(
            label,
            {
                day: {
                    "hours": 0.0,
                    "comments": [],
                    "details": [],
                }
                for day in days
            },
        )
        per_day = per_charge[entry.entry_date]
        hours = entry.duration_minutes / 60
        per_day["hours"] += hours
        per_day["comments"].append(entry.activity_text)
        per_day["details"].append(
            {
                "start_time": entry.start_time,
                "end_time": entry.end_time,
                "activity_text": entry.activity_text,
            }
        )
        day_totals[entry.entry_date] += hours

    rows = []
    for label in sorted(overview.keys()):
        per_charge = overview[label]
        cells: Dict[str, Dict[str, object]] = {}
        for day in days:
            info = per_charge[day]
            cells[day] = {
                "hours": round(info["hours"], 2),
                "comments": info["comments"],
                "details": info["details"],
            }
        total_hours = round(sum(cell["hours"] for cell in cells.values()), 2)
        rows.append({"label": label, "cells": cells, "total": total_hours})

    day_totals = {day: round(total, 2) for day, total in day_totals.items()}
    week_total = round(sum(day_totals.values()), 2)
    return {"days": days, "rows": rows, "day_totals": day_totals, "week_total": week_total}


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, host="0.0.0.0", port=5001)
