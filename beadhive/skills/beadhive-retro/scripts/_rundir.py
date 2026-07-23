#!/usr/bin/env python3
"""Shared run-folder helpers for the beadhive-retro pipeline scripts.

Stdlib only, no CLI of its own. A "run-dir" is `~/.beadhive/retros/<run-id>/`, where
`run-id` = `<YYYYMMDD-HHMMSS>-<hash8>` derived from a run's own `window.since`,
`generatedAt`, and session count (see `compute_run_id`). `identify.py` creates the run-dir;
`extract.py`, `analyze.py`, and `render.py` resolve the same one via `--run-dir` or the
`latest` pointer file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime

RETROS_ROOT = os.path.expanduser("~/.beadhive/retros")
LATEST_POINTER = os.path.join(RETROS_ROOT, "latest")


def compute_run_id(since: str, generated_at: str, session_count: int) -> str:
    """`<YYYYMMDD-HHMMSS>-<hash8>` from a run's own since/generatedAt/session-count.

    hash8 = first 8 hex chars of sha256(json.dumps({since, generatedAt, sessions},
    sort_keys=True)). This exact scheme is pinned by example against a real run folder —
    see identify.py's selftest.
    """
    payload = json.dumps(
        {"since": since, "generatedAt": generated_at, "sessions": session_count},
        sort_keys=True,
    )
    hash8 = hashlib.sha256(payload.encode()).hexdigest()[:8]
    dt = datetime.fromisoformat(generated_at)
    return f"{dt.strftime('%Y%m%d-%H%M%S')}-{hash8}"


def new_run_dir(run_id: str) -> tuple[str, bool]:
    """Create `~/.beadhive/retros/<run_id>/`, falling back to cwd if unwritable.

    Returns `(run_dir, degraded)` — `degraded` is True when the `~/.beadhive` fallback to
    cwd was used (caller should skip updating the `latest` pointer in that case).
    """
    run_dir = os.path.join(RETROS_ROOT, run_id)
    try:
        os.makedirs(run_dir, exist_ok=True)
        return run_dir, False
    except OSError as exc:
        print(
            f"warning: cannot create {run_dir} ({exc}); writing to cwd instead",
            file=sys.stderr,
        )
        return os.getcwd(), True


def write_latest_pointer(run_dir: str) -> None:
    """Best-effort: point `~/.beadhive/retros/latest` at the most recent run-dir."""
    try:
        os.makedirs(RETROS_ROOT, exist_ok=True)
        with open(LATEST_POINTER, "w") as f:
            f.write(run_dir + "\n")
    except OSError:
        pass


def read_latest_pointer() -> str | None:
    try:
        with open(LATEST_POINTER) as f:
            path = f.read().strip()
        return path or None
    except OSError:
        return None


def resolve_run_dir(explicit: str | None) -> str | None:
    """Explicit `--run-dir` wins; else the `latest` pointer; else None (caller falls back
    to its legacy cwd-relative defaults)."""
    if explicit:
        return explicit
    return read_latest_pointer()
