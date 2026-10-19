from pathlib import Path
from contextlib import contextmanager
import secrets
import sqlite3

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


app = Flask(__name__)

app.secret_key = secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("Employee@123")

DATABASE = Path(__file__).resolve().parent / "employees.db"


@contextmanager
def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with get_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                department TEXT NOT NULL,
                designation TEXT NOT NULL,
                salary REAL NOT NULL CHECK (salary >= 0),
                joining_date TEXT NOT NULL
            )
        """)


@app.before_request
def require_login():
    public_pages = {"login", "static"}

    if request.endpoint is None:
        return None

    if request.endpoint not in public_pages:
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))

    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_logged_in"):
        return redirect(url_for("home"))

    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if (
            username == ADMIN_USERNAME
            and check_password_hash(ADMIN_PASSWORD_HASH, password)
        ):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("home"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def home():
    search = request.args.get("search", "").strip()

    with get_db() as connection:
        employees = connection.execute("""
            SELECT * FROM employees
            WHERE name LIKE ? OR department LIKE ?
            ORDER BY id DESC
        """, (
            f"%{search}%",
            f"%{search}%"
        )).fetchall()

        total = connection.execute(
            "SELECT COUNT(*) FROM employees"
        ).fetchone()[0]

        departments = connection.execute(
            "SELECT COUNT(DISTINCT department) FROM employees"
        ).fetchone()[0]

    return render_template(
        "index.html",
        employees=employees,
        total=total,
        departments=departments,
        search=search,
        error=request.args.get("error", "")
    )


@app.route("/add", methods=["POST"])
def add_employee():
    fields = [
        "name",
        "email",
        "phone",
        "department",
        "designation",
        "salary",
        "joining_date"
    ]

    data = {
        field: request.form.get(field, "").strip()
        for field in fields
    }

    if not all(data.values()):
        return redirect(
            url_for("home", error="Fill in all fields.")
        )

    try:
        salary = float(data["salary"])

        if not 0 <= salary <= 1_000_000_000:
            raise ValueError

    except ValueError:
        return redirect(
            url_for(
                "home",
                error="Enter a valid non-negative salary."
            )
        )

    try:
        with get_db() as connection:
            connection.execute("""
                INSERT INTO employees (
                    name,
                    email,
                    phone,
                    department,
                    designation,
                    salary,
                    joining_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data["name"],
                data["email"].lower(),
                data["phone"],
                data["department"],
                data["designation"],
                salary,
                data["joining_date"]
            ))

    except sqlite3.IntegrityError:
        return redirect(
            url_for(
                "home",
                error="This email is already registered."
            )
        )

    return redirect(url_for("home"))


@app.route("/edit/<int:employee_id>", methods=["GET", "POST"])
def edit_employee(employee_id):
    with get_db() as connection:
        employee = connection.execute(
            "SELECT * FROM employees WHERE id = ?",
            (employee_id,)
        ).fetchone()

    if employee is None:
        return "Employee not found", 404

    error = ""

    if request.method == "POST":
        fields = [
            "name",
            "email",
            "phone",
            "department",
            "designation",
            "salary",
            "joining_date"
        ]

        data = {
            field: request.form.get(field, "").strip()
            for field in fields
        }

        salary = None

        if not all(data.values()):
            error = "Fill in all fields."
        else:
            try:
                salary = float(data["salary"])

                if not 0 <= salary <= 1_000_000_000:
                    raise ValueError

            except ValueError:
                error = "Enter a valid non-negative salary."

        if not error:
            try:
                with get_db() as connection:
                    connection.execute("""
                        UPDATE employees
                        SET name = ?,
                            email = ?,
                            phone = ?,
                            department = ?,
                            designation = ?,
                            salary = ?,
                            joining_date = ?
                        WHERE id = ?
                    """, (
                        data["name"],
                        data["email"].lower(),
                        data["phone"],
                        data["department"],
                        data["designation"],
                        salary,
                        data["joining_date"],
                        employee_id
                    ))

                return redirect(url_for("home"))

            except sqlite3.IntegrityError:
                error = "This email belongs to another employee."

        employee = {"id": employee_id, **data}

    return render_template(
        "edit.html",
        employee=employee,
        error=error
    )


@app.route("/delete/<int:employee_id>", methods=["POST"])
def delete_employee(employee_id):
    with get_db() as connection:
        connection.execute(
            "DELETE FROM employees WHERE id = ?",
            (employee_id,)
        )

    return redirect(url_for("home"))


initialize_database()

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)