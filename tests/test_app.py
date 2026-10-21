import io
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analytics  # noqa: E402
import db  # noqa: E402
from app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    app.config["TESTING"] = True
    return app.test_client()


def add(client, **overrides):
    data = {
        "company": "Acme GmbH", "position": "Working Student Data",
        "status": "Applied", "date_applied": date.today().isoformat(),
        "source": "LinkedIn", "notes": "",
    }
    data.update(overrides)
    return client.post("/add", data=data, follow_redirects=True)


# ---------- pages and CRUD ----------

def test_pages_load_when_empty(client):
    for path in ["/", "/applications", "/add", "/analytics", "/api/stats", "/export.csv"]:
        assert client.get(path).status_code == 200


def test_add_application(client):
    response = add(client)
    assert b"Application added." in response.data
    assert b"Acme GmbH" in response.data


@pytest.mark.parametrize("bad", [
    {"company": ""},
    {"position": "   "},
    {"status": "Hired"},
    {"date_applied": "21.10.2026"},
])
def test_add_rejects_invalid_input(client, bad):
    response = add(client, **bad)
    assert response.status_code == 400
    assert b"Application added." not in response.data
    # nothing was saved
    assert b"No applications found." in client.get("/applications").data


def test_edit_application(client):
    add(client)
    response = client.post(
        "/edit/1",
        data={"company": "Acme GmbH", "position": "Data Analyst Intern", "status": "Interview",
              "date_applied": date.today().isoformat(), "source": "Referral", "notes": "Phone screen"},
        follow_redirects=True,
    )
    assert b"Application updated." in response.data
    assert b"Data Analyst Intern" in response.data
    assert b"Interview" in response.data


def test_edit_missing_application_returns_404(client):
    assert client.get("/edit/999").status_code == 404


def test_delete_requires_post_and_deletes(client):
    add(client)
    assert client.get("/delete/1").status_code == 405
    response = client.post("/delete/1", follow_redirects=True)
    assert b"Application deleted." in response.data
    assert b"Acme GmbH" not in response.data


def test_search_and_status_filter(client):
    add(client, company="Alpha", status="Applied")
    add(client, company="Beta", status="Interview")
    assert b"Alpha" in client.get("/applications?q=alp").data
    assert b"Beta" not in client.get("/applications?q=alp").data
    filtered = client.get("/applications?status=Interview").data
    assert b"Beta" in filtered and b"Alpha" not in filtered


def test_sql_injection_attempt_is_harmless(client):
    add(client)
    response = client.get("/applications?q=' OR 1=1 --")
    assert response.status_code == 200
    assert b"Acme GmbH" not in response.data


def test_html_is_escaped(client):
    add(client, company="<script>alert(1)</script>")
    page = client.get("/applications").data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;" in page


# ---------- CSV ----------

def test_export_and_import_roundtrip(client):
    add(client, company="Alpha", status="Applied")
    add(client, company="Beta", status="Rejected")
    exported = client.get("/export.csv").data
    assert exported.splitlines()[0] == b"company,position,status,date_applied,source,notes"

    for _ in (1, 2):
        client.post("/delete/" + str(_))
    response = client.post(
        "/import",
        data={"file": (io.BytesIO(exported), "backup.csv")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert b"Imported 2 applications, skipped 0 invalid rows." in response.data


def test_import_skips_invalid_rows(client):
    csv_text = ("company,position,status\n"
                "Good Co,Intern,Applied\n"
                "Bad Co,Intern,NotAStatus\n"
                ",Intern,Applied\n")
    response = client.post(
        "/import",
        data={"file": (io.BytesIO(csv_text.encode()), "x.csv")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert b"Imported 1 applications, skipped 2 invalid rows." in response.data


def test_import_rejects_wrong_file_and_missing_columns(client):
    wrong = client.post("/import", data={"file": (io.BytesIO(b"x"), "x.txt")},
                        content_type="multipart/form-data", follow_redirects=True)
    assert b"Please choose a .csv file." in wrong.data
    missing = client.post("/import", data={"file": (io.BytesIO(b"a,b\n1,2\n"), "x.csv")},
                          content_type="multipart/form-data", follow_redirects=True)
    assert b"CSV needs the columns" in missing.data


def test_export_blocks_formula_injection(client):
    add(client, company="=HYPERLINK(\"http://evil\")")
    body = client.get("/export.csv").data.decode()
    assert "'=HYPERLINK" in body


# ---------- analytics ----------

def rows(*statuses, dates=None, sources=None):
    out = []
    for i, s in enumerate(statuses):
        out.append({
            "status": s,
            "date_applied": (dates[i] if dates else None),
            "source": (sources[i] if sources else None),
        })
    return out


def test_summary_rates():
    s = analytics.summary(rows("Applied", "Applied", "Interview", "Accepted", "Rejected"))
    assert s["total"] == 5
    assert s["response_rate"] == 60      # 3 of 5 got an answer
    assert s["interview_rate"] == 40     # interview + accepted
    assert s["offer_rate"] == 20
    assert s["funnel"] == [("Applications", 5), ("Interview or later", 2), ("Offers", 1)]


def test_summary_empty_has_no_division_error():
    s = analytics.summary([])
    assert s["total"] == 0 and s["response_rate"] == 0 and s["offer_rate"] == 0


def test_weekly_counts_buckets_by_monday():
    today = date(2026, 10, 21)  # Wednesday
    monday = today - timedelta(days=2)
    data = rows("Applied", "Applied", "Applied", "Applied",
                dates=[monday.isoformat(), today.isoformat(),
                       (monday - timedelta(weeks=1)).isoformat(), None])
    labels, values = analytics.weekly_counts(data, weeks=4, today=today)
    assert len(labels) == len(values) == 4
    assert values[-1] == 2 and values[-2] == 1 and sum(values) == 3


def test_weekly_counts_ignores_dates_outside_window():
    today = date(2026, 10, 21)
    old = (today - timedelta(weeks=30)).isoformat()
    _, values = analytics.weekly_counts(rows("Applied", dates=[old]), weeks=12, today=today)
    assert sum(values) == 0


def test_by_source_counts_and_unknown():
    labels, values = analytics.by_source(
        rows("Applied", "Applied", "Applied", sources=["LinkedIn", "LinkedIn", None]))
    assert labels[0] == "LinkedIn" and values[0] == 2
    assert "Unknown" in labels


# ---------- migration ----------

def test_old_database_is_migrated_and_keeps_data(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "company TEXT NOT NULL, position TEXT NOT NULL, status TEXT NOT NULL)")
    conn.execute("INSERT INTO applications (company, position, status) VALUES ('Old Co','Intern','Applied')")
    conn.commit()
    conn.close()

    db.init_db(path)
    db.init_db(path)  # running twice must be safe

    conn = db.connect(path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}
    row = conn.execute("SELECT * FROM applications").fetchone()
    conn.close()
    assert {"date_applied", "source", "notes"} <= cols
    assert row["company"] == "Old Co" and row["date_applied"] is None

    app = create_app(path)
    app.config["TESTING"] = True
    assert b"Old Co" in app.test_client().get("/applications").data
