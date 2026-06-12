use crate::detect::{self, Provider};
use crate::types::claude::*;
use crate::types::copilot::*;
use crate::utils;
use crate::vtab::{self, ColDef, TableFunc};
use duckdb::core::DataChunkHandle;
use std::io::{BufRead, BufReader};

/// A flattened conversation row ready for output.
#[derive(Default)]
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
    fn claude_base_row(base: &BaseFields, project_dir: &str, file_name: &str, is_agent: bool,
                       file_session_id: &str, line_number: i64, message_type: &str) -> ConversationRow {
        let fallback = utils::decode_project_path(project_dir);
        ConversationRow {
            source: "claude".to_string(),
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

    fn claude_simple_row(project_dir: &str, file_name: &str, is_agent: bool,
                         file_session_id: &str, line_number: i64, message_type: &str) -> ConversationRow {
        ConversationRow {
            source: "claude".to_string(),
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

    fn claude_message_to_row(msg: ConversationMessage, project_dir: &str, file_name: &str,
                             is_agent: bool, file_session_id: &str, line_number: i64) -> ConversationRow {
        match msg {
            ConversationMessage::User(u) => {
                let content = u.message.as_ref()
                    .and_then(|m| m.content.as_ref())
                    .map(utils::extract_text_content);
                let mut row = Self::claude_base_row(&u.base, project_dir, file_name, is_agent, file_session_id, line_number, "user");
                row.message_role = Some("user".to_string());
                row.message_content = content;
                row
            }
            ConversationMessage::Assistant(a) => {
                let msg_content = a.message.as_ref();
                let mut row = Self::claude_base_row(&a.base, project_dir, file_name, is_agent, file_session_id, line_number, "assistant");
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
                let mut row = Self::claude_base_row(&s.base, project_dir, file_name, is_agent, file_session_id, line_number, "system");
                row.message_content = s.content.as_ref().map(utils::extract_text_content);
                row
            }
            ConversationMessage::Summary(s) => {
                let mut row = Self::claude_simple_row(project_dir, file_name, is_agent, file_session_id, line_number, "summary");
                row.message_content = s.summary;
                row
            }
            ConversationMessage::FileHistorySnapshot { .. } => {
                Self::claude_simple_row(project_dir, file_name, is_agent, file_session_id, line_number, "file-history-snapshot")
            }
            ConversationMessage::QueueOperation(q) => {
                let mut row = Self::claude_simple_row(project_dir, file_name, is_agent, file_session_id, line_number, "queue-operation");
                if let Some(sid) = q.session_id { row.session_id = sid; }
                row.timestamp = q.timestamp;
                row.message_content = q.content;
                row
            }
        }
    }

    fn load_claude_rows(base_path: &std::path::Path) -> Vec<ConversationRow> {
        let files = utils::discover_conversation_files(base_path);
        let mut rows = Vec::new();

        for (project_dir, is_agent, file_path) in &files {
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
                    Ok(msg) => Self::claude_message_to_row(msg, project_dir, &file_name, *is_agent, &file_session_id, file_line),
                    Err(e) => {
                        let mut row = Self::claude_simple_row(project_dir, &file_name, *is_agent, &file_session_id, file_line, "_parse_error");
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
            vtab::bigint("cache_read_tokens"), vtab::varchar("slug"),
            vtab::varchar("git_branch"),    vtab::varchar("cwd"),
            vtab::varchar("version"),       vtab::varchar("stop_reason"),
            vtab::varchar("repository"),
        ]
    }

    fn load_rows(path: Option<&str>, source: Option<&str>) -> Vec<ConversationRow> {
        let base_path = utils::resolve_data_path(path);
        match detect::resolve_provider(&base_path, source) {
            Provider::Claude => Self::load_claude_rows(&base_path),
            Provider::Copilot => Self::load_copilot_rows(&base_path),
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
        vtab::set_varchar_opt(output, 21, idx, row.slug.as_deref());
        vtab::set_varchar_opt(output, 22, idx, row.git_branch.as_deref());
        vtab::set_varchar_opt(output, 23, idx, row.cwd.as_deref());
        vtab::set_varchar_opt(output, 24, idx, row.version.as_deref());
        vtab::set_varchar_opt(output, 25, idx, row.stop_reason.as_deref());
        vtab::set_varchar_opt(output, 26, idx, row.repository.as_deref());
    }
}
