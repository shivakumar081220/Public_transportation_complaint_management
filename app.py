import os
import sqlite3
from datetime import datetime
from functools import wraps
from uuid import uuid4

from flask import Flask, flash, g, redirect, render_template, request, session, send_from_directory, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
HOMEPAGE_IMAGE_FOLDER = os.path.join(BASE_DIR, "images", "homepage")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def link_user_complaints(user_email, username):
    """Attach older complaints to the user when they match by name and are still unlinked."""
    db = get_db()
    db.execute(
        """
        UPDATE complaints
        SET user_email = ?
        WHERE user_email IS NULL
                    AND LOWER(REPLACE(TRIM(name), ' ', '')) = LOWER(REPLACE(TRIM(?), ' ', ''))
        """,
        (user_email, username),
    )
    db.commit()


def link_user_complaints_by_id(user_id, user_email, username):
    """Backfill user_id and email for historical complaints belonging to this user."""
    db = get_db()
    db.execute(
        """
        UPDATE complaints
        SET user_id = ?, user_email = COALESCE(user_email, ?)
        WHERE user_id IS NULL
          AND (
              LOWER(COALESCE(user_email, '')) = LOWER(?)
              OR LOWER(REPLACE(TRIM(name), ' ', '')) = LOWER(REPLACE(TRIM(?), ' ', ''))
          )
        """,
        (user_id, user_email, user_email, username),
    )
    db.commit()


def init_db():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    complaints_columns = {row[1] for row in cursor.execute("PRAGMA table_info(complaints)").fetchall()}
    if "user_id" not in complaints_columns:
        cursor.execute("ALTER TABLE complaints ADD COLUMN user_id INTEGER")
    if "user_email" not in complaints_columns:
        cursor.execute("ALTER TABLE complaints ADD COLUMN user_email TEXT")
    if "vehicle_number" not in complaints_columns:
        cursor.execute("ALTER TABLE complaints ADD COLUMN vehicle_number TEXT")
    if "admin_message" not in complaints_columns:
        cursor.execute("ALTER TABLE complaints ADD COLUMN admin_message TEXT")
    if "status" not in complaints_columns:
        cursor.execute("ALTER TABLE complaints ADD COLUMN status TEXT NOT NULL DEFAULT 'Pending'")
    if "updated_at" not in complaints_columns:
        cursor.execute("ALTER TABLE complaints ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")

    existing_admin = cursor.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
    if existing_admin is None:
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Admin",
                ADMIN_EMAIL,
                generate_password_hash(ADMIN_PASSWORD),
                "admin",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

    conn.commit()
    conn.close()


with app.app_context():
    init_db()


@app.before_request
def load_current_user():
    g.current_user = None
    user_id = session.get("user_id")
    if not user_id:
        return

    user = get_db().execute(
        "SELECT id, username, email, role, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if user is None:
        session.clear()
        return

    g.current_user = user


@app.context_processor
def inject_user_context():
    current_user = getattr(g, "current_user", None)
    is_authenticated = current_user is not None

    return {
        "current_user": current_user,
        "is_authenticated": is_authenticated,
        "is_admin": False,
        "profile_link": url_for("profile"),
    }


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.current_user is None:
            flash("Login or sign up to continue using the website.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def index():
    auth_tab = request.args.get("auth", "login")
    return render_template("index.html", auth_tab=auth_tab)


@app.route("/homepage-images/<path:filename>")
def homepage_image(filename):
    return send_from_directory(HOMEPAGE_IMAGE_FOLDER, filename)


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email and password are required.", "error")
        return redirect(url_for("index", auth="login"))

    user = get_db().execute(
        "SELECT id, username, email, password_hash, role FROM users WHERE email = ?",
        (email,),
    ).fetchone()

    if user and check_password_hash(user["password_hash"], password):
        if user["role"] == "admin":
            flash("Use admin.py to login as admin (http://127.0.0.1:5001).", "error")
            return redirect(url_for("index", auth="login"))

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user["email"]
        session["role"] = user["role"]

        if user["role"] == "user":
            link_user_complaints(user["email"], user["username"])
            link_user_complaints_by_id(user["id"], user["email"], user["username"])

        flash("Login successful.", "success")
        return redirect(url_for("index"))

    flash("Invalid email or password.", "error")
    return redirect(url_for("index", auth="login"))


@app.route("/signup", methods=["POST"])
def signup():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not username or not email or not password or not confirm_password:
        flash("Please fill in all signup fields.", "error")
        return redirect(url_for("index", auth="signup"))

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("index", auth="signup"))

    existing_user = get_db().execute(
        "SELECT id FROM users WHERE email = ?",
        (email,),
    ).fetchone()

    if existing_user is not None:
        flash("This email is already registered.", "error")
        return redirect(url_for("index", auth="signup"))

    get_db().execute(
        """
        INSERT INTO users (username, email, password_hash, role, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            username,
            email,
            generate_password_hash(password),
            "user",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    get_db().commit()

    flash("Signup successful. Please login to continue.", "success")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/services")
@login_required
def services():
    return render_template("services.html")


@app.route("/profile")
@login_required
def profile():
    link_user_complaints_by_id(g.current_user["id"], g.current_user["email"], g.current_user["username"])

    complaints = get_db().execute(
        """
           SELECT id, name, contact, transport_type, description, admin_message, image_path, status, created_at, updated_at
               , vehicle_number
        FROM complaints
        WHERE user_id = ?
           OR LOWER(COALESCE(user_email, '')) = LOWER(?)
              OR LOWER(REPLACE(TRIM(name), ' ', '')) = LOWER(REPLACE(TRIM(?), ' ', ''))
        ORDER BY datetime(created_at) DESC
        """,
        (g.current_user["id"], g.current_user["email"], g.current_user["username"]),
    ).fetchall()

    complaint_count = len(complaints)
    pending_count = sum(1 for complaint in complaints if complaint["status"] == "Pending")
    in_progress_count = sum(1 for complaint in complaints if complaint["status"] == "In Progress")
    resolved_count = sum(1 for complaint in complaints if complaint["status"] == "Resolved")

    return render_template(
        "profile.html",
        username=g.current_user["username"],
        email=g.current_user["email"],
        complaints=complaints,
        complaint_count=complaint_count,
        pending_count=pending_count,
        in_progress_count=in_progress_count,
        resolved_count=resolved_count,
    )


@app.route("/api/profile_stats")
@login_required
def profile_stats():
    link_user_complaints_by_id(g.current_user["id"], g.current_user["email"], g.current_user["username"])

    complaints = get_db().execute(
        """
        SELECT status
               , vehicle_number
        FROM complaints
        WHERE user_id = ?
           OR LOWER(COALESCE(user_email, '')) = LOWER(?)
              OR LOWER(REPLACE(TRIM(name), ' ', '')) = LOWER(REPLACE(TRIM(?), ' ', ''))
        """,
        (g.current_user["id"], g.current_user["email"], g.current_user["username"]),
    ).fetchall()

    return {
        "complaint_count": len(complaints),
        "pending_count": sum(1 for complaint in complaints if complaint["status"] == "Pending"),
        "in_progress_count": sum(1 for complaint in complaints if complaint["status"] == "In Progress"),
        "resolved_count": sum(1 for complaint in complaints if complaint["status"] == "Resolved"),
    }


@app.route("/api/profile_complaints")
@login_required
def profile_complaints():
    link_user_complaints_by_id(g.current_user["id"], g.current_user["email"], g.current_user["username"])

    complaints = get_db().execute(
        """
        SELECT id, status, updated_at
               , vehicle_number
        FROM complaints
        WHERE user_id = ?
           OR LOWER(COALESCE(user_email, '')) = LOWER(?)
              OR LOWER(REPLACE(TRIM(name), ' ', '')) = LOWER(REPLACE(TRIM(?), ' ', ''))
        ORDER BY datetime(created_at) DESC
        """,
        (g.current_user["id"], g.current_user["email"], g.current_user["username"]),
    ).fetchall()

    return {
        "complaints": [
            {
                "id": complaint["id"],
                "status": complaint["status"],
                "updated_at": complaint["updated_at"],
            }
            for complaint in complaints
        ]
    }


@app.route("/user/dashboard")
@login_required
def user_dashboard():
    complaints = get_db().execute(
        """
        SELECT id, name, contact, transport_type, vehicle_number, description, admin_message, image_path, status, created_at, updated_at
        FROM complaints
          WHERE user_id = ?
              OR LOWER(COALESCE(user_email, '')) = LOWER(?)
              OR LOWER(REPLACE(TRIM(name), ' ', '')) = LOWER(REPLACE(TRIM(?), ' ', ''))
        ORDER BY datetime(created_at) DESC
        """,
          (g.current_user["id"], g.current_user["email"], g.current_user["username"]),
    ).fetchall()

    return render_template("user/dashboard.html", complaints=complaints)


@app.route("/complaints")
@login_required
def complaints():
    selected_type = request.args.get("transport_type", "All")

    if selected_type != "All":
        all_complaints = get_db().execute(
            """
              SELECT id, name, contact, transport_type, description, admin_message, image_path, status, created_at, updated_at
                  , vehicle_number
            FROM complaints
            WHERE transport_type = ?
            ORDER BY datetime(created_at) DESC
            """,
            (selected_type,),
        ).fetchall()
    else:
        all_complaints = get_db().execute(
            """
            SELECT id, name, contact, transport_type, vehicle_number, description, admin_message, image_path, status, created_at, updated_at
            FROM complaints
            ORDER BY datetime(created_at) DESC
            """
        ).fetchall()

    return render_template(
        "complaints.html",
        complaints=all_complaints,
        selected_type=selected_type,
    )


@app.route("/new_complaint", methods=["GET", "POST"])
@login_required
def new_complaint():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact = request.form.get("contact", "").strip()
        transport_type = request.form.get("transport_type", "").strip()
        vehicle_number = request.form.get("vehicle_number", "").strip()
        description = request.form.get("description", "").strip()
        file = request.files.get("image")

        if not name or not contact or not transport_type or not vehicle_number or not description or not file or not file.filename:
            flash("All complaint fields are required, including vehicle number and image.", "error")
            return redirect(url_for("new_complaint"))

        if transport_type not in {"Bus", "Train", "Auto", "Metro", "Taxi"}:
            flash("Invalid transportation type selected.", "error")
            return redirect(url_for("new_complaint"))

        if not allowed_file(file.filename):
            flash("Invalid file type. Please upload an image file.", "error")
            return redirect(url_for("new_complaint"))

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid4().hex}_{filename}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
        file.save(save_path)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        get_db().execute(
            """
            INSERT INTO complaints (
                user_id, user_email, name, contact, transport_type, vehicle_number, description,
                image_path, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                g.current_user["id"],
                g.current_user["email"],
                name,
                contact,
                transport_type,
                vehicle_number,
                description,
                f"uploads/{unique_filename}",
                "Pending",
                timestamp,
                timestamp,
            ),
        )
        get_db().commit()

        flash("Complaint submitted successfully.", "success")
        return redirect(url_for("complaints"))

    return render_template("new_complaint.html")


if __name__ == "__main__":
    app.run(debug=True)
