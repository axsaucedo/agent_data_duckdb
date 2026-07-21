use serde::Deserialize;

// ─── Grok chat_history.jsonl (the transcript) ───
//
// Each session lives at:
//   ~/.grok/sessions/<url-encoded-cwd>/<session-uuid>/chat_history.jsonl
// Lines are tagged by `type`: system | user | reasoning | assistant | tool_result.
// chat_history lines carry NO per-message timestamp and (except reasoning `id`)
// no stable uuid. Session metadata (timestamp, git branch, model, repo, title,
// format version) is read from summary.json in the same dir.
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
    /// Per-message effort (low|medium|high|xhigh|…). Mapped to `reasoning_effort`.
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
    /// Session-level effort; backfills `reasoning_effort` when the message has none.
    pub reasoning_effort: Option<String>,
    pub agent_name: Option<String>,
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

// ─── Grok updates.jsonl (token usage) ───
//
// Sibling of chat_history.jsonl. Token usage is NOT on chat_history lines.
// Final (or only) usage snapshot for a prompt lives on:
//   params.update.sessionUpdate == "turn_completed"
//   params.update.usage = { inputTokens, outputTokens, cachedReadTokens,
//                           reasoningTokens, numTurns, ... }
// Usage is cumulative within one user-prompt agent loop (numTurns 1→N), then
// resets for the next prompt. Interactive sessions may emit one turn_completed
// per prompt with the final cumulative totals.

/// Envelope for one updates.jsonl line (other fields ignored).
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokUpdatesLine {
    pub params: Option<GrokUpdatesParams>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokUpdatesParams {
    pub update: Option<GrokSessionUpdate>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokSessionUpdate {
    #[serde(rename = "sessionUpdate")]
    pub session_update: Option<String>,
    pub usage: Option<GrokUsage>,
}

/// Token usage from turn_completed (camelCase keys as emitted by the CLI).
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokUsage {
    #[serde(rename = "inputTokens")]
    pub input_tokens: Option<i64>,
    #[serde(rename = "outputTokens")]
    pub output_tokens: Option<i64>,
    #[serde(rename = "cachedReadTokens")]
    pub cached_read_tokens: Option<i64>,
    #[serde(rename = "reasoningTokens")]
    pub reasoning_tokens: Option<i64>,
}

impl GrokUsage {
    /// True if any mapped token field is present (skip empty / zero-only task events).
    pub fn has_any_tokens(&self) -> bool {
        self.input_tokens.is_some()
            || self.output_tokens.is_some()
            || self.cached_read_tokens.is_some()
            || self.reasoning_tokens.is_some()
    }
}

// ─── Grok plan.md / plan_mode.json are handled by read_plans (plain markdown) ───
