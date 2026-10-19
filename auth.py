"""FaceTrack teacher authentication: login, signup, password reset. UI + logic, all in Python."""
import hashlib, os, re, secrets, smtplib, sqlite3
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from flask import (Blueprint, abort, flash, get_flashed_messages, jsonify, redirect,
                   render_template_string, request, session, url_for)
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "students.db"
KEY_PATH = BASE_DIR / "secret.key"
RESET_MINUTES = 30
PUBLIC = {"auth.login", "auth.signup", "auth.forgot", "auth.reset"}
bp = Blueprint("auth", __name__)

# ---------- validation rules (single source of truth) ----------
RULES = {
    "email": (r"[^@\s]+@[^@\s]+\.[^@\s]+", "Enter a valid email address."),
    "college_email": (r"[^@\s]+@[^@\s]+\.[^@\s]+", "Enter a valid college email."),
    "phone": (r"[0-9+()\-\s]{7,20}", "Enter a valid phone number."),
    "username": (r"[A-Za-z0-9_.]{4,30}", "Username: 4-30 characters, letters, numbers, dot or underscore."),
}


def field(name, label, kind="text", auto="off", hint=""):
    return dict(name=name, label=label, kind=kind, auto=auto, hint=hint)


PW_HINT = "8+ characters, letters and a number"
NEW_PW = [[field("password", "Password", "password", "new-password", PW_HINT),
           field("confirm", "Confirm password", "password", "new-password")]]

# ---------- every page is just data ----------
PAGES = {
    "login": dict(eyebrow="Welcome back", title="Log in", sub="Use your username or college email.",
        fields=[[field("identifier", "Username or college email", auto="username")],
                [field("password", "Password", "password", "current-password")]],
        button="Log in", remember=True,
        links=[("Forgot password?", "auth.forgot"), ("Create an account", "auth.signup")]),
    "signup": dict(eyebrow="New teacher account", title="Sign up",
        sub="Your college email is where password reset links are sent.",
        fields=[[field("name", "Full name", auto="name"), field("teacher_code", "Teacher code")],
                [field("subject", "Subject you teach")],
                [field("phone", "Phone number", "tel", "tel"), field("email", "Personal email", "email", "email")],
                [field("college_email", "College email", "email")],
                [field("username", "Username", auto="username", hint="Letters, numbers, dot, underscore")],
                *NEW_PW],
        button="Create account", links=[("Already registered? Log in", "auth.login")]),
    "forgot": dict(eyebrow="Account recovery", title="Reset password",
        sub="Enter your college email or username. The reset link goes to the college email on your account.",
        fields=[[field("identifier", "College email or username")]],
        button="Send reset link", links=[("Back to log in", "auth.login")]),
    "reset": dict(eyebrow="Account recovery", title="New password", sub="Choose a password you have not used here before.",
        fields=[[field("password", "New password", "password", "new-password", PW_HINT)],
                [field("confirm", "Confirm new password", "password", "new-password")]],
        button="Save new password", links=[]),
}

# ---------- the one layout used by every page ----------
THEME_CSS = """
:root{--bg:#070914;--panel:#0e1122;--line:#23263f;--text:#f4f4fb;--mute:#8b90a8;--violet:#8b7cf6;--teal:#5fd8d8;--err:#ff7a8a;--ok:#4ade80}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;color:var(--text);
 font-family:"Segoe UI",system-ui,sans-serif;background:radial-gradient(circle at 15% 10%,#1d1a3d 0,transparent 45%),radial-gradient(circle at 90% 95%,#0d2a2e 0,transparent 40%),var(--bg)}
.shell{width:100%;max-width:560px}
.brand{display:flex;align-items:center;gap:14px;margin-bottom:22px}
.logo{width:46px;height:46px;border-radius:14px;background:linear-gradient(135deg,#b49cff,var(--teal));display:grid;place-items:center}
.logo::after{content:"";width:18px;height:18px;border-radius:50%;border:4px solid #0b0d1a;box-shadow:inset 0 0 0 3px #0b0d1a;background:#0b0d1a}
.brand b{font-size:1.35rem;letter-spacing:-.02em}.brand b i{font-style:normal;color:var(--violet)}
.brand small{display:block;font-size:.62rem;letter-spacing:.3em;color:var(--mute);margin-top:3px}
.card{background:linear-gradient(160deg,#17163a,var(--panel) 60%);border:1px solid var(--line);border-radius:28px;padding:36px}
.eyebrow{font-size:.72rem;font-weight:800;letter-spacing:.22em;text-transform:uppercase;color:var(--violet);margin:0 0 10px}
h1{font-size:2.5rem;line-height:1.05;letter-spacing:-.04em;margin:0 0 10px;font-weight:800}
h1 i{font-style:normal;background:linear-gradient(135deg,#b49cff,var(--teal));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--mute);margin:0 0 26px;line-height:1.55}
form{display:grid;gap:16px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
label{display:grid;gap:7px;font-weight:600;font-size:.88rem}
.hint{font-weight:400;color:var(--mute);font-size:.78rem}
input{font:inherit;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:#0a0c1b;color:var(--text)}
input:focus{outline:2px solid var(--violet);border-color:transparent}
.check{display:flex;align-items:center;gap:9px;font-weight:400;color:var(--mute)}.check input{width:auto}
button{font:inherit;font-weight:700;padding:13px;border:0;border-radius:12px;color:#fff;cursor:pointer;
 background:linear-gradient(135deg,#8b7cf6,#6c5ce7);box-shadow:0 8px 24px #6c5ce755}
button:hover{filter:brightness(1.1)}button:focus-visible,a:focus-visible{outline:2px solid var(--teal);outline-offset:3px}
.links{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-top:22px;font-size:.9rem}
a{color:var(--teal);font-weight:600;text-decoration:none}a:hover{text-decoration:underline}
.msg{padding:12px 14px;border-radius:12px;margin-bottom:18px;font-size:.9rem;border:1px solid}
.msg.error{color:var(--err);border-color:#ff7a8a55;background:#ff7a8a14}
.msg.ok{color:var(--ok);border-color:#4ade8055;background:#4ade8014}
@media(max-width:520px){.card{padding:24px}h1{font-size:2rem}}
"""

LAYOUT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ p.title }} - FaceTrack</title>
<style>{{ css|safe }}</style></head><body><div class="shell">
<div class="brand"><span class="logo"></span><div><b>Face<i>Track</i></b><small>ATTENDANCE OS</small></div></div>
<div class="card">
<p class="eyebrow">{{ p.eyebrow }}</p><h1>{{ p.title }}<i>.</i></h1><p class="sub">{{ p.sub }}</p>
{% for cat, text in messages %}<div class="msg {{ cat }}" role="alert">{{ text }}</div>{% endfor %}
<form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}">
{% for row in p.fields %}<div class="row">{% for f in row %}
<label>{{ f.label }}{% if f.hint %}<span class="hint">{{ f.hint }}</span>{% endif %}
<input name="{{ f.name }}" type="{{ f.kind }}" autocomplete="{{ f.auto }}" required
 value="{{ '' if f.kind == 'password' else form.get(f.name, '') }}"></label>{% endfor %}</div>{% endfor %}
{% if p.remember %}<label class="check"><input type="checkbox" name="remember"> Keep me logged in for 14 days</label>{% endif %}
<button type="submit">{{ p.button }}</button></form>
{% if p.links %}<div class="links">{% for text, endpoint in p.links %}<a href="{{ url_for(endpoint) }}">{{ text }}</a>{% endfor %}</div>{% endif %}
</div></div></body></html>"""


def page(key, form=None):
    return render_template_string(LAYOUT, p=PAGES[key], form=form or {}, css=THEME_CSS,
                                  messages=get_flashed_messages(with_categories=True))


# ---------- helpers ----------
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def csrf_token():
    return session.setdefault("_csrf", secrets.token_hex(16))


def safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else url_for("dashboard")


def password_error(pw, confirm):
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must be 8+ characters with at least one letter and one number."
    return None if pw == confirm else "Passwords do not match."


def validate(spec_key, data):
    """Check required + format rules for every field on a page; return first error or None."""
    for row in PAGES[spec_key]["fields"]:
        for f in row:
            value = data.get(f["name"], "")
            if not value:
                return "Please fill in every field."
            rule = RULES.get(f["name"])
            if rule and not re.fullmatch(rule[0], value):
                return rule[1]
    return None


def send_reset_mail(to_addr, name, link):
    host = os.environ.get("SMTP_HOST")
    if not host:  # dev mode: show the link in the terminal
        print(f"\n[DEV MODE - SMTP not configured] Reset link for {to_addr}:\n{link}\n", flush=True)
        return
    user = os.environ.get("SMTP_USER", "")
    msg = EmailMessage()
    msg["Subject"], msg["To"] = "FaceTrack password reset", to_addr
    msg["From"] = os.environ.get("SMTP_FROM", user)
    msg.set_content(f"Hello {name},\n\nSet a new password here (valid {RESET_MINUTES} minutes, one use):\n\n{link}\n\n"
                    "If you did not ask for this, ignore this email.")
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
        s.starttls()
        if user:
            s.login(user, os.environ.get("SMTP_PASS", ""))
        s.send_message(msg)


def init_auth_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, teacher_code TEXT NOT NULL UNIQUE,
            subject TEXT NOT NULL, phone TEXT NOT NULL, email TEXT NOT NULL,
            college_email TEXT NOT NULL UNIQUE, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS password_resets (
            token_hash TEXT PRIMARY KEY, teacher_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0)""")


# ---------- routes ----------
@bp.route("/signup", methods=["GET", "POST"])
def signup():
    form = {k: v.strip() for k, v in request.form.items()} if request.method == "POST" else {}
    if form:
        error = validate("signup", form) or password_error(form["password"], form["confirm"])
        if not error:
            try:
                with db() as conn:
                    conn.execute("""INSERT INTO teachers (name, teacher_code, subject, phone, email, college_email,
                        username, password_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                        (form["name"], form["teacher_code"], form["subject"], form["phone"], form["email"],
                         form["college_email"].lower(), form["username"], generate_password_hash(form["password"]),
                         datetime.now().isoformat(timespec="seconds")))
                flash("Account created. Log in to continue.", "ok")
                return redirect(url_for("auth.login"))
            except sqlite3.IntegrityError as exc:
                taken = next((w for w in ("username", "teacher_code", "college_email") if w in str(exc)), "college_email")
                error = f"That {taken.replace('_', ' ')} is already registered."
        flash(error, "error")
    return page("signup", form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "teacher_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        ident = request.form.get("identifier", "").strip()
        with db() as conn:
            t = conn.execute("SELECT * FROM teachers WHERE username = ? OR college_email = ?",
                             (ident, ident.lower())).fetchone()
        if t and check_password_hash(t["password_hash"], request.form.get("password", "")):
            session.clear()
            session.update(teacher_id=t["id"], teacher_name=t["name"], _csrf=secrets.token_hex(16))
            session.permanent = bool(request.form.get("remember"))
            return redirect(safe_next(request.args.get("next")))
        flash("Wrong username or password.", "error")
    return page("login")


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "ok")
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        ident = request.form.get("identifier", "").strip()
        with db() as conn:
            t = conn.execute("SELECT * FROM teachers WHERE college_email = ? OR username = ?",
                             (ident.lower(), ident)).fetchone()
            if t:
                token = secrets.token_urlsafe(32)
                conn.execute("INSERT INTO password_resets VALUES (?,?,?,0)",
                             (hashlib.sha256(token.encode()).hexdigest(), t["id"],
                              (datetime.now() + timedelta(minutes=RESET_MINUTES)).isoformat()))
                try:
                    send_reset_mail(t["college_email"], t["name"], url_for("auth.reset", token=token, _external=True))
                except (OSError, smtplib.SMTPException) as exc:
                    print("Reset mail failed:", exc, flush=True)
        flash("If that account exists, a reset link has been sent to its college email.", "ok")
        return redirect(url_for("auth.login"))
    return page("forgot")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset(token):
    with db() as conn:
        row = conn.execute("SELECT * FROM password_resets WHERE token_hash = ? AND used = 0",
                           (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row or datetime.fromisoformat(row["expires_at"]) < datetime.now():
            flash("This reset link is invalid or has expired. Request a new one.", "error")
            return redirect(url_for("auth.forgot"))
        if request.method == "POST":
            error = password_error(request.form.get("password", ""), request.form.get("confirm", ""))
            if error:
                flash(error, "error")
            else:
                conn.execute("UPDATE teachers SET password_hash = ? WHERE id = ?",
                             (generate_password_hash(request.form["password"]), row["teacher_id"]))
                conn.execute("UPDATE password_resets SET used = 1 WHERE teacher_id = ?", (row["teacher_id"],))
                flash("Password changed. Log in with the new password.", "ok")
                return redirect(url_for("auth.login"))
    return page("reset")


# ---------- wiring into the main app ----------
CHIP = ('<div style="position:fixed;right:16px;bottom:16px;z-index:99;display:flex;gap:10px;align-items:center;'
        'padding:8px 14px;border-radius:999px;background:#0e1122;border:1px solid #23263f;color:#f4f4fb;'
        'font:600 13px Segoe UI,sans-serif">{name}<a href="/logout" style="color:#5fd8d8;text-decoration:none">Log out</a></div>')


def init_auth(app):
    """Call once in app.py right after `app = Flask(__name__)` setup."""
    if not KEY_PATH.exists():
        KEY_PATH.write_text(secrets.token_hex(32))
    app.secret_key = KEY_PATH.read_text().strip()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=timedelta(days=14))
    init_auth_db()
    app.register_blueprint(bp)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.context_processor(lambda: {"current_teacher": session.get("teacher_name")})

    @app.before_request
    def guard():
        if request.method == "POST" and request.endpoint in PUBLIC:
            if not secrets.compare_digest(request.form.get("_csrf", ""), session.get("_csrf", "x")):
                abort(400, "Invalid form token. Reload the page and try again.")
        if request.endpoint in PUBLIC or request.endpoint in (None, "static", "auth.logout"):
            return None
        if "teacher_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(ok=False, message="Please log in first."), 401
            return redirect(url_for("auth.login", next=request.path))
        return None

    @app.after_request
    def add_logout_chip(resp):
        """Show 'name / Log out' on dashboard pages without editing their templates."""
        if "teacher_id" in session and resp.mimetype == "text/html" and not (request.endpoint or "").startswith("auth."):
            resp.set_data(resp.get_data(as_text=True).replace(
                "</body>", CHIP.format(name=escape(session.get("teacher_name", ""))) + "</body>", 1))
        return resp