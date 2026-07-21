use crate::detect::{self, Provider};
use crate::types::claude::*;
use crate::types::codex::*;
use crate::types::copilot::*;
#[cfg(feature = "cursor")]
use crate::types::cursor::*;
use crate::types::gemini::*;
use crate::types::grok::*;
use crate::utils;
use crate::vtab::{self, ColDef, TableFunc};
use duckdb::core::DataChunkHandle;
use std::io::{BufRead, BufReader};

/// A flattened conversation row ready for output.
#[derive(Default, Clone)]
pub struct ConversationRow {
    source: String,
    session_id: String,
    project_path: String,
    project_dir: String,
    file_name: String,
    is_agent: bool,
    line_number: i64,
    message_type: String,
    uuid: Option<String>,
    parent_uuid: Option<String>,
    timestamp: Option<String>,
    message_role: Option<String>,
    message_content: Option<String>,
    model: Option<String>,
    tool_name: Option<String>,
    tool_use_id: Option<String>,
    tool_input: Option<String>,
    input_tokens: Option<i64>,
    output_tokens: Option<i64>,
    cache_creation_tokens: Option<i64>,
    cache_read_tokens: Option<i64>,
    /// Grok-only: `updates.jsonl` turn_completed `reasoningTokens`. Other providers NULL.
    reasoning_tokens: Option<i64>,
    slug: Option<String>,
    git_branch: Option<String>,
    cwd: Option<String>,
    version: Option<String>,
    stop_reason: Option<String>,
    repository: Option<String>,
}

pub struct Conversations;

// ─── Claude loading helpers ───

impl Conversations {
    fn claude_base_row(source: &str, base: &BaseFields, project_dir: &str, file_name: &str, is_agent: bool,
                       file_session_id: &str, line_number: i64, message_type: &str) -> ConversationRow {
        let fallback = utils::decode_project_path(project_dir);
        ConversationRow {
            source: source.to_string(),
            session_id: base.session_id.clone().unwrap_or_else(|| file_session_id.to_string()),
            project_path: base.cwd.clone().unwrap_or(fallback),
            project_dir: project_dir.to_string(),
            file_name: file_name.to_string(),
            is_agent,
            line_number,
            message_type: message_type.to_string(),
            uuid: base.uuid.clone(),
            parent_uuid: base.parent_uuid.clone(),
            timestamp: base.timestamp.clone(),
            slug: base.slug.clone(),
            git_branch: base.git_branch.clone(),
            cwd: base.cwd.clone(),
            version: base.version.clone(),
            ..Default::default()
        }
    }

    fn claude_simple_row(source: &str, project_dir: &str, file_name: &str, is_agent: bool,
                         file_session_id: &str, line_number: i64, message_type: &str) -> ConversationRow {
        ConversationRow {
            source: source.to_string(),
            session_id: file_session_id.to_string(),
            project_path: utils::decode_project_path(project_dir),
            project_dir: project_dir.to_string(),
            file_name: file_name.to_string(),
            is_agent,
            line_number,
            message_type: message_type.to_string(),
            ..Default::default()
        }
    }

    fn claude_message_to_row(source: &str, msg: ConversationMessage, project_dir: &str, file_name: &str,
                             is_agent: bool, file_session_id: &str, line_number: i64) -> ConversationRow {
        match msg {
            ConversationMessage::User(u) => {
                let content = u.message.as_ref()
                    .and_then(|m| m.content.as_ref())
                    .map(utils::extract_text_content);
                let mut row = Self::claude_base_row(source, &u.base, project_dir, file_name, is_agent, file_session_id, line_number, "user");
                row.message_role = Some("user".to_string());
                row.message_content = content;
                row
            }
            ConversationMessage::Assistant(a) => {
                let msg_content = a.message.as_ref();
                let mut row = Self::claude_base_row(source, &a.base, project_dir, file_name, is_agent, file_session_id, line_number, "assistant");
                row.message_role = Some("assistant".to_string());

                row.message_content = msg_content
                    .and_then(|m| m.content.as_ref())
                    .map(|blocks| blocks.iter().filter_map(|b| match b {
                        ContentBlock::Text { text } => Some(text.as_str()),
                        _ => None,
                    }).collect::<Vec<_>>().join("\n"));

                if let Some(blocks) = msg_content.and_then(|m| m.content.as_ref()) {
                    for b in blocks {
                        if let ContentBlock::ToolUse { id, name, input } = b {
                            row.tool_name = name.clone();
                            row.tool_use_id = id.clone();
                            row.tool_input = input.as_ref().map(|i| i.to_string());
                            break;
                        }
                    }
                }

                let usage = msg_content.and_then(|m| m.usage.as_ref());
                row.model = msg_content.and_then(|m| m.model.clone());
                row.input_tokens = usage.and_then(|u| u.input_tokens);
                row.output_tokens = usage.and_then(|u| u.output_tokens);
                row.cache_creation_tokens = usage.and_then(|u| u.cache_creation_input_tokens);
                row.cache_read_tokens = usage.and_then(|u| u.cache_read_input_tokens);
                row.stop_reason = msg_content.and_then(|m| m.stop_reason.clone());
                row
            }
            ConversationMessage::System(s) => {
                let mut row = Self::claude_base_row(source, &s.base, project_dir, file_name, is_agent, file_session_id, line_number, "system");
                row.message_content = s.content.as_ref().map(utils::extract_text_content);
                row
            }
            ConversationMessage::Summary(s) => {
                let mut row = Self::claude_simple_row(source, project_dir, file_name, is_agent, file_session_id, line_number, "summary");
                row.message_content = s.summary;
                row
            }
            ConversationMessage::FileHistorySnapshot { .. } => {
                Self::claude_simple_row(source, project_dir, file_name, is_agent, file_session_id, line_number, "file-history-snapshot")
            }
            ConversationMessage::QueueOperation(q) => {
                let mut row = Self::claude_simple_row(source, project_dir, file_name, is_agent, file_session_id, line_number, "queue-operation");
                if let Some(sid) = q.session_id { row.session_id = sid; }
                row.timestamp = q.timestamp;
                row.message_content = q.content;
                row
            }
        }
    }

    fn load_claude_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        let files = utils::discover_conversation_files(base_path);
        Self::load_claude_jsonl_rows("claude", &files)
    }

    /// Claude Desktop ("Cowork") stores transcripts using the same camelCase
    /// schema as Claude Code, so this delegates to the shared line-parser; only
    /// the discovered file set and the `source` label differ.
    fn load_claude_desktop_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        let files = utils::discover_claude_desktop_files(base_path);
        Self::load_claude_jsonl_rows("claude-desktop", &files)
    }

    /// Parse a set of discovered Claude-schema JSONL transcript files into rows.
    /// Shared by both `Provider::Claude` and `Provider::ClaudeDesktop`.
    fn load_claude_jsonl_rows(
        source: &str,
        files: &[(String, bool, std::path::PathBuf)],
    ) -> Vec<ConversationRow> {
        let mut rows = Vec::new();

        for (project_dir, is_agent, file_path) in files {
            let file_name = file_path.file_name()
                .map(|f| f.to_string_lossy().to_string())
                .unwrap_or_default();
            let file_session_id = utils::fallback_session_id(file_path);

            let file = match std::fs::File::open(file_path) {
                Ok(f) => f,
                Err(_) => continue,
            };

            let file_rows_start = rows.len();
            let mut file_cwd: Option<String> = None;
            let mut file_line: i64 = 0;

            for line_result in BufReader::new(file).lines() {
                file_line += 1;
                let line = match line_result {
                    Ok(l) if !l.trim().is_empty() => l,
                    _ => continue,
                };

                let row = match serde_json::from_str::<ConversationMessage>(&line) {
                    Ok(msg) => Self::claude_message_to_row(source, msg, project_dir, &file_name, *is_agent, &file_session_id, file_line),
                    Err(e) => {
                        let mut row = Self::claude_simple_row(source, project_dir, &file_name, *is_agent, &file_session_id, file_line, "_parse_error");
                        row.message_content = Some(format!("Parse error: {}", e));
                        row
                    }
                };

                if file_cwd.is_none() && row.cwd.is_some() {
                    file_cwd = row.cwd.clone();
                }
                rows.push(row);
            }

            if let Some(ref cwd) = file_cwd {
                let fallback = utils::decode_project_path(project_dir);
                for row in &mut rows[file_rows_start..] {
                    if row.project_path == fallback {
                        row.project_path = cwd.clone();
                    }
                }
            }
        }
        rows
    }
}

// ─── Copilot loading ───

/// Session-level metadata extracted from workspace.yaml and session.start events.
struct CopilotSessionMeta {
    session_id: String,
    project_path: String,
    git_branch: Option<String>,
    repository: Option<String>,
    version: Option<String>,
    model: Option<String>,
}

impl Conversations {
    fn load_copilot_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        let event_files = utils::discover_copilot_event_files(base_path);
        let mut rows = Vec::new();

        for (dir_session_id, file_path) in &event_files {
            // Read workspace.yaml for session metadata
            let workspace = file_path.parent()
                .and_then(|p| if p.join("workspace.yaml").exists() { utils::read_workspace_yaml(p) } else { None });

            let mut meta = CopilotSessionMeta {
                session_id: workspace.as_ref().and_then(|w| w.id.clone()).unwrap_or_else(|| dir_session_id.clone()),
                project_path: workspace.as_ref().and_then(|w| w.cwd.clone()).unwrap_or_default(),
                git_branch: workspace.as_ref().and_then(|w| w.branch.clone()),
                repository: workspace.as_ref().and_then(|w| w.repository.clone()),
                version: None,
                model: None,
            };

            let file_name = file_path.file_name()
                .map(|f| f.to_string_lossy().to_string())
                .unwrap_or_default();

            let file = match std::fs::File::open(file_path) {
                Ok(f) => f,
                Err(_) => continue,
            };

            let mut file_line: i64 = 0;
            for line_result in BufReader::new(file).lines() {
                file_line += 1;
                let line = match line_result {
                    Ok(l) if !l.trim().is_empty() => l,
                    _ => continue,
                };

                let event = match serde_json::from_str::<CopilotEvent>(&line) {
                    Ok(e) => e,
                    Err(e) => {
                        rows.push(ConversationRow {
                            source: "copilot".to_string(),
                            session_id: meta.session_id.clone(),
                            file_name: file_name.clone(),
                            line_number: file_line,
                            message_type: "_parse_error".to_string(),
                            message_content: Some(format!("Parse error: {}", e)),
                            ..Default::default()
                        });
                        continue;
                    }
                };

                // Update session metadata from session.start
                if event.event_type == "session.start" {
                    if let Ok(data) = serde_json::from_value::<SessionStartData>(event.data.clone()) {
                        if let Some(sid) = &data.session_id { meta.session_id = sid.clone(); }
                        if let Some(ver) = &data.copilot_version { meta.version = Some(ver.clone()); }
                        if let Some(ctx) = &data.context {
                            if let Some(cwd) = &ctx.cwd { meta.project_path = cwd.clone(); }
                            if let Some(br) = &ctx.branch { meta.git_branch = Some(br.clone()); }
                            if let Some(repo) = &ctx.repository { meta.repository = Some(repo.clone()); }
                        }
                    }
                }

                // Track model changes
                if event.event_type == "session.model_change" {
                    if let Ok(data) = serde_json::from_value::<ModelChangeData>(event.data.clone()) {
                        if let Some(m) = data.new_model { meta.model = Some(m); }
                    }
                }

                let row = Self::copilot_event_to_row(&event, &meta, &file_name, file_line);
                rows.push(row);
            }

            // Backfill session metadata to all rows from this file
            let start = rows.len().saturating_sub(file_line as usize);
            for row in &mut rows[start..] {
                if row.session_id.is_empty() { row.session_id = meta.session_id.clone(); }
            }
        }
        rows
    }

    fn copilot_event_to_row(event: &CopilotEvent, meta: &CopilotSessionMeta,
                            file_name: &str, line_number: i64) -> ConversationRow {
        let (message_type, message_role) = Self::copilot_type_role(&event.event_type);

        let mut row = ConversationRow {
            source: "copilot".to_string(),
            session_id: meta.session_id.clone(),
            project_path: meta.project_path.clone(),
            file_name: file_name.to_string(),
            line_number,
            message_type: message_type.to_string(),
            uuid: event.id.clone(),
            parent_uuid: event.parent_id.clone(),
            timestamp: event.timestamp.clone(),
            message_role: message_role.map(String::from),
            git_branch: meta.git_branch.clone(),
            cwd: if meta.project_path.is_empty() { None } else { Some(meta.project_path.clone()) },
            version: meta.version.clone(),
            model: meta.model.clone(),
            repository: meta.repository.clone(),
            ..Default::default()
        };

        // Extract type-specific fields
        match event.event_type.as_str() {
            "user.message" => {
                if let Ok(data) = serde_json::from_value::<UserMessageData>(event.data.clone()) {
                    row.message_content = data.content;
                }
            }
            "assistant.message" => {
                if let Ok(data) = serde_json::from_value::<AssistantMessageData>(event.data.clone()) {
                    row.message_content = data.content;
                    if let Some(reqs) = &data.tool_requests {
                        if let Some(first) = reqs.first() {
                            row.tool_name = first.name.clone();
                            row.tool_use_id = first.tool_call_id.clone();
                            row.tool_input = first.arguments.as_ref().map(|a| a.to_string());
                        }
                    }
                }
            }
            "assistant.reasoning" => {
                if let Ok(data) = serde_json::from_value::<ReasoningData>(event.data.clone()) {
                    row.message_content = data.content;
                }
            }
            "tool.execution_start" => {
                if let Ok(data) = serde_json::from_value::<ToolExecutionStartData>(event.data.clone()) {
                    row.tool_name = data.tool_name;
                    row.tool_use_id = data.tool_call_id;
                    row.tool_input = data.arguments.as_ref().map(|a| a.to_string());
                }
            }
            "tool.execution_complete" => {
                if let Ok(data) = serde_json::from_value::<ToolExecutionCompleteData>(event.data.clone()) {
                    row.tool_use_id = data.tool_call_id;
                    row.message_content = data.result.and_then(|r| r.content);
                }
            }
            "session.truncation" => {
                if let Ok(data) = serde_json::from_value::<TruncationData>(event.data.clone()) {
                    row.input_tokens = data.pre_truncation_tokens;
                    row.output_tokens = data.post_truncation_tokens;
                }
            }
            "session.error" => {
                if let Ok(data) = serde_json::from_value::<SessionErrorData>(event.data.clone()) {
                    row.message_content = data.message;
                }
            }
            "session.start" => {
                if let Ok(data) = serde_json::from_value::<SessionStartData>(event.data.clone()) {
                    row.version = data.copilot_version;
                }
            }
            _ => {} // turn_start, turn_end, info, resume, abort, compaction — no extra fields
        }

        row
    }

    fn copilot_type_role(event_type: &str) -> (&'static str, Option<&'static str>) {
        match event_type {
            "user.message" => ("user", Some("user")),
            "assistant.message" => ("assistant", Some("assistant")),
            "assistant.reasoning" => ("reasoning", Some("assistant")),
            "assistant.turn_start" => ("turn_start", Some("assistant")),
            "assistant.turn_end" => ("turn_end", Some("assistant")),
            "tool.execution_start" => ("tool_start", Some("tool")),
            "tool.execution_complete" => ("tool_result", Some("tool")),
            "session.start" => ("session_start", None),
            "session.resume" => ("session_resume", None),
            "session.info" => ("session_info", None),
            "session.error" => ("session_error", None),
            "session.truncation" => ("truncation", None),
            "session.compaction_start" => ("compaction_start", None),
            "session.compaction_complete" => ("compaction_complete", None),
            "session.model_change" => ("model_change", None),
            "abort" => ("abort", None),
            _ => ("unknown", None),
        }
    }
}

// ─── Codex loading ───
//
// rollout-*.jsonl is a single ordered stream. `session_meta` (first line) and the
// latest `turn_context` are carried forward and applied to every emitted row —
// the same "session metadata backfill" technique used for Copilot above.
// `session_meta` / `turn_context` / `token_count` lines are NOT emitted as rows.

impl Conversations {
    fn load_codex_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        let files = utils::discover_codex_rollout_files(base_path);
        let mut rows = Vec::new();

        for (session_uuid, file_path) in &files {
            let file_name = file_path
                .file_name()
                .map(|f| f.to_string_lossy().to_string())
                .unwrap_or_default();

            let file = match std::fs::File::open(file_path) {
                Ok(f) => f,
                Err(_) => continue,
            };

            let mut meta = CodexSessionMeta::default();
            let mut current_model: Option<String> = None;
            let mut file_line: i64 = 0;
            // event_msg/{user,agent}_message duplicate the response_item/message
            // turns. Buffer them and only emit as a fallback for sessions that
            // carry no response_item/message rows, so canonical turns are never
            // double-counted.
            let mut has_response_message = false;
            let mut event_msg_fallback: Vec<ConversationRow> = Vec::new();

            for line_result in BufReader::new(file).lines() {
                file_line += 1;
                let line = match line_result {
                    Ok(l) if !l.trim().is_empty() => l,
                    _ => continue,
                };

                let parsed: CodexLine = match serde_json::from_str(&line) {
                    Ok(p) => p,
                    Err(e) => {
                        rows.push(ConversationRow {
                            source: "codex".to_string(),
                            session_id: session_uuid.clone(),
                            file_name: file_name.clone(),
                            line_number: file_line,
                            message_type: "_parse_error".to_string(),
                            message_content: Some(format!("Parse error: {}", e)),
                            ..Default::default()
                        });
                        continue;
                    }
                };

                match parsed.line_type.as_str() {
                    "session_meta" => {
                        if let Ok(m) =
                            serde_json::from_value::<CodexSessionMeta>(parsed.payload.clone())
                        {
                            meta = m;
                        }
                        continue; // not a conversation row
                    }
                    "turn_context" => {
                        if let Ok(tc) =
                            serde_json::from_value::<CodexTurnContext>(parsed.payload.clone())
                        {
                            if let Some(m) = tc.model {
                                current_model = Some(m);
                            }
                        }
                        continue;
                    }
                    _ => {}
                }

                if let Some(row) = Self::codex_line_to_row(
                    &parsed,
                    session_uuid,
                    &file_name,
                    file_line,
                    &meta,
                    current_model.as_deref(),
                ) {
                    if parsed.line_type == "event_msg"
                        && matches!(row.message_type.as_str(), "user" | "assistant")
                    {
                        event_msg_fallback.push(row);
                    } else {
                        if parsed.line_type == "response_item"
                            && parsed.payload.get("type").and_then(|v| v.as_str())
                                == Some("message")
                        {
                            has_response_message = true;
                        }
                        rows.push(row);
                    }
                }
            }

            if !has_response_message {
                rows.append(&mut event_msg_fallback);
            }
        }
        rows
    }

    fn codex_base_row(
        session_uuid: &str,
        file_name: &str,
        line_number: i64,
        timestamp: Option<String>,
        meta: &CodexSessionMeta,
        model: Option<&str>,
    ) -> ConversationRow {
        let git = meta.git.as_ref();
        ConversationRow {
            source: "codex".to_string(),
            session_id: session_uuid.to_string(),
            project_path: meta.cwd.clone().unwrap_or_default(),
            file_name: file_name.to_string(),
            line_number,
            timestamp,
            cwd: meta.cwd.clone(),
            git_branch: git.and_then(|g| g.branch.clone()),
            repository: git.and_then(|g| g.repository_url.clone()),
            version: meta.cli_version.clone(),
            model: model.map(String::from),
            ..Default::default()
        }
    }

    fn codex_line_to_row(
        parsed: &CodexLine,
        session_uuid: &str,
        file_name: &str,
        line_number: i64,
        meta: &CodexSessionMeta,
        model: Option<&str>,
    ) -> Option<ConversationRow> {
        let base = Self::codex_base_row(
            session_uuid,
            file_name,
            line_number,
            parsed.timestamp.clone(),
            meta,
            model,
        );

        match parsed.line_type.as_str() {
            "response_item" => {
                let item: CodexResponseItem =
                    serde_json::from_value(parsed.payload.clone()).ok()?;
                match item.item_type.as_deref() {
                    Some("message") => {
                        // Normalize to a role-specific type (user/assistant/...)
                        // like the other providers, so cross-source filters on
                        // message_type work; fall back to the raw role.
                        let role = item.role.clone();
                        let message_type = match role.as_deref() {
                            Some("user") => "user".to_string(),
                            Some("assistant") => "assistant".to_string(),
                            Some(other) => other.to_string(),
                            None => "message".to_string(),
                        };
                        Some(ConversationRow {
                            message_type,
                            message_role: role,
                            message_content: item.content.as_ref().map(utils::extract_text_content),
                            ..base
                        })
                    }
                    Some("reasoning") => Some(ConversationRow {
                        message_type: "reasoning".to_string(),
                        message_role: Some("assistant".to_string()),
                        message_content: item.summary.as_ref().map(utils::extract_text_content),
                        ..base
                    }),
                    Some("function_call") => Some(ConversationRow {
                        message_type: "function_call".to_string(),
                        message_role: Some("tool".to_string()),
                        tool_name: item.name.clone(),
                        tool_use_id: item.call_id.clone(),
                        tool_input: item.arguments.as_ref().map(|v| v.to_string()),
                        ..base
                    }),
                    Some("function_call_output") => Some(ConversationRow {
                        message_type: "function_call_output".to_string(),
                        message_role: Some("tool".to_string()),
                        tool_use_id: item.call_id.clone(),
                        message_content: item.output.as_ref().map(utils::extract_text_content),
                        ..base
                    }),
                    Some(other) => Some(ConversationRow {
                        message_type: other.to_string(),
                        ..base
                    }),
                    None => None,
                }
            }
            "event_msg" => {
                let ev: CodexEventMsg = serde_json::from_value(parsed.payload.clone()).ok()?;
                match ev.event_type.as_deref() {
                    // event_msg user/agent text duplicates the response_item
                    // message rows above. The loader buffers these and only
                    // emits them for sessions with no response_item/message
                    // rows, so canonical turns are never double-counted.
                    // task_started / task_complete / token_count are not
                    // conversation rows.
                    Some("user_message") => Some(ConversationRow {
                        message_type: "user".to_string(),
                        message_role: Some("user".to_string()),
                        message_content: ev.message.clone(),
                        ..base
                    }),
                    Some("agent_message") => Some(ConversationRow {
                        message_type: "assistant".to_string(),
                        message_role: Some("assistant".to_string()),
                        message_content: ev.message.clone(),
                        ..base
                    }),
                    _ => None,
                }
            }
            _ => None,
        }
    }
}

// ─── Gemini loading ───

impl Conversations {
    fn load_gemini_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        let chat_files = utils::discover_gemini_chat_files(base_path);
        let project_map = utils::read_gemini_project_map(base_path);
        let mut rows = Vec::new();

        for (project_hash, file_path) in &chat_files {
            let file_name = file_path
                .file_name()
                .map(|f| f.to_string_lossy().to_string())
                .unwrap_or_default();

            let content = match std::fs::read_to_string(file_path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            let session = match serde_json::from_str::<GeminiSession>(&content) {
                Ok(s) => s,
                Err(e) => {
                    rows.push(ConversationRow {
                        source: "gemini".to_string(),
                        session_id: project_hash.clone(),
                        project_dir: project_hash.clone(),
                        file_name: file_name.clone(),
                        line_number: 1,
                        message_type: "_parse_error".to_string(),
                        message_content: Some(format!("Parse error: {}", e)),
                        ..Default::default()
                    });
                    continue;
                }
            };

            let session_id = session
                .session_id
                .clone()
                .unwrap_or_else(|| project_hash.clone());
            // Resolve the project hash back to an absolute path when an alias
            // mapping exists; otherwise leave the project path empty (the hash
            // is an opaque SHA-256 of the original cwd).
            let project_path = project_map.get(project_hash).cloned().unwrap_or_default();
            let is_agent = session.kind.as_deref() == Some("subagent");

            // Each message gets a 1-based ordinal within the session file.
            let mut message_index: i64 = 0;
            for msg in &session.messages {
                message_index += 1;
                let (message_type, message_role) = Self::gemini_type_role(msg.message_type.as_deref());

                let mut row = ConversationRow {
                    source: "gemini".to_string(),
                    session_id: session_id.clone(),
                    project_path: project_path.clone(),
                    project_dir: project_hash.clone(),
                    file_name: file_name.clone(),
                    is_agent,
                    line_number: message_index,
                    message_type: message_type.to_string(),
                    uuid: msg.id.clone(),
                    timestamp: msg.timestamp.clone().or_else(|| session.start_time.clone()),
                    message_role: message_role.map(String::from),
                    message_content: msg.content.clone().filter(|c| !c.is_empty()),
                    model: msg.model.clone(),
                    cwd: if project_path.is_empty() { None } else { Some(project_path.clone()) },
                    ..Default::default()
                };

                if let Some(tokens) = &msg.tokens {
                    row.input_tokens = tokens.input;
                    row.output_tokens = tokens.output;
                    // Gemini reports a single `cached` figure (read-side reuse).
                    row.cache_read_tokens = tokens.cached;
                }

                // Every tool call is emitted as its own dedicated `tool_call` row
                // below, so the assistant row deliberately leaves the tool_* fields
                // unset. This keeps each invocation represented exactly once and
                // avoids double-counting the first call in tool-usage aggregates.
                let tool_calls = msg.tool_calls.as_deref().unwrap_or(&[]);
                rows.push(row);

                for tc in tool_calls {
                    rows.push(ConversationRow {
                        source: "gemini".to_string(),
                        session_id: session_id.clone(),
                        project_path: project_path.clone(),
                        project_dir: project_hash.clone(),
                        file_name: file_name.clone(),
                        is_agent,
                        line_number: message_index,
                        message_type: "tool_call".to_string(),
                        uuid: tc.id.clone(),
                        parent_uuid: msg.id.clone(),
                        timestamp: tc.timestamp.clone().or_else(|| msg.timestamp.clone()),
                        message_role: Some("tool".to_string()),
                        message_content: tc.status.clone(),
                        model: msg.model.clone(),
                        tool_name: tc.name.clone(),
                        tool_use_id: tc.id.clone(),
                        tool_input: tc.args.as_ref().map(|a| a.to_string()),
                        cwd: if project_path.is_empty() { None } else { Some(project_path.clone()) },
                        ..Default::default()
                    });
                }
            }
        }
        rows
    }

    /// Map a Gemini message `type` to (message_type, message_role).
    /// Gemini uses `gemini` for the assistant; everything else passes through.
    fn gemini_type_role(message_type: Option<&str>) -> (&'static str, Option<&'static str>) {
        match message_type {
            Some("user") => ("user", Some("user")),
            Some("gemini") => ("assistant", Some("assistant")),
            Some("info") => ("info", None),
            Some("error") => ("error", None),
            _ => ("unknown", None),
        }
    }
}

// ─── Cursor loading ───
//
// Cursor stores chat in a SQLite KV store (state.vscdb). `composerData:<id>` rows
// are conversations; `bubbleId:<composerId>:<bubbleId>` rows are messages. Order
// within a composer comes from its `fullConversationHeadersOnly` array.
//
// The `state.vscdb` SQLite file is read with a self-contained, pure-Rust,
// read-only reader (`crate::vscdb`) — no external SQLite dependency. The whole
// path is gated behind the default-on `cursor` cargo feature. Parsing is
// defensive: missing keys/rows are tolerated and never panic (every field falls
// back to NULL via `..Default::default()`).

#[cfg(feature = "cursor")]
impl Conversations {
    fn load_cursor_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        use crate::vscdb::VscDb;

        let db_path = if base_path.extension().map_or(false, |e| e == "vscdb") {
            base_path.to_path_buf()
        } else {
            base_path.join("state.vscdb")
        };

        let db = match VscDb::open(&db_path) {
            Some(db) => db,
            None => return Vec::new(),
        };

        // Single scan of the cursorDiskKV table; split the rows by key prefix.
        // (Equivalent to the two `key LIKE 'composerData:%' / 'bubbleId:%'`
        // queries the bundled-SQLite version used to run.)
        let mut composers: std::collections::HashMap<String, CursorComposer> =
            std::collections::HashMap::new();
        let mut bubbles: std::collections::HashMap<(String, String), CursorBubble> =
            std::collections::HashMap::new();

        for row in db.read_table("cursorDiskKV") {
            let key = match std::str::from_utf8(&row.key) {
                Ok(k) => k,
                Err(_) => continue,
            };
            if let Some(id) = key.strip_prefix("composerData:") {
                // 1. composers (sessions)
                if let Ok(c) = serde_json::from_slice::<CursorComposer>(&row.value) {
                    composers.insert(id.to_string(), c);
                }
            } else if key.starts_with("bubbleId:") {
                // 2. bubbles, keyed by (composerId, bubbleId)
                //    key = bubbleId:<composerId>:<bubbleId>
                let parts: Vec<&str> = key.splitn(3, ':').collect();
                if parts.len() == 3 {
                    if let Ok(b) = serde_json::from_slice::<CursorBubble>(&row.value) {
                        bubbles.insert((parts[1].to_string(), parts[2].to_string()), b);
                    }
                }
            }
        }

        // 3. Walk each composer's ordered headers, emit a row per bubble.
        let mut rows = Vec::new();
        let mut composer_ids: Vec<&String> = composers.keys().collect();
        composer_ids.sort();

        for composer_id in composer_ids {
            let composer = &composers[composer_id];
            let model = composer
                .model_config
                .as_ref()
                .and_then(|m| m.model_name.clone());
            let headers = composer.headers.clone().unwrap_or_default();
            let mut prev_bubble: Option<String> = None;

            for (idx, header) in headers.iter().enumerate() {
                let bubble_id = match &header.bubble_id {
                    Some(b) => b.clone(),
                    None => continue,
                };
                let bubble = bubbles.get(&(composer_id.clone(), bubble_id.clone()));

                let (message_type, role) = match header.bubble_type {
                    Some(1) => ("user", Some("user")),
                    Some(2) => ("assistant", Some("assistant")),
                    _ => ("unknown", None),
                };

                let tool = bubble.and_then(|b| b.tool_former_data.as_ref());
                let timestamp = bubble
                    .and_then(|b| {
                        b.created_at
                            .or_else(|| b.timing_info.as_ref().and_then(|t| t.client_start_time))
                    })
                    .map(utils::epoch_ms_to_iso);

                rows.push(ConversationRow {
                    source: "cursor".to_string(),
                    session_id: composer_id.clone(),
                    file_name: "state.vscdb".to_string(),
                    line_number: idx as i64 + 1,
                    message_type: message_type.to_string(),
                    message_role: role.map(String::from),
                    uuid: Some(bubble_id.clone()),
                    parent_uuid: prev_bubble.clone(),
                    timestamp,
                    is_agent: bubble.and_then(|b| b.is_agentic).unwrap_or(false),
                    message_content: bubble.and_then(|b| b.text.clone()),
                    model: model.clone(),
                    tool_name: tool.and_then(|t| t.name.clone().or_else(|| t.tool.clone())),
                    tool_use_id: tool.and_then(|t| t.tool_call_id.clone()),
                    tool_input: tool.and_then(|t| {
                        t.raw_args
                            .as_ref()
                            .or(t.params.as_ref())
                            .map(|v| v.to_string())
                    }),
                    input_tokens: bubble
                        .and_then(|b| b.token_count.as_ref())
                        .and_then(|t| t.input_tokens),
                    output_tokens: bubble
                        .and_then(|b| b.token_count.as_ref())
                        .and_then(|t| t.output_tokens),
                    ..Default::default()
                });
                prev_bubble = Some(bubble_id);
            }
        }
        rows
    }
}

#[cfg(not(feature = "cursor"))]
impl Conversations {
    fn load_cursor_rows(_base_path: &std::path::Path) -> Vec<ConversationRow> {
        Vec::new()
    }
}

// ─── Grok loading ───
//
// chat_history.jsonl is the transcript (no per-line timestamp; reasoning has
// `id`). Session metadata (timestamp, branch, model, repo, slug, version,
// session-level reasoning_effort) comes from summary.json and is applied to
// every row — same "session metadata backfill" technique as Copilot.
//
// Subagent children (linked via parent/subagents/<id>/meta.json) get
// is_agent=true and parent_uuid=parent_session_id.
//
// Token usage is not on chat_history lines. Sibling updates.jsonl turn_completed
// events carry cumulative-per-prompt usage; we stamp the last usable snapshot
// onto every row of the session (session/prompt aggregate, not per-message).

impl Conversations {
    fn load_grok_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        let files = utils::discover_grok_session_files(base_path);
        let subagent_parents = utils::discover_grok_subagent_parents(base_path);
        let mut rows = Vec::new();

        for (session_uuid, decoded_cwd, encoded_cwd, file_path) in &files {
            let session_dir = file_path.parent().unwrap_or(file_path);
            let summary = utils::read_grok_summary(session_dir);
            let usage = utils::read_grok_last_turn_usage(session_dir);

            let session_ts = summary.as_ref().and_then(|s| s.created_at.clone());
            let git_branch = summary.as_ref().and_then(|s| s.head_branch.clone());
            let repository = summary
                .as_ref()
                .and_then(|s| s.git_remotes.as_ref())
                .and_then(|r| r.first().cloned());
            let session_model = summary.as_ref().and_then(|s| s.current_model_id.clone());
            let session_effort = summary.as_ref().and_then(|s| s.reasoning_effort.clone());
            let slug = summary.as_ref().and_then(|s| s.generated_title.clone());
            let version = summary.as_ref().and_then(|s| {
                s.chat_format_version.as_ref().map(|v| match v {
                    serde_json::Value::String(s) => s.clone(),
                    other => other.to_string(),
                })
            });
            let project_path = summary
                .as_ref()
                .and_then(|s| s.git_root_dir.clone())
                .unwrap_or_else(|| decoded_cwd.clone());

            let is_agent = subagent_parents.contains_key(session_uuid);
            let parent_uuid = subagent_parents.get(session_uuid).cloned();

            let file = match std::fs::File::open(file_path) {
                Ok(f) => f,
                Err(_) => continue,
            };

            let mut file_line: i64 = 0;
            for line_result in BufReader::new(file).lines() {
                file_line += 1;
                let line = match line_result {
                    Ok(l) if !l.trim().is_empty() => l,
                    _ => continue,
                };

                let base = ConversationRow {
                    source: "grok".to_string(),
                    session_id: session_uuid.clone(),
                    project_path: project_path.clone(),
                    project_dir: encoded_cwd.clone(),
                    file_name: "chat_history.jsonl".to_string(),
                    is_agent,
                    line_number: file_line,
                    parent_uuid: parent_uuid.clone(),
                    timestamp: session_ts.clone(),
                    slug: slug.clone(),
                    git_branch: git_branch.clone(),
                    cwd: Some(decoded_cwd.clone()),
                    version: version.clone(),
                    repository: repository.clone(),
                    // Session/prompt aggregate from last turn_completed (duplicated).
                    input_tokens: usage.as_ref().and_then(|u| u.input_tokens),
                    output_tokens: usage.as_ref().and_then(|u| u.output_tokens),
                    cache_read_tokens: usage.as_ref().and_then(|u| u.cached_read_tokens),
                    reasoning_tokens: usage.as_ref().and_then(|u| u.reasoning_tokens),
                    ..Default::default()
                };

                match serde_json::from_str::<GrokMessage>(&line) {
                    Ok(msg) => {
                        for row in Self::grok_message_to_rows(
                            msg,
                            base,
                            session_model.as_deref(),
                            session_effort.as_deref(),
                        ) {
                            rows.push(row);
                        }
                    }
                    Err(e) => rows.push(ConversationRow {
                        message_type: "_parse_error".to_string(),
                        message_content: Some(format!("Parse error: {}", e)),
                        ..base
                    }),
                }
            }
        }
        rows
    }

    /// Serialize tool `arguments` (JSON string or object) to a stable varchar.
    fn grok_tool_input(args: &Option<serde_json::Value>) -> Option<String> {
        args.as_ref().map(|v| match v {
            serde_json::Value::String(s) => s.clone(),
            other => other.to_string(),
        })
    }

    /// Map one chat_history line to one or more rows.
    /// Assistant with tool_calls → optional text row + one `tool_call` row per call
    /// (Gemini-style multi-tool fan-out; first tool is no longer collapsed).
    fn grok_message_to_rows(
        msg: GrokMessage,
        base: ConversationRow,
        session_model: Option<&str>,
        session_effort: Option<&str>,
    ) -> Vec<ConversationRow> {
        match msg {
            GrokMessage::User(u) => vec![ConversationRow {
                message_type: "user".to_string(),
                message_role: Some("user".to_string()),
                message_content: u.content.as_ref().map(utils::extract_text_content),
                ..base
            }],
            GrokMessage::Reasoning(r) => {
                // Like Codex: message_type=reasoning, role=assistant, summary text only.
                let effort = r
                    .reasoning_effort
                    .or_else(|| session_effort.map(String::from));
                vec![ConversationRow {
                    message_type: "reasoning".to_string(),
                    message_role: Some("assistant".to_string()),
                    uuid: r.id,
                    message_content: r.summary.as_ref().map(utils::extract_text_content),
                    stop_reason: effort,
                    model: session_model.map(String::from),
                    ..base
                }]
            }
            GrokMessage::Assistant(a) => {
                let model = a
                    .model_id
                    .clone()
                    .or_else(|| session_model.map(String::from));
                let effort = a
                    .reasoning_effort
                    .or_else(|| session_effort.map(String::from));
                let content = a
                    .content
                    .filter(|c| !c.is_empty());
                let mut out = Vec::new();

                // Text row when content is non-empty; if only tools, skip empty
                // assistant shell (tool rows alone).
                if content.is_some() || a.tool_calls.is_empty() {
                    out.push(ConversationRow {
                        message_type: "assistant".to_string(),
                        message_role: Some("assistant".to_string()),
                        message_content: content,
                        model: model.clone(),
                        stop_reason: effort.clone(),
                        ..base.clone()
                    });
                }

                for tc in &a.tool_calls {
                    out.push(ConversationRow {
                        message_type: "tool_call".to_string(),
                        message_role: Some("tool".to_string()),
                        model: model.clone(),
                        stop_reason: effort.clone(),
                        tool_name: tc.name.clone(),
                        tool_use_id: tc.id.clone(),
                        tool_input: Self::grok_tool_input(&tc.arguments),
                        ..base.clone()
                    });
                }
                out
            }
            GrokMessage::ToolResult(t) => vec![ConversationRow {
                message_type: "tool_result".to_string(),
                message_role: Some("tool".to_string()),
                tool_use_id: t.tool_call_id,
                message_content: t.content.as_ref().map(utils::extract_text_content),
                ..base
            }],
            GrokMessage::System(s) => vec![ConversationRow {
                message_type: "system".to_string(),
                message_content: s.content.as_ref().map(utils::extract_text_content),
                ..base
            }],
        }
    }
}


// ─── TableFunc implementation ───

impl TableFunc for Conversations {
    type Row = ConversationRow;

    fn columns() -> Vec<ColDef> {
        vec![
            vtab::varchar("source"),        vtab::varchar("session_id"),
            vtab::varchar("project_path"),  vtab::varchar("project_dir"),
            vtab::varchar("file_name"),     vtab::boolean("is_agent"),
            vtab::bigint("line_number"),    vtab::varchar("message_type"),
            vtab::varchar("uuid"),          vtab::varchar("parent_uuid"),
            vtab::varchar("timestamp"),     vtab::varchar("message_role"),
            vtab::varchar("message_content"), vtab::varchar("model"),
            vtab::varchar("tool_name"),     vtab::varchar("tool_use_id"),
            vtab::varchar("tool_input"),    vtab::bigint("input_tokens"),
            vtab::bigint("output_tokens"),  vtab::bigint("cache_creation_tokens"),
            vtab::bigint("cache_read_tokens"), vtab::bigint("reasoning_tokens"),
            vtab::varchar("slug"),
            vtab::varchar("git_branch"),    vtab::varchar("cwd"),
            vtab::varchar("version"),       vtab::varchar("stop_reason"),
            vtab::varchar("repository"),
        ]
    }

    fn load_rows(path: Option<&str>, source: Option<&str>) -> Vec<ConversationRow> {
        let base_path = utils::resolve_data_path(path);
        match detect::resolve_provider(&base_path, source) {
            Provider::Claude => Self::load_claude_rows(&base_path),
            Provider::ClaudeDesktop => Self::load_claude_desktop_rows(&base_path),
            Provider::Copilot => Self::load_copilot_rows(&base_path),
            Provider::Cursor => Self::load_cursor_rows(&base_path),
            Provider::Codex => Self::load_codex_rows(&base_path),
            Provider::Gemini => Self::load_gemini_rows(&base_path),
            Provider::Grok => Self::load_grok_rows(&base_path),
            Provider::Unknown => Vec::new(),
        }
    }

    fn write_row(output: &mut DataChunkHandle, idx: usize, row: &ConversationRow) {
        vtab::set_varchar(output, 0, idx, &row.source);
        vtab::set_varchar(output, 1, idx, &row.session_id);
        vtab::set_varchar(output, 2, idx, &row.project_path);
        vtab::set_varchar(output, 3, idx, &row.project_dir);
        vtab::set_varchar(output, 4, idx, &row.file_name);
        vtab::set_bool(output, 5, idx, row.is_agent);
        vtab::set_i64(output, 6, idx, row.line_number);
        vtab::set_varchar(output, 7, idx, &row.message_type);
        vtab::set_varchar_opt(output, 8, idx, row.uuid.as_deref());
        vtab::set_varchar_opt(output, 9, idx, row.parent_uuid.as_deref());
        vtab::set_varchar_opt(output, 10, idx, row.timestamp.as_deref());
        vtab::set_varchar_opt(output, 11, idx, row.message_role.as_deref());
        vtab::set_varchar_opt(output, 12, idx, row.message_content.as_deref());
        vtab::set_varchar_opt(output, 13, idx, row.model.as_deref());
        vtab::set_varchar_opt(output, 14, idx, row.tool_name.as_deref());
        vtab::set_varchar_opt(output, 15, idx, row.tool_use_id.as_deref());
        vtab::set_varchar_opt(output, 16, idx, row.tool_input.as_deref());
        vtab::set_i64_opt(output, 17, idx, row.input_tokens);
        vtab::set_i64_opt(output, 18, idx, row.output_tokens);
        vtab::set_i64_opt(output, 19, idx, row.cache_creation_tokens);
        vtab::set_i64_opt(output, 20, idx, row.cache_read_tokens);
        vtab::set_i64_opt(output, 21, idx, row.reasoning_tokens);
        vtab::set_varchar_opt(output, 22, idx, row.slug.as_deref());
        vtab::set_varchar_opt(output, 23, idx, row.git_branch.as_deref());
        vtab::set_varchar_opt(output, 24, idx, row.cwd.as_deref());
        vtab::set_varchar_opt(output, 25, idx, row.version.as_deref());
        vtab::set_varchar_opt(output, 26, idx, row.stop_reason.as_deref());
        vtab::set_varchar_opt(output, 27, idx, row.repository.as_deref());
    }
}
