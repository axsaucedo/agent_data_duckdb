use serde::Deserialize;

// ─── Cursor state.vscdb (SQLite KV) ───
//
// Path: ~/Library/Application Support/Cursor/User/globalStorage/state.vscdb
// Table `cursorDiskKV (key TEXT, value BLOB)`. Conversation data lives under:
//   composerData:<composerId>            -> a conversation/session
//   bubbleId:<composerId>:<bubbleId>     -> an individual message
// `bubble.type`: 1 = user, 2 = assistant.

/// `composerData:<composerId>` value.
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct CursorComposer {
    #[serde(rename = "composerId")]
    pub composer_id: Option<String>,
    /// epoch milliseconds
    #[serde(rename = "createdAt")]
    pub created_at: Option<i64>,
    /// Ordered message references — defines bubble order within the composer.
    #[serde(rename = "fullConversationHeadersOnly")]
    pub headers: Option<Vec<CursorHeader>>,
    #[serde(rename = "modelConfig")]
    pub model_config: Option<CursorModelConfig>,
    pub name: Option<String>,
    pub context: Option<serde_json::Value>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct CursorHeader {
    #[serde(rename = "bubbleId")]
    pub bubble_id: Option<String>,
    /// 1 = user, 2 = assistant
    #[serde(rename = "type")]
    pub bubble_type: Option<i64>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct CursorModelConfig {
    #[serde(rename = "modelName")]
    pub model_name: Option<String>,
}

/// `bubbleId:<composerId>:<bubbleId>` value.
#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct CursorBubble {
    #[serde(rename = "bubbleId")]
    pub bubble_id: Option<String>,
    /// 1 = user, 2 = assistant
    #[serde(rename = "type")]
    pub bubble_type: Option<i64>,
    /// Plain-text rendering of the message (preferred over `richText`).
    pub text: Option<String>,
    /// Lexical/editor tree; only used as a fallback if `text` is empty.
    #[serde(rename = "richText")]
    pub rich_text: Option<serde_json::Value>,
    pub thinking: Option<serde_json::Value>,
    #[serde(rename = "createdAt")]
    pub created_at: Option<i64>,
    #[serde(rename = "tokenCount")]
    pub token_count: Option<serde_json::Value>,
    #[serde(rename = "isAgentic")]
    pub is_agentic: Option<bool>,
    #[serde(rename = "timingInfo")]
    pub timing_info: Option<CursorTimingInfo>,
    #[serde(rename = "toolFormerData")]
    pub tool_former_data: Option<CursorToolData>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct CursorTimingInfo {
    #[serde(rename = "clientStartTime")]
    pub client_start_time: Option<i64>,
}

#[derive(Deserialize, Debug, Clone, Default)]
#[serde(default)]
pub struct CursorToolData {
    pub tool: Option<String>,
    pub name: Option<String>,
    /// Raw stringified JSON arguments as sent to the model.
    #[serde(rename = "rawArgs")]
    pub raw_args: Option<serde_json::Value>,
    pub params: Option<serde_json::Value>,
    #[serde(rename = "toolCallId")]
    pub tool_call_id: Option<String>,
    pub status: Option<String>,
}
