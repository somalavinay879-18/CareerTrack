"""Create (or migrate) the local database. The app also does this on start-up."""
import os

import db

path = os.environ.get("DATABASE", "database.db")
db.init_db(path)
print(f"Database ready: {path}")
