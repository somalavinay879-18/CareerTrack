import csv
import io
import os
from contextlib import closing
from datetime import date

from flask import (
    Flask, Response, abort, flash, jsonify, redirect,
    render_template, request, url_for,
)

import analytics
import db

STATUSES = analytics.STATUSES
SOURCES = ["LinkedIn", "StepStone", "Indeed", "Company website", "Referral", "Other"]
CSV_COLUMNS = ["company", "position", "status", "date_applied", "source", "notes"]
MAX_IMPORT_ROWS = 2000


def create_app(database=None):
    app = Flask(__name__)
    app.config["DATABASE"] = database or os.environ.get("DATABASE", "database.db")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024  # 1 MB upload limit
    db.init_db(app.config["DATABASE"])

    def connect():
        return db.connect(app.config["DATABASE"])

    def all_rows():
        with closing(connect()) as conn:
            return conn.execute("SELECT * FROM applications ORDER BY id DESC").fetchall()

    def validate(form):
        """Return (clean_values, errors) for the add/edit form or a CSV row."""
        company = (form.get("company") or "").strip()
        position = (form.get("position") or "").strip()
        status = (form.get("status") or "").strip()
        source = (form.get("source") or "").strip()[:60]
        notes = (form.get("notes") or "").strip()[:1000]
        raw_date = (form.get("date_applied") or "").strip()
        errors = []
        if not company or len(company) > 120:
            errors.append("Company is required (max 120 characters).")
        if not position or len(position) > 120:
            errors.append("Position is required (max 120 characters).")
        if status not in STATUSES:
            errors.append("Status must be one of: " + ", ".join(STATUSES) + ".")
        if raw_date:
            parsed = analytics.parse_date(raw_date)
            if parsed is None:
                errors.append("Date must look like 2026-10-21.")
        else:
            parsed = date.today()
        values = {
            "company": company, "position": position, "status": status,
            "date_applied": parsed.isoformat() if parsed else raw_date,
            "source": source, "notes": notes,
        }
        return values, errors

    @app.route("/")
    def dashboard():
        rows = all_rows()
        return render_template(
            "dashboard.html", stats=analytics.summary(rows), recent=rows[:5]
        )

    @app.route("/applications")
    def applications():
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()
        sql = "SELECT * FROM applications WHERE 1=1"
        params = []
        if q:
            sql += " AND (company LIKE ? OR position LIKE ?)"
            params += [f"%{q}%", f"%{q}%"]
        if status in STATUSES:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id DESC"
        with closing(connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return render_template(
            "applications.html", applications=rows, q=q, status=status, statuses=STATUSES
        )

    @app.route("/add", methods=["GET", "POST"])
    def add_application():
        if request.method == "POST":
            values, errors = validate(request.form)
            if errors:
                for e in errors:
                    flash(e, "danger")
                return render_template(
                    "form.html", item=values, statuses=STATUSES, sources=SOURCES, mode="add"
                ), 400
            with closing(connect()) as conn:
                conn.execute(
                    "INSERT INTO applications (company, position, status, date_applied, source, notes) "
                    "VALUES (:company, :position, :status, :date_applied, :source, :notes)",
                    values,
                )
                conn.commit()
            flash("Application added.", "success")
            return redirect(url_for("applications"))
        item = {"date_applied": date.today().isoformat(), "status": "Applied"}
        return render_template(
            "form.html", item=item, statuses=STATUSES, sources=SOURCES, mode="add"
        )

    @app.route("/edit/<int:app_id>", methods=["GET", "POST"])
    def edit_application(app_id):
        with closing(connect()) as conn:
            row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            abort(404)
        if request.method == "POST":
            values, errors = validate(request.form)
            if errors:
                for e in errors:
                    flash(e, "danger")
                values["id"] = app_id
                return render_template(
                    "form.html", item=values, statuses=STATUSES, sources=SOURCES, mode="edit"
                ), 400
            values["id"] = app_id
            with closing(connect()) as conn:
                conn.execute(
                    "UPDATE applications SET company=:company, position=:position, status=:status, "
                    "date_applied=:date_applied, source=:source, notes=:notes WHERE id=:id",
                    values,
                )
                conn.commit()
            flash("Application updated.", "success")
            return redirect(url_for("applications"))
        return render_template(
            "form.html", item=dict(row), statuses=STATUSES, sources=SOURCES, mode="edit"
        )

    @app.route("/delete/<int:app_id>", methods=["POST"])
    def delete_application(app_id):
        with closing(connect()) as conn:
            conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
            conn.commit()
        flash("Application deleted.", "secondary")
        return redirect(url_for("applications"))

    @app.route("/analytics")
    def analytics_page():
        rows = all_rows()
        week_labels, week_values = analytics.weekly_counts(rows)
        source_labels, source_values = analytics.by_source(rows)
        return render_template(
            "analytics.html",
            stats=analytics.summary(rows),
            week_labels=week_labels, week_values=week_values,
            source_labels=source_labels, source_values=source_values,
        )

    @app.route("/api/stats")
    def api_stats():
        stats = analytics.summary(all_rows())
        stats["funnel"] = [{"stage": s, "count": c} for s, c in stats["funnel"]]
        return jsonify(stats)

    def _safe_cell(value):
        """Stop spreadsheet formula injection when the CSV is opened in Excel."""
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text

    @app.route("/export.csv")
    def export_csv():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        for r in reversed(all_rows()):
            writer.writerow([_safe_cell(r[c]) for c in CSV_COLUMNS])
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=careertrack_applications.csv"},
        )

    @app.route("/import", methods=["POST"])
    def import_csv():
        file = request.files.get("file")
        if not file or not file.filename.lower().endswith(".csv"):
            flash("Please choose a .csv file.", "danger")
            return redirect(url_for("applications"))
        try:
            text = file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            flash("The file must be UTF-8 encoded.", "danger")
            return redirect(url_for("applications"))
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or not {"company", "position", "status"} <= set(reader.fieldnames):
            flash("CSV needs the columns: company, position, status "
                  "(optional: date_applied, source, notes).", "danger")
            return redirect(url_for("applications"))
        imported = skipped = 0
        with closing(connect()) as conn:
            for i, row in enumerate(reader):
                if i >= MAX_IMPORT_ROWS:
                    break
                values, errors = validate(row)
                if errors:
                    skipped += 1
                    continue
                conn.execute(
                    "INSERT INTO applications (company, position, status, date_applied, source, notes) "
                    "VALUES (:company, :position, :status, :date_applied, :source, :notes)",
                    values,
                )
                imported += 1
            conn.commit()
        flash(f"Imported {imported} applications, skipped {skipped} invalid rows.", "success")
        return redirect(url_for("applications"))

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
