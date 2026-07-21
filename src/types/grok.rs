use serde::Deserialize;

// ─── Grok chat_history.jsonl (the transcript) ───
//
// Each session lives at:
//   ~/.grok/sessions/<url-encoded-cwd>/<session-uuid>/chat_history.jsonl
// Lines are tagged by `type`: system | user | reasoning | assistant | tool_result.
// chat_history lines carry NO per-message timestamp and (except reasoning `id`)
// no stable uuid. When uuid is missing we synthesize
//   `{session_id}:{line_number}`
// so every row has a non-NULL uuid; real `reasoning.id` is preferred when present.
//
// Timestamps: no per-message ts in chat_history. Session-level stamp from
// summary (`last_active_at` → `updated_at` → `created_at`). updates.jsonl has
// wall-clock `timestamp` (unix secs) but does not 1:1-align with chat lines, so
// we do not invent per-message times from it.
//
// Session metadata (git branch, model, repo, title, format version) is read
// from summary.json in the same dir. Optional `signals.json` feeds read_stats.
//
// Subagents: parent session may contain
//   subagents/<child_uuid>/meta.json
// linking parent_session_id ↔ child_session_id. The child also has its own
// top-level session directory under the same encoded cwd.

#[derive(Deserialize, Debug, Clone)]
#[serde(tag = "type")]
pub enum GrokMessage {
    #[serde(rename = "user")]
    User(GrokUserMessage),
    #[serde(rename = "assistant")]
    Assistant(GrokAssistantMessage),
    #[serde(rename = "tool_result")]
    ToolResult(GrokToolResult),
    #[serde(rename = "system")]
    System(GrokSystemMessage),
    #[serde(rename = "reasoning")]
    Reasoning(GrokReasoningMessage),
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokUserMessage {
    /// Either a plain string or a list of `{type:"text", text}` content blocks.
    pub content: Option<serde_json::Value>,
    pub synthetic_reason: Option<String>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokAssistantMessage {
    pub content: Option<String>,
    pub reasoning: Option<String>,
    pub model_id: Option<String>,
    pub model_fingerprint: Option<String>,
    /// Per-message effort (low|medium|high|xhigh|…). Mapped to `stop_reason`.
    pub reasoning_effort: Option<String>,
    #[serde(default)]
    pub tool_calls: Vec<GrokToolCall>,
}

#[derive(Deserialize, Debug, Clone)]
pub struct GrokToolCall {
    pub id: Option<String>,
    pub name: Option<String>,
    /// May be a JSON string or an object — serialized to a stable string for
    /// `tool_input` (string payloads keep their raw text; objects use JSON).
    pub arguments: Option<serde_json::Value>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokToolResult {
    pub content: Option<serde_json::Value>,
    pub tool_call_id: Option<String>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokSystemMessage {
    pub content: Option<serde_json::Value>,
}

/// Assistant chain-of-thought summary. `encrypted_content` is intentionally
/// ignored (never mapped).
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokReasoningMessage {
    pub id: Option<String>,
    /// Array of `{type:"summary_text", text:"…"}` blocks (same shape Codex uses).
    pub summary: Option<serde_json::Value>,
    pub status: Option<String>,
    /// Per-message effort when present on the reasoning line.
    pub reasoning_effort: Option<String>,
}

// ─── Grok summary.json (per-session metadata) ───

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokSummary {
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
    pub last_active_at: Option<String>,
    pub current_model_id: Option<String>,
    pub head_branch: Option<String>,
    pub git_root_dir: Option<String>,
    /// origin/remote URLs; first entry used as `repository`.
    pub git_remotes: Option<Vec<String>>,
    /// Session title → `slug`.
    pub generated_title: Option<String>,
    /// Format version → `version` (as string).
    pub chat_format_version: Option<serde_json::Value>,
    /// Session-level effort; backfills `stop_reason` when the message has none.
    pub reasoning_effort: Option<String>,
    pub agent_name: Option<String>,
    /// Optional chat-history line count (fallback for read_stats message_count).
    pub num_messages: Option<i64>,
}

// ─── Grok subagent meta.json ───
//
// Path: sessions/<cwd>/<parent_uuid>/subagents/<child_uuid>/meta.json
// Child transcript lives at sessions/<cwd>/<child_uuid>/chat_history.jsonl.

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokSubagentMeta {
    pub parent_session_id: Option<String>,
    pub child_session_id: Option<String>,
    pub subagent_type: Option<String>,
    pub description: Option<String>,
    pub effective_model_id: Option<String>,
}

// ─── Grok signals.json (per-session aggregates → read_stats) ───
//
// Optional sibling of chat_history. Session-level counters only; no per-message
// rows. Mapped into existing read_stats columns (date / message_count /
// session_count / tool_call_count) — no new table function.

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default, rename_all = "camelCase")]
pub struct GrokSignals {
    pub user_message_count: Option<i64>,
    pub assistant_message_count: Option<i64>,
    pub tool_call_count: Option<i64>,
    pub turn_count: Option<i64>,
    pub avg_time_to_first_token_ms: Option<f64>,
    pub context_tokens_used: Option<i64>,
    pub models_used: Option<Vec<String>>,
    pub primary_model_id: Option<String>,
    pub session_duration_seconds: Option<i64>,
}

// ─── Grok plan.md / plan_mode.json are handled by read_plans (plain markdown) ───
