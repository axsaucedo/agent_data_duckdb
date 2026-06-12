use crate::detect::{self, Provider};
use crate::types::claude::StatsCache;
use crate::utils;
use crate::vtab::{self, ColDef, TableFunc};
use duckdb::core::DataChunkHandle;

pub struct StatsRow {
    source: String,
    date: String,
    message_count: i64,
    session_count: i64,
    tool_call_count: i64,
}

pub struct Stats;

impl TableFunc for Stats {
    type Row = StatsRow;

    fn columns() -> Vec<ColDef> {
        vec![
            vtab::varchar("source"),
            vtab::varchar("date"),
            vtab::bigint("message_count"),
            vtab::bigint("session_count"),
            vtab::bigint("tool_call_count"),
        ]
    }

    fn load_rows(path: Option<&str>, source: Option<&str>) -> Vec<StatsRow> {
        let base_path = utils::resolve_data_path(path);
        match detect::resolve_provider(&base_path, source) {
            Provider::Claude => {
                let stats_path = utils::stats_file_path(&base_path);
                let content = match std::fs::read_to_string(&stats_path) {
                    Ok(c) => c,
                    Err(_) => return Vec::new(),
                };
                let cache: StatsCache = match serde_json::from_str(&content) {
                    Ok(c) => c,
                    Err(_) => return Vec::new(),
                };
                cache.daily_activity.unwrap_or_default().into_iter().map(|day| StatsRow {
                    source: "claude".to_string(),
                    date: day.date.unwrap_or_default(),
                    message_count: day.message_count.unwrap_or(0),
                    session_count: day.session_count.unwrap_or(0),
                    tool_call_count: day.tool_call_count.unwrap_or(0),
                }).collect()
            }
            // Copilot and Claude Desktop have no stats equivalent; return empty
            Provider::ClaudeDesktop | Provider::Copilot | Provider::Unknown => Vec::new(),
        }
    }

    fn write_row(output: &mut DataChunkHandle, idx: usize, row: &StatsRow) {
        vtab::set_varchar(output, 0, idx, &row.source);
        vtab::set_varchar(output, 1, idx, &row.date);
        vtab::set_i64(output, 2, idx, row.message_count);
        vtab::set_i64(output, 3, idx, row.session_count);
        vtab::set_i64(output, 4, idx, row.tool_call_count);
    }
}
