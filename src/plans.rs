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
            // Claude Desktop has no top-level plans/ directory; return empty.
            Provider::ClaudeDesktop | Provider::Unknown => Vec::new(),
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
