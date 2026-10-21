"""Fill the database with DEMO data so you can see the dashboard and charts.

The companies, roles and dates are made up. Run it only on a throw-away
database, e.g.:  DATABASE=demo.db python seed_demo.py && DATABASE=demo.db python app.py
"""
import os
import random
from contextlib import closing
from datetime import date, timedelta

import db

path = os.environ.get("DATABASE", "demo.db")
db.init_db(path)

random.seed(7)
companies = ["Northwind Retail", "Hanse Logistics", "Elbe Analytics", "Alster Foods", "Port Data GmbH",
             "Nordic Pharma", "Harbor Energy", "Kontor Software", "Fischmarkt Online", "Speicher Supply"]
roles = ["Working Student Data Analytics", "Working Student BI", "Intern Supply Chain Analytics",
         "Working Student Data Science", "Thesis Student Forecasting"]
sources = ["LinkedIn", "LinkedIn", "StepStone", "Indeed", "Company website", "Referral"]
statuses = ["Applied"] * 5 + ["Interview"] * 2 + ["Rejected"] * 3 + ["Accepted"]

with closing(db.connect(path)) as conn:
    for i in range(34):
        day = date.today() - timedelta(days=random.randint(0, 80))
        conn.execute(
            "INSERT INTO applications (company, position, status, date_applied, source, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (random.choice(companies), random.choice(roles), random.choice(statuses),
             day.isoformat(), random.choice(sources), "Demo data"),
        )
    conn.commit()
print(f"Added demo rows to {path}")
