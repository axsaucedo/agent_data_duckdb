import marimo

__generated_with = "0.19.9"
app = marimo.App(width="medium", app_title="agent_data Explorer")


@app.cell
def _():
    import marimo as mo

    mo.md(
        """
    # agent_data Explorer

    Interactive exploration of AI coding agent session data using the `agent_data` DuckDB extension.

    Supports both **Claude Code** (`~/.claude`) and **GitHub Copilot CLI** (`~/.copilot`) data.

    Set `DATA_PATH` to your agent data directory, or provide two paths for cross-source analysis.
    """
    )
    return (mo,)


@app.cell
def _(mo):
    import os

    # Configuration: change these to explore your own data
    DATA_PATH = os.environ.get("AGENT_DATA_PATH", "~/.claude")
    COPILOT_PATH = os.environ.get("COPILOT_DATA_PATH", "~/.copilot")

    mo.md(
        f"""
    **Primary data:** `{DATA_PATH}`
    **Copilot data:** `{COPILOT_PATH}`
    """
    )
    return COPILOT_PATH, DATA_PATH, os


@app.cell
def _(COPILOT_PATH, DATA_PATH):
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL agent_data FROM community")
    con.execute("LOAD agent_data")

    def load_table(name, path):
        return con.execute(f"SELECT * FROM read_{name}(path='{path}')").df()

    def load_union(name):
        return con.execute(
            f"SELECT * FROM read_{name}(path='{DATA_PATH}') "
            f"UNION ALL "
            f"SELECT * FROM read_{name}(path='{COPILOT_PATH}')"
        ).df()

    # Load all tables from both sources
    conversations = load_union("conversations")
    plans = load_union("plans")
    todos = load_union("todos")
    history = load_union("history")
    stats = load_union("stats")
    return con, conversations, duckdb, history, load_union, plans, stats, todos


@app.cell
def _(conversations, history, mo, plans, stats, todos):
    def source_counts(df):
        if "source" in df.columns:
            counts = df["source"].value_counts().to_dict()
            return " | ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        return str(len(df))

    mo.md(
        f"""
    ## Overview

    | Table | Total Rows | By Source |
    |-------|-----------|----------|
    | Conversations | {len(conversations)} | {source_counts(conversations)} |
    | Plans | {len(plans)} | {source_counts(plans)} |
    | Todos | {len(todos)} | {source_counts(todos)} |
    | History | {len(history)} | {source_counts(history)} |
    | Stats | {len(stats)} | {source_counts(stats)} |
    """
    )
    return (source_counts,)


@app.cell
def _(conversations, mo):
    mo.md("## Conversations by Source and Type")
    return


@app.cell
def _(conversations, mo):
    project_summary = (
        conversations.groupby(["source", "message_type"])
        .size()
        .reset_index(name="count")
        .sort_values(["source", "count"], ascending=[True, False])
    )
    mo.ui.table(project_summary, label="Messages by Source and Type")
    return (project_summary,)


@app.cell
def _(conversations, mo):
    mo.md("## Session Explorer")
    return


@app.cell
def _(conversations, mo):
    sessions = conversations[["source", "session_id", "project_path", "file_name"]].drop_duplicates()
    session_options = {
        f"[{row['source']}] {row['session_id'][:12]}… ({row['project_path']})": row["session_id"]
        for _, row in sessions.drop_duplicates(subset=["session_id"]).iterrows()
        if row["session_id"]
    }
    session_selector = mo.ui.dropdown(
        options=session_options,
        label="Select Session",
    )
    session_selector
    return session_options, session_selector, sessions


@app.cell
def _(conversations, mo, session_selector):
    if session_selector.value:
        session_msgs = conversations[
            conversations["session_id"] == session_selector.value
        ][
            [
                "source",
                "line_number",
                "message_type",
                "message_role",
                "timestamp",
                "model",
                "tool_name",
            ]
        ].sort_values("line_number")
        mo.ui.table(session_msgs, label=f"Messages in session {session_selector.value}")
    else:
        mo.md("*Select a session above*")
    return (session_msgs,)


@app.cell
def _(mo):
    mo.md("## Todos Status")
    return


@app.cell
def _(mo, todos):
    todo_status = (
        todos.groupby(["source", "status"]).size().reset_index(name="count").sort_values("count", ascending=False)
    )
    mo.ui.table(todo_status, label="Todo Status Distribution")
    return (todo_status,)


@app.cell
def _(mo, todos):
    display_cols = ["source", "session_id", "content", "status"]
    if "agent_id" in todos.columns:
        display_cols.insert(2, "agent_id")
    mo.ui.table(
        todos[display_cols],
        label="All Todos",
    )
    return (display_cols,)


@app.cell
def _(mo):
    mo.md("## Plans")
    return


@app.cell
def _(mo, plans):
    mo.ui.table(
        plans[["source", "session_id", "plan_name", "file_name", "file_size"]],
        label="Available Plans",
    )
    return


@app.cell
def _(mo):
    mo.md("## History")
    return


@app.cell
def _(history, mo):
    hist_display = history.copy()
    if "timestamp_ms" in hist_display.columns:
        import pandas as pd

        hist_display["timestamp"] = pd.to_datetime(
            hist_display["timestamp_ms"], unit="ms", errors="coerce"
        )
    display_cols = ["source", "display"]
    if "timestamp" in hist_display.columns:
        display_cols.insert(1, "timestamp")
    if "project" in hist_display.columns:
        display_cols.append("project")
    mo.ui.table(
        hist_display[display_cols].sort_values(display_cols[1], ascending=False, na_position="last"),
        label="Command History",
    )
    return display_cols, hist_display, pd


@app.cell
def _(mo):
    mo.md("## Daily Activity Stats")
    return


@app.cell
def _(mo, stats):
    if len(stats) > 0:
        mo.ui.table(stats, label="Daily Activity")
    else:
        mo.md("*No stats data available*")
    return


@app.cell
def _(mo):
    mo.md(
        """
    ## Cross-Source Analysis

    Aggregate session activity across all loaded sources.
    """
    )
    return


@app.cell
def _(COPILOT_PATH, DATA_PATH, con, mo):
    cross_query = f"""
    WITH all_conversations AS (
        SELECT * FROM read_conversations(path='{DATA_PATH}')
        UNION ALL
        SELECT * FROM read_conversations(path='{COPILOT_PATH}')
    ),
    all_todos AS (
        SELECT * FROM read_todos(path='{DATA_PATH}')
        UNION ALL
        SELECT * FROM read_todos(path='{COPILOT_PATH}')
    )
    SELECT
        c.source,
        c.session_id,
        c.project_path,
        COUNT(DISTINCT c.uuid) as message_count,
        COUNT(DISTINCT t.content) as todo_count
    FROM all_conversations c
    LEFT JOIN all_todos t ON c.session_id = t.session_id AND c.source = t.source
    GROUP BY c.source, c.session_id, c.project_path
    ORDER BY message_count DESC
    """
    cross_data = con.execute(cross_query).df()
    mo.ui.table(cross_data, label="Session Activity Summary (All Sources)")
    return cross_data, cross_query


if __name__ == "__main__":
    app.run()
