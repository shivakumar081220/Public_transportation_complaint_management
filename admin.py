import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")
ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"

app = Flask(__name__)
app.config["SECRET_KEY"] = "admin-secret-key-change-this"


def init_admin_db():
	conn = sqlite3.connect(DATABASE)
	cursor = conn.cursor()
	cursor.execute(
		"""
		CREATE TABLE IF NOT EXISTS complaints (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER,
			user_email TEXT,
			name TEXT NOT NULL,
			contact TEXT NOT NULL,
			transport_type TEXT NOT NULL,
			vehicle_number TEXT,
			description TEXT NOT NULL,
			admin_message TEXT,
			image_path TEXT,
			status TEXT NOT NULL DEFAULT 'Pending',
			created_at TEXT NOT NULL,
			updated_at TEXT NOT NULL
		)
		"""
	)
	columns = {row[1] for row in cursor.execute("PRAGMA table_info(complaints)").fetchall()}
	if "admin_message" not in columns:
		cursor.execute("ALTER TABLE complaints ADD COLUMN admin_message TEXT")
	conn.commit()
	conn.close()


init_admin_db()


def get_db():
	if "db" not in g:
		g.db = sqlite3.connect(DATABASE)
		g.db.row_factory = sqlite3.Row
	return g.db


@app.teardown_appcontext
def close_db(exception):
	db = g.pop("db", None)
	if db is not None:
		db.close()


@app.before_request
def load_admin_user():
	g.current_user = None
	if session.get("admin_logged_in"):
		g.current_user = {
			"username": "Admin",
			"email": session.get("admin_email", ADMIN_EMAIL),
		}


@app.context_processor
def inject_admin_context():
	return {
		"current_user": getattr(g, "current_user", None),
	}


def admin_login_required(view):
	@wraps(view)
	def wrapped_view(*args, **kwargs):
		if not session.get("admin_logged_in"):
			flash("Please login as admin.", "error")
			return redirect(url_for("admin_login"))
		return view(*args, **kwargs)

	return wrapped_view


@app.route("/")
def home():
	if session.get("admin_logged_in"):
		return redirect(url_for("admin_dashboard"))
	return redirect(url_for("admin_login"))


@app.route("/login", methods=["GET", "POST"])
def admin_login():
	if request.method == "POST":
		email = request.form.get("email", "").strip().lower()
		password = request.form.get("password", "")

		if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
			session.clear()
			session["admin_logged_in"] = True
			session["admin_email"] = ADMIN_EMAIL
			flash("Admin login successful.", "success")
			return redirect(url_for("admin_dashboard"))

		flash("Invalid admin credentials.", "error")
		return redirect(url_for("admin_login"))

	return render_template("admin/login.html")


@app.route("/dashboard")
@admin_login_required
def admin_dashboard():
	complaints = get_db().execute(
		"""
		SELECT id, user_email, name, contact, transport_type, description, admin_message, image_path, status, created_at, updated_at
		FROM complaints
		ORDER BY datetime(created_at) DESC
		"""
	).fetchall()

	summary = get_db().execute(
		"""
		SELECT
			COUNT(*) AS total_count,
			SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending_count,
			SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) AS progress_count,
			SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS resolved_count
		FROM complaints
		"""
	).fetchone()

	return render_template("admin/dashboard.html", complaints=complaints, summary=summary)


@app.route("/analytics")
@admin_login_required
def admin_analytics():
	status_rows = get_db().execute(
		"""
		SELECT status, COUNT(*) AS count
		FROM complaints
		GROUP BY status
		ORDER BY count DESC
		"""
	).fetchall()

	transport_rows = get_db().execute(
		"""
		SELECT transport_type, COUNT(*) AS count
		FROM complaints
		GROUP BY transport_type
		ORDER BY count DESC
		"""
	).fetchall()

	daily_rows = get_db().execute(
		"""
		SELECT date(created_at) AS day, COUNT(*) AS count
		FROM complaints
		WHERE datetime(created_at) >= datetime('now', '-14 day')
		GROUP BY date(created_at)
		ORDER BY day ASC
		"""
	).fetchall()

	analytics = {
		"status_labels": [row["status"] for row in status_rows],
		"status_values": [row["count"] for row in status_rows],
		"transport_labels": [row["transport_type"] for row in transport_rows],
		"transport_values": [row["count"] for row in transport_rows],
		"daily_labels": [row["day"] for row in daily_rows],
		"daily_values": [row["count"] for row in daily_rows],
	}

	return render_template("admin/analytics.html", analytics=analytics)


@app.route("/update_status/<int:complaint_id>", methods=["POST"])
@admin_login_required
def update_status(complaint_id):
	admin_message = request.form.get("admin_message", "").strip()
	new_status = request.form.get("status", "").strip()
	allowed_statuses = {"Pending", "In Progress", "Resolved", "Rejected"}

	if not admin_message:
		flash("Please enter admin description before saving status.", "error")
		return redirect(url_for("admin_dashboard"))

	if new_status not in allowed_statuses:
		flash("Please choose a valid status.", "error")
		return redirect(url_for("admin_dashboard"))

	get_db().execute(
		"""
		UPDATE complaints
		SET status = ?, admin_message = ?, updated_at = ?
		WHERE id = ?
		""",
		(new_status, admin_message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), complaint_id),
	)
	get_db().commit()

	flash("Complaint status updated.", "success")
	return redirect(url_for("admin_dashboard"))


@app.route("/logout")
def admin_logout():
	session.clear()
	flash("Admin logged out.", "success")
	return redirect(url_for("admin_login"))


if __name__ == "__main__":
	print("Admin portal running at: http://127.0.0.1:5001")
	app.run(debug=True, port=5001)
