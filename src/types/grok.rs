use serde::Deserialize;

// ─── Grok chat_history.jsonl (the transcript) ───
//
// Each session lives at:
//   ~/.grok/sessions/<url-encoded-cwd>/<session-uuid>/chat_history.jsonl
// Lines are tagged by `type`: user | assistant | tool_result | system.
// chat_history lines carry NO per-message timestamp or id; session metadata
// (timestamp, git branch, model, repo) is read from summary.json in the same dir.

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
    #[serde(default)]
    pub tool_calls: Vec<GrokToolCall>,
}

#[derive(Deserialize, Debug, Clone)]
pub struct GrokToolCall {
    pub id: Option<String>,
    pub name: Option<String>,
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

// ─── Grok summary.json (per-session metadata) ───

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GrokSummary {
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
    pub current_model_id: Option<String>,
    pub head_branch: Option<String>,
    pub git_root_dir: Option<String>,
    /// origin/remote URLs; first entry used as `repository`.
    pub git_remotes: Option<Vec<String>>,
    pub generated_title: Option<String>,
    pub chat_format_version: Option<i64>,
}

// ─── Grok plan.md / plan_mode.json are handled by read_plans (plain markdown) ───
