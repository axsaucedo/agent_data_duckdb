#!/usr/bin/env python3
"""Generate the Cursor test fixture: test/data_cursor/state.vscdb.

This produces a tiny, reproducible SQLite database mirroring Cursor's real
on-disk format (table `cursorDiskKV (key TEXT, value BLOB)`), with one composer
(session) and two bubbles (a user message and an assistant message that makes a
tool call). All content is synthetic — no real conversation data.

Re-run after changing the fixture:
    python3 test/data_cursor/make_fixture.py

The generated state.vscdb is committed so the test suite does not depend on
Python at build/test time.
"""
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "state.vscdb")

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


def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # Mirror the two tables Cursor's globalStorage state.vscdb actually has.
        cur.execute("CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
        cur.execute("CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")

        rows = [
            (f"composerData:{COMPOSER_ID}", json.dumps(composer_data)),
            (f"bubbleId:{COMPOSER_ID}:{BUBBLE_USER}", json.dumps(bubble_user)),
            (f"bubbleId:{COMPOSER_ID}:{BUBBLE_ASSISTANT}", json.dumps(bubble_assistant)),
            # Noise rows the parser must ignore.
            ("messageRequestContext:foo", json.dumps({"unused": True})),
            ("checkpointId:bar", json.dumps({"unused": True})),
        ]
        cur.executemany("INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    print(f"wrote {DB_PATH}")


if __name__ == "__main__":
    main()
