#!/usr/bin/env python3
"""
CIQ Data Copy Tool V3
Trigger an async data copy between Databricks environments, poll until done,
and emit verification SQL for Claude to run via dbx MCP.

Base URL: https://db-admin-tools.prod.commerceiq.ai

Usage:
  python data_copy_v3.py request.json
  python data_copy_v3.py request.json --poll-interval 60 --timeout 7200
  python data_copy_v3.py request.json --skip-poll          # trigger-only
  python data_copy_v3.py request.json --request-id <id>   # poll existing request
  cat request.json | python data_copy_v3.py -

Exit codes: 0=COMPLETED, 2=PARTIALLY_COMPLETE, 3=FAILED, 1=error/timeout
"""

import json
import sys
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE_URL = "https://db-admin-tools.prod.commerceiq.ai"
TERMINAL_STATES = {"COMPLETED", "PARTIALLY_COMPLETE", "FAILED"}
DEFAULT_USER = "suman.y@commerceiq.ai"
DEFAULT_POLL_INTERVAL = 30   # seconds between polls
DEFAULT_TIMEOUT = 7200       # 2 hours max wait


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _to_api_payload(request: Dict) -> Dict:
    """
    Convert a snake_case config into the actual API wire format.

    The V3 API has MIXED casing (verified by testing):
    - Top-level keys: camelCase  (sourceEnv, targetEnv, requestedBy)
    - tables[] item keys: snake_case  (table_name, copy_mode, date_filter, …)

    So tables[] passes through unchanged from the user config, only the
    three top-level fields need renaming.
    """
    tables = []
    for t in request.get("tables", []):
        t_copy = dict(t)
        if "clients" in t_copy and "client_ids" not in t_copy:
            t_copy["client_ids"] = t_copy.pop("clients")
        tables.append(t_copy)

    return {
        "source_env": request["source_env"],
        "target_env": request["target_env"],
        "requested_by": request.get("requested_by", DEFAULT_USER),
        "tables": tables,
    }


def _http(method: str, path: str, body: Optional[Dict] = None,
          token: Optional[str] = None) -> Dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection error: {e.reason}") from e


# ---------------------------------------------------------------------------
# API operations
# ---------------------------------------------------------------------------

def trigger_copy(request: Dict, token: Optional[str] = None) -> str:
    """POST /v1/copy-data/trigger — returns request_id.

    NOTE: The V3 API expects camelCase keys despite the Confluence docs showing
    snake_case. _to_api_payload() handles the conversion.
    """
    payload = _to_api_payload(request)
    resp = _http("POST", "/v1/copy-data/trigger", payload, token)
    return resp["request_id"]


def get_status(request_id: str, token: Optional[str] = None) -> Dict:
    """GET /v1/copy-data/status/{requestId}."""
    return _http("GET", f"/v1/copy-data/status/{request_id}", token=token)


def poll_until_done(request_id: str,
                    token: Optional[str] = None,
                    interval: int = DEFAULT_POLL_INTERVAL,
                    timeout: int = DEFAULT_TIMEOUT) -> Dict:
    """Poll status until a terminal state is reached or timeout expires."""
    deadline = time.time() + timeout
    poll_count = 0
    status: Dict = {}
    while time.time() < deadline:
        status = get_status(request_id, token)
        state = status.get("status", "UNKNOWN")
        summary = status.get("summary", {})
        _log(
            f"[poll #{poll_count}] status={state}  "
            f"completed={summary.get('completed', '?')}/{summary.get('total', '?')}  "
            f"failed={summary.get('failed', '?')}  "
            f"in_progress={summary.get('in_progress', '?')}"
        )
        tasks = status.get("tasks", [])
        non_terminal_tasks = [t for t in tasks if t.get("status") not in {"COMPLETED", "FAILED", "VALIDATION_FAILED"}]
        if state in TERMINAL_STATES and not non_terminal_tasks:
            return status
        poll_count += 1
        time.sleep(interval)

    state = status.get("status", "UNKNOWN")
    raise TimeoutError(
        f"Copy did not reach terminal state within {timeout}s. Last state: {state}"
    )


# ---------------------------------------------------------------------------
# Verification SQL generation
# ---------------------------------------------------------------------------

def build_verification_queries(request: Dict, status: Dict) -> List[Dict]:
    """
    For each task in the status response, generate:
    - source_count_sql  — run on source env MCP (dbx-prod for AWS_PROD/GCP_PROD)
    - target_count_sql  — run on target env MCP (dbx-dev for AWS_QA/AWS_BETA)
    - target_sample_sql — 5-row spot check on target
    - target_date_range_sql — min/max date check on target (only when date_filter present)
    """
    # Build a lookup of table_name → table config from the original request
    table_configs: Dict[str, Dict] = {
        t["table_name"]: t for t in request.get("tables", [])
    }

    queries = []
    for task in status.get("tasks", []):
        table_name: str = task["table_name"]
        cfg = table_configs.get(table_name, {})

        clients: List[str] = cfg.get("clients", []) or cfg.get("client_ids", [])
        date_filter: Dict = cfg.get("date_filter", {})
        column_filters: Dict = cfg.get("column_filters", {})

        # Build WHERE clause parts
        where_parts = []
        if clients:
            client_list = ", ".join(f"'{c}'" for c in clients)
            where_parts.append(f"client_id IN ({client_list})")
        if date_filter:
            col = date_filter["param"]
            start = date_filter["start_date"]
            end = date_filter["end_date"]
            where_parts.append(f"{col} BETWEEN '{start}' AND '{end}'")
        for col, values in column_filters.items():
            val_list = ", ".join(f"'{v}'" for v in values)
            where_parts.append(f"{col} IN ({val_list})")

        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        count_sql = f"SELECT COUNT(*) AS row_count FROM {table_name} {where_clause}".strip()
        sample_sql = f"SELECT * FROM {table_name} {where_clause} LIMIT 5".strip()
        date_range_sql = None
        if date_filter:
            col = date_filter["param"]
            date_range_sql = (
                f"SELECT MIN({col}) AS min_date, MAX({col}) AS max_date "
                f"FROM {table_name} {where_clause}"
            ).strip()

        queries.append({
            "table": table_name,
            "task_status": task.get("status"),
            "task_id": task.get("task_id"),
            "estimated_row_count": task.get("estimated_row_count"),
            "error_message": task.get("error_message"),
            "source_env": request.get("source_env"),
            "target_env": request.get("target_env"),
            "source_count_sql": count_sql,
            "target_count_sql": count_sql,
            "target_sample_sql": sample_sql,
            "target_date_range_sql": date_range_sql,
        })

    return queries


def _mcp_hint(env: str) -> str:
    """Return which dbx MCP server to use for a given environment."""
    if env in ("AWS_PROD", "GCP_PROD"):
        return "dbx-prod"
    return "dbx-dev"


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr)


def _print_verification_guide(queries: List[Dict], source_env: str, target_env: str) -> None:
    """Print a human-readable guide to stderr for Claude to follow."""
    src_mcp = _mcp_hint(source_env)
    tgt_mcp = _mcp_hint(target_env)

    _log("")
    _log("=" * 60)
    _log("VERIFICATION GUIDE")
    _log(f"  Source MCP: {src_mcp}  ({source_env})")
    _log(f"  Target MCP: {tgt_mcp}  ({target_env})")
    _log("=" * 60)
    for q in queries:
        _log(f"\n--- {q['table']} (status: {q['task_status']}) ---")
        if q.get("estimated_row_count"):
            _log(f"  Estimated rows copied: {q['estimated_row_count']:,}")
        if q.get("error_message"):
            _log(f"  ERROR: {q['error_message']}")
        _log(f"\n  [1] Source row count  ({src_mcp}):")
        _log(f"      {q['source_count_sql']}")
        _log(f"\n  [2] Target row count  ({tgt_mcp}):")
        _log(f"      {q['target_count_sql']}")
        if q.get("target_date_range_sql"):
            _log(f"\n  [3] Target date range ({tgt_mcp}):")
            _log(f"      {q['target_date_range_sql']}")
        _log(f"\n  [4] Target sample rows ({tgt_mcp}):")
        _log(f"      {q['target_sample_sql']}")
    _log("")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CIQ Data Copy Tool V3 — trigger, poll, and verify"
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="-",
        help="Path to JSON config file (or '-' for stdin). Required unless --request-id is used.",
    )
    parser.add_argument(
        "--token",
        help="Bearer auth token (if the service requires it)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        metavar="SECONDS",
        help=f"Seconds between status polls (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"Max seconds to wait for completion (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--skip-poll",
        action="store_true",
        help="Trigger the copy but return immediately without polling",
    )
    parser.add_argument(
        "--request-id",
        metavar="ID",
        help="Resume polling an already-triggered request (skip trigger step)",
    )
    args = parser.parse_args()

    # ---- Load request config (not needed for resume-poll mode) ----
    request: Dict = {}
    if not args.request_id:
        if args.config == "-":
            _log("Reading request config from stdin...")
            request = json.load(sys.stdin)
        else:
            with open(args.config) as f:
                request = json.load(f)

        if "requested_by" not in request:
            request["requested_by"] = DEFAULT_USER

    # ---- Trigger or resume ----
    if args.request_id:
        request_id = args.request_id
        _log(f"Resuming poll for request_id={request_id}")
    else:
        src = request.get("source_env", "?")
        tgt = request.get("target_env", "?")
        n_tables = len(request.get("tables", []))
        _log(f"Triggering copy: {src} → {tgt}  ({n_tables} table(s))")
        for t in request.get("tables", []):
            clients = t.get("clients", []) or t.get("client_ids", [])
            df = t.get("date_filter", {})
            date_str = (
                f"{df['start_date']} → {df['end_date']}" if df else "no date filter"
            )
            _log(f"  {t['table_name']}  clients={clients}  dates={date_str}  mode={t.get('copy_mode', '?')}")

        request_id = trigger_copy(request, args.token)
        _log(f"Accepted — request_id={request_id}")

    if args.skip_poll:
        print(json.dumps({"request_id": request_id, "status": "PENDING"}, indent=2))
        sys.exit(0)

    # ---- Poll ----
    _log(f"Polling every {args.poll_interval}s (timeout={args.timeout}s)...")
    try:
        final_status = poll_until_done(
            request_id, args.token, args.poll_interval, args.timeout
        )
    except TimeoutError as e:
        _log(f"TIMEOUT: {e}")
        sys.exit(1)

    # ---- Build verification output ----
    verification: List[Dict] = []
    if request:
        verification = build_verification_queries(request, final_status)
        _print_verification_guide(
            verification,
            request.get("source_env", ""),
            request.get("target_env", ""),
        )

    output = {
        "request_id": request_id,
        "final_status": final_status,
        "verification_queries": verification,
        "mcp_hint": {
            "source": _mcp_hint(request.get("source_env", "")),
            "target": _mcp_hint(request.get("target_env", "")),
        },
    }
    print(json.dumps(output, indent=2))

    state = final_status.get("status", "FAILED")
    if state == "COMPLETED":
        sys.exit(0)
    elif state == "PARTIALLY_COMPLETE":
        sys.exit(2)
    else:
        sys.exit(3)


if __name__ == "__main__":
    main()
