# Copilot CLI File Schemas

## Event Envelope (Common to All Events)

Every line in `events.jsonl` follows this structure:

```json
{
  "type": "string",           // Event type identifier
  "id": "uuid",               // Unique event ID
  "timestamp": "ISO-8601",    // Event timestamp (UTC)
  "parentId": "uuid | null",  // Parent event for ordering/threading
  "data": { ... }             // Type-specific payload
}
```

## Event Types

### `session.start` — Session Initialization
```json
{
  "type": "session.start",
  "data": {
    "sessionId": "uuid",
    "version": 1,
    "producer": "copilot-agent",
    "copilotVersion": "0.0.407-1",
    "startTime": "ISO-8601",
    "context": {
      "cwd": "/path/to/project",
      "gitRoot": "/path/to/repo",
      "branch": "main",
      "repository": "owner/repo"
    }
  }
}
```
**Notes:** `context` is optional. Provides session metadata including model version and git context.

### `session.resume` — Session Resumed
```json
{
  "type": "session.resume",
  "data": {
    "resumeTime": "ISO-8601",
    "eventCount": 25
  }
}
```

### `session.info` — Session Information
```json
{
  "type": "session.info",
  "data": {
    "infoType": "authentication | mcp",
    "message": "descriptive message"
  }
}
```

### `session.error` — Session Error
```json
{
  "type": "session.error",
  "data": {
    "errorType": "model_call",
    "message": "error description",
    "stack": "stack trace (optional)"
  }
}
```

### `session.truncation` — Context Window Truncation
```json
{
  "type": "session.truncation",
  "data": {
    "tokenLimit": 128000,
    "preTruncationTokensInMessages": 95000,
    "preTruncationMessagesLength": 50,
    "postTruncationTokensInMessages": 80000,
    "postTruncationMessagesLength": 40,
    "tokensRemovedDuringTruncation": 15000,
    "messagesRemovedDuringTruncation": 10,
    "performedBy": "BasicTruncator"
  }
}
```

### `session.model_change` — Model Switch
```json
{
  "type": "session.model_change",
  "data": {
    "newModel": "claude-opus-4.5"
  }
}
```

### `session.compaction_start` / `session.compaction_complete` — Context Compaction
```json
{
  "type": "session.compaction_start",
  "data": {}
}
```

### `user.message` — User Input
```json
{
  "type": "user.message",
  "data": {
    "content": "user message text",
    "attachments": []
  }
}
```

### `assistant.message` — Assistant Response
```json
{
  "type": "assistant.message",
  "data": {
    "messageId": "uuid",
    "content": "response text (may be empty if only tool calls)",
    "toolRequests": [
      {
        "toolCallId": "toolu_vrtx_...",
        "name": "bash",
        "arguments": { "command": "ls -la" },
        "type": "function"
      }
    ]
  }
}
```
**Notes:** `toolRequests` is present when the assistant calls tools. `content` may be empty string when only tool calls are made.

### `assistant.reasoning` — Model Reasoning
```json
{
  "type": "assistant.reasoning",
  "data": {
    "reasoningId": "uuid",
    "content": "reasoning text"
  }
}
```

### `assistant.turn_start` / `assistant.turn_end` — Turn Boundaries
```json
{
  "type": "assistant.turn_start",
  "data": { "turnId": "0" }
}
```

### `tool.execution_start` — Tool Invocation
```json
{
  "type": "tool.execution_start",
  "data": {
    "toolCallId": "toolu_vrtx_...",
    "toolName": "bash",
    "arguments": { "command": "ls -la" }
  }
}
```

### `tool.execution_complete` — Tool Result
```json
{
  "type": "tool.execution_complete",
  "data": {
    "toolCallId": "toolu_vrtx_...",
    "success": true,
    "result": {
      "content": "result text",
      "detailedContent": "detailed result (optional)"
    },
    "toolTelemetry": {}
  }
}
```

### `abort` — User Abort
```json
{
  "type": "abort",
  "data": { "reason": "user initiated" }
}
```

## workspace.yaml Schema

```yaml
id: uuid                    # Session UUID
cwd: /path/to/project       # Working directory
git_root: /path/to/repo     # Git repository root (optional)
repository: owner/repo      # GitHub repository (optional)
branch: main                # Git branch (optional)
summary: Session title       # Auto-generated summary (optional)
summary_count: 1             # Number of summary updates
created_at: ISO-8601         # Session creation time
updated_at: ISO-8601         # Last update time
```

## command-history-state.json Schema

```json
{
  "commandHistory": [
    "first command text",
    "second command text",
    "..."
  ]
}
```
Simple array of command strings. No timestamps, project paths, or session IDs.

## plan.md Format

Standard markdown document. Typically contains:
- Problem statement
- Implementation plan with phases
- Markdown checklists (`- [x]` / `- [ ]`)

## Checkpoint Files

### `checkpoints/index.md`
```markdown
# Checkpoint History
| # | Title | File |
|---|-------|------|
| 1 | Task description | 001-task-slug.md |
```

### `checkpoints/NNN-slug.md`
Detailed checkpoint documents with context, decisions, and progress checklists.

## rewind-snapshots/index.json Schema

```json
{
  "version": 1,
  "snapshots": [
    {
      "snapshotId": "uuid",
      "eventId": "uuid",
      "userMessage": "triggering message text",
      "timestamp": "ISO-8601",
      "fileCount": 0,
      "gitCommit": "sha",
      "gitBranch": "branch",
      "backupHashes": [],
      "files": {}
    }
  ],
  "filePathMap": {}
}
```

## DuckDB Table Mapping

### Conversations (from events.jsonl)
Maps all 16 event types to rows with normalized `message_type` values:
- `user.message` → `user`
- `assistant.message` → `assistant`
- `assistant.reasoning` → `reasoning`
- `tool.execution_start` → `tool_start`
- `tool.execution_complete` → `tool_result`
- Session events → `session_start`, `session_resume`, `session_info`, `session_error`, `truncation`, `compaction_start`, `compaction_complete`, `model_change`, `abort`

### Plans (from plan.md)
One row per plan file found in session directories.

### Todos (from checkpoint checklists)
Extracted from markdown `- [x]`/`- [ ]` patterns in checkpoint files.

### History (from command-history-state.json)
One row per command string. No metadata (timestamps, projects) available.

### Stats
No Copilot equivalent — returns empty result set.
