#!/bin/sh
set -e

STAMP_NEEDED=$(
python - <<'PY'
from sqlalchemy import create_engine, inspect

from app.config import settings

engine = create_engine(settings.DATABASE_URL)
inspector = inspect(engine)
tables = set(inspector.get_table_names())
has_existing_app_tables = bool({"targets", "molecules", "reports"} & tables)
has_alembic_version = "alembic_version" in tables

print("yes" if has_existing_app_tables and not has_alembic_version else "no")
PY
)

if [ "$STAMP_NEEDED" = "yes" ]; then
  echo "Stamping existing database schema as 001_init before upgrade..."
  alembic stamp 001_init
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
