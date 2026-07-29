use crate::detect::{self, Provider};
use crate::utils;
use crate::vtab::{self, ColDef, TableFunc};
use duckdb::core::DataChunkHandle;

pub struct PlanRow {
    source: String,
    session_id: Option<String>,
    plan_name: String,
    file_name: String,
    file_path: String,
    content: String,
    file_size: i64,
}

pub struct Plans;

impl Plans {
    fn load_claude_rows(base_path: &std::path::Path) -> Vec<PlanRow> {
        utils::discover_plan_files(base_path).into_iter().filter_map(|file_path| {
            let content = std::fs::read_to_string(&file_path).ok()?;
            let file_size = std::fs::metadata(&file_path).map(|m| m.len() as i64).unwrap_or(0);
            Some(PlanRow {
                source: "claude".to_string(),
                session_id: None,
                plan_name: file_path.file_stem()?.to_string_lossy().to_string(),
                file_name: file_path.file_name()?.to_string_lossy().to_string(),
                file_path: file_path.to_string_lossy().to_string(),
                content,
                file_size,
            })
        }).collect()
    }

    fn load_copilot_rows(base_path: &std::path::Path) -> Vec<PlanRow> {
        utils::discover_copilot_plan_files(base_path).into_iter().filter_map(|(session_id, file_path)| {
            let content = std::fs::read_to_string(&file_path).ok()?;
            let file_size = std::fs::metadata(&file_path).map(|m| m.len() as i64).unwrap_or(0);
            let workspace = file_path.parent().and_then(|p| utils::read_workspace_yaml(p));
            let plan_name = workspace.and_then(|w| w.summary).unwrap_or_else(|| session_id.clone());
            Some(PlanRow {
                source: "copilot".to_string(),
                session_id: Some(session_id),
                plan_name,
                file_name: file_path.file_name()?.to_string_lossy().to_string(),
                file_path: file_path.to_string_lossy().to_string(),
                content,
                file_size,
            })
        }).collect()
    }

    /// Grok: `sessions/<cwd-enc>/<session-id>/plan.md` (and plan.json when present).
    fn load_grok_rows(base_path: &std::path::Path) -> Vec<PlanRow> {
        let mut rows = Vec::new();
        let mut session_dirs = Vec::new();
        if base_path.join("plan.md").is_file() {
            session_dirs.push(base_path.to_path_buf());
        }
        let sessions = base_path.join("sessions");
        if sessions.is_dir() {
            for cwd_ent in std::fs::read_dir(&sessions).into_iter().flatten().flatten() {
                if !cwd_ent.path().is_dir() {
                    continue;
                }
                for sess in std::fs::read_dir(cwd_ent.path()).into_iter().flatten().flatten() {
                    let sp = sess.path();
                    if sp.is_dir() && sp.join("plan.md").is_file() {
                        session_dirs.push(sp);
                    }
                }
            }
        }
        session_dirs.sort();
        for sp in session_dirs {
            let session_id = sp
                .file_name()
                .map(|s| s.to_string_lossy().to_string());
            for name in ["plan.md", "plan.json"] {
                let fp = sp.join(name);
                if !fp.is_file() {
                    continue;
                }
                let Ok(content) = std::fs::read_to_string(&fp) else {
                    continue;
                };
                let file_size = std::fs::metadata(&fp).map(|m| m.len() as i64).unwrap_or(0);
                rows.push(PlanRow {
                    source: "grok".to_string(),
                    session_id: session_id.clone(),
                    plan_name: fp
                        .file_stem()
                        .map(|s| s.to_string_lossy().to_string())
                        .unwrap_or_else(|| "plan".to_string()),
                    file_name: name.to_string(),
                    file_path: fp.to_string_lossy().to_string(),
                    content,
                    file_size,
                });
            }
        }
        rows
    }
}

impl TableFunc for Plans {
    type Row = PlanRow;

    fn columns() -> Vec<ColDef> {
        vec![
            vtab::varchar("source"),
            vtab::varchar("session_id"),
            vtab::varchar("plan_name"),
            vtab::varchar("file_name"),
            vtab::varchar("file_path"),
            vtab::varchar("content"),
            vtab::bigint("file_size"),
        ]
    }

    fn load_rows(path: Option<&str>, source: Option<&str>) -> Vec<PlanRow> {
        let base_path = utils::resolve_data_path(path);
        match detect::resolve_provider(&base_path, source) {
            Provider::Claude => Self::load_claude_rows(&base_path),
            Provider::Copilot => Self::load_copilot_rows(&base_path),
            // Claude Desktop has no top-level plans/ directory; Cursor has no
            // standalone plan files; Codex plans live inline in the rollout stream
            // and Gemini plan steps live inline in the chat transcript (no
            // standalone plan files). Return empty.
            Provider::Grok => Self::load_grok_rows(&base_path),
            Provider::ClaudeDesktop
            | Provider::Cursor
            | Provider::Codex
            | Provider::Gemini
            | Provider::Unknown => Vec::new(),
        }
    }

    fn write_row(output: &mut DataChunkHandle, idx: usize, row: &PlanRow) {
        vtab::set_varchar(output, 0, idx, &row.source);
        vtab::set_varchar_opt(output, 1, idx, row.session_id.as_deref());
        vtab::set_varchar(output, 2, idx, &row.plan_name);
        vtab::set_varchar(output, 3, idx, &row.file_name);
        vtab::set_varchar(output, 4, idx, &row.file_path);
        vtab::set_varchar(output, 5, idx, &row.content);
        vtab::set_i64(output, 6, idx, row.file_size);
    }
}
