#!/usr/bin/env python3
"""Generate the Cursor test fixtures under test/data_cursor/.

Two SQLite databases mirroring Cursor's real on-disk format (table
`cursorDiskKV (key TEXT, value BLOB)`), all content synthetic:

  * state.vscdb        — tiny happy-path fixture: 1 composer + 2 bubbles, plus
                         two noise rows. Single leaf page, small values.
  * state_large.vscdb  — stress fixture that forces the pure-Rust reader's
                         harder paths: 1 composer + 300 bubbles (many leaf pages
                         under an interior b-tree page) with one ~100 KB bubble
                         value that spills across overflow pages. This exercises
                         interior-page traversal and overflow-chain reassembly
                         in src/vscdb.rs, which the tiny fixture cannot.

Re-run after changing either fixture:
    python3 test/data_cursor/make_fixture.py

The generated .vscdb files are committed so the test suite does not depend on
Python at build/test time.
"""
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "state.vscdb")
LARGE_DB_PATH = os.path.join(HERE, "state_large.vscdb")

# ─── Small happy-path fixture ───

COMPOSER_ID = "comp-1111-0000-0000-0000-000000000001"
BUBBLE_USER = "bub-aaaa"
BUBBLE_ASSISTANT = "bub-bbbb"

# createdAt values are epoch milliseconds (Cursor stores ms).
# 1717000000000 -> 2024-05-29T16:26:40Z, +1000 ms for the second bubble.
TS_USER = 1717000000000
TS_ASSISTANT = 1717000001000

composer_data = {
    "composerId": COMPOSER_ID,
    "createdAt": TS_USER,
    "name": "Add a hello function",
    "modelConfig": {"modelName": "claude-3.7-sonnet", "maxMode": False},
    "fullConversationHeadersOnly": [
        {"bubbleId": BUBBLE_USER, "type": 1},
        {"bubbleId": BUBBLE_ASSISTANT, "type": 2},
    ],
}

bubble_user = {
    "bubbleId": BUBBLE_USER,
    "type": 1,
    "text": "Please add a hello() function to hello.py.",
    "createdAt": TS_USER,
    "isAgentic": True,
    "tokenCount": {"inputTokens": 12, "outputTokens": 0},
}

bubble_assistant = {
    "bubbleId": BUBBLE_ASSISTANT,
    "type": 2,
    "text": "I'll add it now.",
    "thinking": {"text": "The user wants a simple function."},
    "createdAt": TS_ASSISTANT,
    "isAgentic": False,
    "timingInfo": {"clientStartTime": TS_ASSISTANT},
    "tokenCount": {"inputTokens": 12, "outputTokens": 34},
    "toolFormerData": {
        "tool": "edit_file",
        "name": "edit_file",
        "rawArgs": json.dumps({"path": "hello.py", "contents": "def hello():\n    return 'world'"}),
        "params": {"path": "hello.py"},
        "result": "File edited: hello.py",
        "status": "completed",
        "toolCallId": "tc-1",
    },
}

# ─── Large stress fixture ───

COMPOSER_ID_LARGE = "comp-large-2222-0000-0000-000000000002"
N_BUBBLES = 300
# A 100 000-char value (no JSON-escaped chars) forces a multi-page overflow
# chain; the repeating marker lets the test assert byte-exact reassembly.
BIG_MARKER = "0123456789ABCDEF"
BIG_TEXT = BIG_MARKER * 6250  # 16 * 6250 = 100000 chars
BIG_BUBBLE_INDEX = N_BUBBLES - 1  # the last bubble carries the large payload


def _write_db(path: str, rows: list) -> None:
    # Remove any prior db and its WAL/SHM sidecars.
    for suffix in ("", "-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            os.remove(p)
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        # Real Cursor state.vscdb files journal in rollback (DELETE) mode, which
        # keeps every row in the main file (no -wal sidecar). Force it here so the
        # pure-Rust main-file reader (src/vscdb.rs) sees everything and the fixture
        # is fully self-contained and deterministic.
        cur.execute("PRAGMA journal_mode=DELETE")
        # Mirror the two tables Cursor's globalStorage state.vscdb actually has.
        cur.execute("CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
        cur.execute("CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
        cur.executemany("INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)", rows)
        conn.commit()
        # Defensive: ensure no WAL frames linger even if a future edit flips mode.
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()
    print(f"wrote {path}")


def build_small() -> None:
    rows = [
        (f"composerData:{COMPOSER_ID}", json.dumps(composer_data)),
        (f"bubbleId:{COMPOSER_ID}:{BUBBLE_USER}", json.dumps(bubble_user)),
        (f"bubbleId:{COMPOSER_ID}:{BUBBLE_ASSISTANT}", json.dumps(bubble_assistant)),
        # Noise rows the parser must ignore.
        ("messageRequestContext:foo", json.dumps({"unused": True})),
        ("checkpointId:bar", json.dumps({"unused": True})),
    ]
    _write_db(DB_PATH, rows)


def build_large() -> None:
    headers = []
    rows = []
    base_ts = 1717000000000
    for i in range(N_BUBBLES):
        bubble_id = f"bub-{i:04d}"
        # Even index -> user (type 1), odd index -> assistant (type 2).
        bubble_type = 1 if i % 2 == 0 else 2
        headers.append({"bubbleId": bubble_id, "type": bubble_type})
        text = BIG_TEXT if i == BIG_BUBBLE_INDEX else f"message number {i}"
        bubble = {
            "bubbleId": bubble_id,
            "type": bubble_type,
            "text": text,
            "createdAt": base_ts + i * 1000,
            "tokenCount": {"inputTokens": i, "outputTokens": i * 2},
        }
        rows.append((f"bubbleId:{COMPOSER_ID_LARGE}:{bubble_id}", json.dumps(bubble)))
    composer = {
        "composerId": COMPOSER_ID_LARGE,
        "createdAt": base_ts,
        "name": "Large synthetic conversation",
        "modelConfig": {"modelName": "gpt-4o"},
        "fullConversationHeadersOnly": headers,
    }
    # The composer row itself (300-entry headers array) is also large enough to
    # spill, adding a second overflow case alongside the big bubble.
    rows.insert(0, (f"composerData:{COMPOSER_ID_LARGE}", json.dumps(composer)))
    _write_db(LARGE_DB_PATH, rows)


def main() -> None:
    build_small()
    build_large()


if __name__ == "__main__":
    main()
