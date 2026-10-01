"""Tests for the additive column auto-migration that runs on every start.

Self-hosted instances upgrade with ``docker compose up --build`` and never run
Alembic, so a column added in a new release must be created at startup;
otherwise every query on that table fails (the 2.4.0 login 500).
"""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, create_engine, func, inspect, text
from sqlalchemy.dialects import postgresql, sqlite

import app.main as main_module
from app.config import settings
from app.database import Base

# (table, column) pairs dropped to simulate a database created by an older release
_DROPPED = [("users", "token_version"), ("users", "created_at"), ("resources", "imported")]


def _old_schema_engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        for table, column in _DROPPED:
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        conn.execute(text(
            "INSERT INTO users (email, hashed_password, display_name, role, is_active, language_code) "
            "VALUES ('old@example.com', 'x', 'Old User', 'member', 1, 'en')"
        ))
    return eng


def test_adds_missing_columns_and_backfills_defaults(tmp_path):
    eng = _old_schema_engine(tmp_path)

    added = main_module._add_missing_columns(eng)

    assert set(added) == {f"{t}.{c}" for t, c in _DROPPED}
    columns = {c["name"] for c in inspect(eng).get_columns("users")}
    assert {"token_version", "created_at"} <= columns
    with eng.connect() as conn:
        # Existing rows get the model default, so token checks keep working
        assert conn.execute(text("SELECT token_version FROM users")).scalar_one() == 0


def test_second_run_is_a_no_op(tmp_path):
    eng = _old_schema_engine(tmp_path)
    main_module._add_missing_columns(eng)
    assert main_module._add_missing_columns(eng) == []


def test_runs_on_startup_in_production_mode(monkeypatch):
    monkeypatch.setattr(settings, "debug", False)
    with patch.object(main_module, "_add_missing_columns", return_value=[]) as mock_add:
        with TestClient(main_module.app):
            pass
    mock_add.assert_called_once()


def test_default_rendering_per_dialect():
    meta = MetaData()
    table = Table(
        "t", meta,
        Column("flag", Boolean, default=False),
        Column("count", Integer, default=0),
        Column("label", String(10), server_default="none"),
        Column("seen_at", DateTime, server_default=func.now()),
        Column("computed", Integer, default=lambda: 1),
    )
    pg, lite = postgresql.dialect(), sqlite.dialect()
    render = main_module._column_default_sql

    assert render(table.c.flag, pg) == " DEFAULT false"
    assert render(table.c.flag, lite) == " DEFAULT 0"
    assert render(table.c.count, pg) == " DEFAULT 0"
    assert render(table.c.label, pg) == " DEFAULT 'none'"
    assert render(table.c.seen_at, pg) == " DEFAULT now()"
    # Python-side callables cannot be expressed in DDL; the column is added without a default
    assert render(table.c.computed, pg) == ""
