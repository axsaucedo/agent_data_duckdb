use serde::Deserialize;

/// A Gemini CLI chat checkpoint file:
/// `~/.gemini/tmp/<project-hash>/chats/session-<ts>-<id>.json`.
///
/// Each file is a single JSON object holding the full ordered transcript for one
/// session. The shape is stable across Gemini CLI releases (verified Nov 2025 →
/// Jun 2026 across hundreds of local sessions).
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GeminiSession {
    #[serde(rename = "sessionId")]
    pub session_id: Option<String>,
    #[serde(rename = "projectHash")]
    pub project_hash: Option<String>,
    #[serde(rename = "startTime")]
    pub start_time: Option<String>,
    #[serde(rename = "lastUpdated")]
    pub last_updated: Option<String>,
    /// `kind` is present on newer sessions: `"main"` or `"subagent"`.
    pub kind: Option<String>,
    pub summary: Option<String>,
    pub messages: Vec<GeminiMessage>,
}

/// A single message within a Gemini session.
///
/// `type` is one of `user`, `gemini`, `info`, `error`. Assistant (`gemini`)
/// messages additionally carry `model`, `tokens`, `thoughts`, and `toolCalls`.
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GeminiMessage {
    pub id: Option<String>,
    pub timestamp: Option<String>,
    #[serde(rename = "type")]
    pub message_type: Option<String>,
    pub content: Option<String>,
    pub model: Option<String>,
    pub tokens: Option<GeminiTokens>,
    /// Free-form reasoning summaries (newer sessions); kept as raw JSON.
    pub thoughts: Option<serde_json::Value>,
    #[serde(rename = "toolCalls")]
    pub tool_calls: Option<Vec<GeminiToolCall>>,
}

/// Per-assistant-message token accounting.
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GeminiTokens {
    pub input: Option<i64>,
    pub output: Option<i64>,
    pub cached: Option<i64>,
    pub thoughts: Option<i64>,
    pub tool: Option<i64>,
    pub total: Option<i64>,
}

/// A tool invocation embedded in a `gemini` message.
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct GeminiToolCall {
    pub id: Option<String>,
    pub name: Option<String>,
    pub args: Option<serde_json::Value>,
    /// `success`, `error`, or `cancelled`.
    pub status: Option<String>,
    pub timestamp: Option<String>,
    #[serde(rename = "resultDisplay")]
    pub result_display: Option<serde_json::Value>,
}
