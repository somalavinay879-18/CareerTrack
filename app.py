from flask import Flask, render_template, request, redirect
import sqlite3
import os


app = Flask(__name__)


@app.route("/")
def dashboard():

    connection = sqlite3.connect("database.db")
    cursor = connection.cursor()

    # Total applications
    cursor.execute("SELECT COUNT(*) FROM applications")
    total = cursor.fetchone()[0]

    # Applied
    cursor.execute(
        "SELECT COUNT(*) FROM applications WHERE status='Applied'"
    )
    applied = cursor.fetchone()[0]

    # Interview
    cursor.execute(
        "SELECT COUNT(*) FROM applications WHERE status='Interview'"
    )
    interview = cursor.fetchone()[0]

    # Accepted
    cursor.execute(
        "SELECT COUNT(*) FROM applications WHERE status='Accepted'"
    )
    accepted = cursor.fetchone()[0]

    # Rejected
    cursor.execute(
        "SELECT COUNT(*) FROM applications WHERE status='Rejected'"
    )
    rejected = cursor.fetchone()[0]

    # Recent applications
    cursor.execute(
        """
        SELECT *
        FROM applications
        ORDER BY id DESC
        LIMIT 5
        """
    )
    recent = cursor.fetchall()

    connection.close()

    # Success rate
    success_rate = 0

    if total > 0:
        success_rate = round((accepted / total) * 100)

    return render_template(
        "dashboard.html",
        total=total,
        applied=applied,
        interview=interview,
        accepted=accepted,
        rejected=rejected,
        recent=recent,
        success_rate=success_rate
    )


@app.route("/applications")
def applications():

    connection = sqlite3.connect("database.db")
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM applications")
    applications = cursor.fetchall()

    connection.close()

    return render_template(
        "applications.html",
        applications=applications
    )


@app.route("/add", methods=["GET", "POST"])
def add_application():

    if request.method == "POST":

        company = request.form["company"]
        position = request.form["position"]
        status = request.form["status"]

        connection = sqlite3.connect("database.db")
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO applications
            (company, position, status)
            VALUES (?, ?, ?)
            """,
            (company, position, status)
        )

        connection.commit()
        connection.close()

        return redirect("/applications")

    return render_template("add_application.html")


@app.route("/delete/<int:id>")
def delete_application(id):

    connection = sqlite3.connect("database.db")
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM applications WHERE id = ?",
        (id,)
    )

    connection.commit()
    connection.close()

    return redirect("/applications")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False
    )