use crate::detect::{self, Provider};
use crate::types::claude::TodoItem;
use crate::utils;
use crate::vtab::{self, ColDef, TableFunc};
use duckdb::core::DataChunkHandle;

pub struct TodoRow {
    source: String,
    session_id: String,
    agent_id: Option<String>,
    file_name: String,
    item_index: i64,
    content: String,
    status: String,
    active_form: Option<String>,
}

pub struct Todos;

impl Todos {
    fn load_claude_rows(base_path: &std::path::Path) -> Vec<TodoRow> {
        let files = utils::discover_todo_files(base_path);
        let mut rows = Vec::new();

        for (session_id, agent_id, file_path) in files {
            let fname = file_path.file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default();

            let content = match std::fs::read_to_string(&file_path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            match serde_json::from_str::<Vec<TodoItem>>(&content) {
                Ok(items) => {
                    for (idx, item) in items.into_iter().enumerate() {
                        rows.push(TodoRow {
                            source: "claude".to_string(),
                            session_id: session_id.clone(),
                            agent_id: Some(agent_id.clone()),
                            file_name: fname.clone(),
                            item_index: idx as i64,
                            content: item.content.unwrap_or_default(),
                            status: item.status.unwrap_or_default(),
                            active_form: item.active_form,
                        });
                    }
                }
                Err(e) => {
                    rows.push(TodoRow {
                        source: "claude".to_string(),
                        session_id: session_id.clone(),
                        agent_id: Some(agent_id.clone()),
                        file_name: fname,
                        item_index: -1,
                        content: format!("Parse error: {}", e),
                        status: "_parse_error".to_string(),
                        active_form: None,
                    });
                }
            }
        }
        rows
    }

    fn load_copilot_rows(base_path: &std::path::Path) -> Vec<TodoRow> {
        let checkpoints = utils::discover_copilot_checkpoint_files(base_path);
        let mut rows = Vec::new();

        for (session_id, fname, file_path) in checkpoints {
            let content = match std::fs::read_to_string(&file_path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            let mut item_index: i64 = 0;
            for line in content.lines() {
                let trimmed = line.trim();
                if let Some(rest) = trimmed.strip_prefix("- [x] ").or_else(|| trimmed.strip_prefix("- [X] ")) {
                    rows.push(TodoRow {
                        source: "copilot".to_string(),
                        session_id: session_id.clone(),
                        agent_id: None,
                        file_name: fname.clone(),
                        item_index,
                        content: rest.to_string(),
                        status: "completed".to_string(),
                        active_form: None,
                    });
                    item_index += 1;
                } else if let Some(rest) = trimmed.strip_prefix("- [ ] ") {
                    rows.push(TodoRow {
                        source: "copilot".to_string(),
                        session_id: session_id.clone(),
                        agent_id: None,
                        file_name: fname.clone(),
                        item_index,
                        content: rest.to_string(),
                        status: "pending".to_string(),
                        active_form: None,
                    });
                    item_index += 1;
                }
            }
        }
        rows
    }
}

impl TableFunc for Todos {
    type Row = TodoRow;

    fn columns() -> Vec<ColDef> {
        vec![
            vtab::varchar("source"),
            vtab::varchar("session_id"),
            vtab::varchar("agent_id"),
            vtab::varchar("file_name"),
            vtab::bigint("item_index"),
            vtab::varchar("content"),
            vtab::varchar("status"),
            vtab::varchar("active_form"),
        ]
    }

    fn load_rows(path: Option<&str>, source: Option<&str>) -> Vec<TodoRow> {
        let base_path = utils::resolve_data_path(path);
        match detect::resolve_provider(&base_path, source) {
            Provider::Claude => Self::load_claude_rows(&base_path),
            Provider::Copilot => Self::load_copilot_rows(&base_path),
            // Claude Desktop has no top-level todos/ directory; return empty.
            Provider::ClaudeDesktop | Provider::Unknown => Vec::new(),
        }
    }

    fn write_row(output: &mut DataChunkHandle, idx: usize, row: &TodoRow) {
        vtab::set_varchar(output, 0, idx, &row.source);
        vtab::set_varchar(output, 1, idx, &row.session_id);
        vtab::set_varchar_opt(output, 2, idx, row.agent_id.as_deref());
        vtab::set_varchar(output, 3, idx, &row.file_name);
        vtab::set_i64(output, 4, idx, row.item_index);
        vtab::set_varchar(output, 5, idx, &row.content);
        vtab::set_varchar(output, 6, idx, &row.status);
        vtab::set_varchar_opt(output, 7, idx, row.active_form.as_deref());
    }
}
