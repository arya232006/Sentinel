"""SQLite repository. Synchronous by design: SQLite writes are fast enough
that async buys nothing here, and it keeps the graph nodes simple.

There is deliberately no update_scope / delete_scope. Scopes are write-once.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentinel.config import DB_PATH, ROOT
from sentinel.scope.models import Scope

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_db_path: Path = DB_PATH


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    global _conn, _db_path
    with _lock:
        if path is not None and Path(path) != _db_path:
            if _conn is not None:
                _conn.close()
            _conn = None
            _db_path = Path(path)
        if _conn is None:
            _conn = sqlite3.connect(str(_db_path), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys = ON")
            _conn.executescript((ROOT / "sentinel" / "store" / "schema.sql").read_text())
            _conn.commit()
        return _conn


def reset(path: Path | str) -> None:
    """Test helper: point the repo at a fresh database."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
    connect(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- scopes ---
def insert_scope(scope: Scope) -> None:
    conn = connect()
    conn.execute(
        """INSERT INTO scopes (scope_id, target_id, target_endpoint, payload_json,
                               signed_hash, authorizer, expiry_timestamp, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            scope.scope_id,
            scope.target_id,
            scope.target_endpoint,
            json.dumps(scope.hashed_payload()),
            scope.signed_hash,
            scope.authorizer,
            scope.expiry_timestamp.isoformat(),
            scope.created_at.isoformat(),
        ),
    )
    conn.commit()


def get_scope(scope_id: str) -> Scope | None:
    row = connect().execute(
        "SELECT payload_json, signed_hash FROM scopes WHERE scope_id = ?", (scope_id,)
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload_json"])
    return Scope(**payload, signed_hash=row["signed_hash"])


def list_scopes() -> list[dict[str, Any]]:
    rows = connect().execute(
        "SELECT scope_id, target_id, authorizer, expiry_timestamp, created_at "
        "FROM scopes ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ runs ---
def insert_run(run_id: str, scope_id: str, budget: dict) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO runs (run_id, scope_id, status, started_at, budget_json) "
        "VALUES (?,?,?,?,?)",
        (run_id, scope_id, "running", _now(), json.dumps(budget)),
    )
    conn.commit()


def update_run(
    run_id: str, status: str, budget: dict, abort_reason: str | None = None
) -> None:
    conn = connect()
    ended = _now() if status in ("completed", "aborted") else None
    conn.execute(
        "UPDATE runs SET status=?, budget_json=?, abort_reason=?, "
        "ended_at=COALESCE(?, ended_at) WHERE run_id=?",
        (status, json.dumps(budget), abort_reason, ended, run_id),
    )
    conn.commit()


def get_run(run_id: str) -> dict[str, Any] | None:
    row = connect().execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return dict(row) if row else None


# -------------------------------------------------------------- findings ---
def insert_finding(run_id: str, finding: dict) -> None:
    conn = connect()
    conn.execute(
        """INSERT OR REPLACE INTO findings
           (finding_id, run_id, attack_category, severity, confirmed, provenance,
            minimized_prompt, mitigation, finding_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            finding["finding_id"],
            run_id,
            finding.get("attack_category", ""),
            float(finding.get("severity", 0.0)),
            1 if finding.get("confirmed") else 0,
            finding.get("provenance", "live"),
            finding.get("minimized_prompt"),
            finding.get("mitigation"),
            json.dumps(finding),
            _now(),
        ),
    )
    conn.commit()


def list_findings(run_id: str) -> list[dict[str, Any]]:
    rows = connect().execute(
        "SELECT finding_json FROM findings WHERE run_id=? ORDER BY severity DESC",
        (run_id,),
    ).fetchall()
    return [json.loads(r["finding_json"]) for r in rows]


# ----------------------------------------------------------------- trace ---
def insert_trace(run_id: str, entry: dict) -> None:
    conn = connect()
    conn.execute(
        """INSERT INTO trace_entries
           (run_id, node, model, ts, latency_ms, tokens_in, tokens_out, usd,
            input_json, output_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            entry["node"],
            entry["model"],
            entry["ts"],
            int(entry["latency_ms"]),
            int(entry["tokens_in"]),
            int(entry["tokens_out"]),
            float(entry["usd"]),
            json.dumps(entry.get("input"))[:20000],
            json.dumps(entry.get("output"))[:20000],
        ),
    )
    conn.commit()


def list_trace(run_id: str) -> list[dict[str, Any]]:
    rows = connect().execute(
        "SELECT * FROM trace_entries WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ----------------------------------------------------------- interceptor ---
def insert_interception(run_id: str, call: dict) -> None:
    conn = connect()
    conn.execute(
        """INSERT INTO interceptor_log
           (run_id, attack_id, turn, tool_name, arguments_json, executed,
            result_json, flagged, flag_reason, ts)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            call.get("attack_id"),
            call.get("turn"),
            call["tool_name"],
            json.dumps(call.get("arguments", {})),
            1 if call.get("executed") else 0,
            json.dumps(call.get("result")),
            1 if call.get("flagged") else 0,
            call.get("flag_reason"),
            call.get("ts", _now()),
        ),
    )
    conn.commit()


# ------------------------------------------------------ attack patterns ---
def get_patterns(target_type: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    if target_type:
        rows = conn.execute(
            "SELECT * FROM attack_patterns WHERE target_type=? ORDER BY success_rate DESC",
            (target_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM attack_patterns ORDER BY success_rate DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def record_pattern_outcome(
    attack_pattern: str, target_type: str, success: bool
) -> None:
    """Called once per attack after the report gate approves, so a rejected
    report cannot poison cross-run learning."""
    conn = connect()
    conn.execute(
        """INSERT INTO attack_patterns (attack_pattern, target_type, attempts,
                                        successes, success_rate, updated_at)
           VALUES (?,?,1,?,?,?)
           ON CONFLICT(attack_pattern, target_type) DO UPDATE SET
             attempts = attempts + 1,
             successes = successes + excluded.successes,
             success_rate = CAST(successes + excluded.successes AS REAL)
                            / (attempts + 1),
             updated_at = excluded.updated_at""",
        (
            attack_pattern,
            target_type,
            1 if success else 0,
            1.0 if success else 0.0,
            _now(),
        ),
    )
    conn.commit()


# -------------------------------------------------- learned techniques ---
def insert_learned_technique(entry: dict[str, Any]) -> bool:
    """Persist a technique discovered by a run. Returns False if the id was
    already taken, which is the last-line dedupe behind the novelty check."""
    conn = connect()
    cur = conn.execute(
        """INSERT OR IGNORE INTO learned_techniques
           (id, category, name, exploits, mechanism, signals_json,
            novelty_reasoning, provenance, source_run_id, source_finding_id,
            source_target, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            entry["id"],
            entry["category"],
            entry["name"],
            entry["exploits"],
            entry["mechanism"],
            json.dumps(entry.get("signals_of_susceptibility", [])),
            entry.get("novelty_reasoning", ""),
            entry.get("provenance", "live"),
            entry.get("source_run_id", ""),
            entry.get("source_finding_id", ""),
            entry.get("source_target", ""),
            _now(),
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def list_learned_techniques(
    provenance: str | None = None, category: str | None = None
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM learned_techniques"
    where, params = [], []
    if provenance:
        where.append("provenance = ?")
        params.append(provenance)
    if category:
        where.append("category = ?")
        params.append(category)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at"

    out = []
    for r in connect().execute(sql, params).fetchall():
        row = dict(r)
        row["signals_of_susceptibility"] = json.loads(row.pop("signals_json") or "[]")
        row["learned"] = True
        out.append(row)
    return out


SEED_PATTERNS = [
    ("authority_impersonation", "support_bot", 7, 5),
    ("multiturn_erosion", "support_bot", 9, 6),
    ("direct_jailbreak", "support_bot", 11, 2),
    ("tool_parameter_hijacking", "tool_agent", 6, 4),
    ("direct_jailbreak", "tool_agent", 8, 1),
    ("rag_context_poisoning", "rag_agent", 5, 4),
    ("indirect_injection", "rag_agent", 7, 5),
    ("multiturn_erosion", "rag_agent", 4, 1),
]


def seed_patterns() -> None:
    """Seeded so the planner's retrieval returns something on run #1."""
    conn = connect()
    for pattern, target, attempts, successes in SEED_PATTERNS:
        conn.execute(
            """INSERT OR IGNORE INTO attack_patterns
               (attack_pattern, target_type, attempts, successes, success_rate, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (pattern, target, attempts, successes, successes / attempts, _now()),
        )
    conn.commit()
