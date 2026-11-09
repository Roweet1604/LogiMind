"""The admin CLI (manage.py): a new tenant's key is printed once, works for sign-in, and is never stored in
plain text; a revoked key stops working."""
import re
import sqlite3

import manage
from app.db.keys import authenticate, hash_key
from app.db.session import admin_session, make_engine, make_session_factory

KEY_RE = re.compile(r"lm_[A-Za-z0-9]+_[A-Za-z0-9_-]+")


def _db(tmp_path, monkeypatch):
    path = tmp_path / "cli.db"
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setenv("LOGIMIND_DATABASE_URL", url)
    return path, url


def _auth(url, key):
    engine = make_engine(url)
    try:
        with admin_session(make_session_factory(engine)) as s:
            return authenticate(s, key)
    finally:
        engine.dispose()


def test_create_tenant_prints_the_key_once_and_stores_only_its_hash(tmp_path, monkeypatch, capsys):
    path, url = _db(tmp_path, monkeypatch)
    assert manage.main(["create-tenant", "Synthetic Test Fleet"]) == 0
    out = capsys.readouterr().out
    keys = KEY_RE.findall(out)
    assert len(keys) == 1                      # printed exactly once
    key = keys[0]
    tenant_id = re.search(r"tenant_id=(ten-[0-9a-f]+)", out).group(1)

    principal = _auth(url, key)                # the printed key signs in as the new tenant
    assert principal is not None and principal.tenant_id == tenant_id

    assert key.encode() not in path.read_bytes()   # never written to the database file in plain text
    with sqlite3.connect(path) as con:
        rows = con.execute("SELECT * FROM api_keys").fetchall()
    assert len(rows) == 1
    assert hash_key(key) in rows[0]
    assert not any(isinstance(v, str) and key in v for v in rows[0])


def test_issue_and_revoke_key(tmp_path, monkeypatch, capsys):
    _, url = _db(tmp_path, monkeypatch)
    manage.main(["create-tenant", "Synthetic Test Fleet"])
    tenant_id = re.search(r"tenant_id=(ten-[0-9a-f]+)", capsys.readouterr().out).group(1)

    assert manage.main(["issue-key", tenant_id, "second"]) == 0
    out = capsys.readouterr().out
    (key,) = KEY_RE.findall(out)
    key_id = re.search(r"key_id=(\S+)", out).group(1)
    assert _auth(url, key).tenant_id == tenant_id

    assert manage.main(["revoke-key", key_id]) == 0
    assert _auth(url, key) is None


def test_usage_without_arguments(capsys):
    assert manage.main([]) == 2
    assert "create-tenant" in capsys.readouterr().out
