use crate::types::HistoryEntry;
use crate::utils;
use duckdb::{
    core::{DataChunkHandle, Inserter, LogicalTypeHandle, LogicalTypeId},
    vtab::{BindInfo, InitInfo, TableFunctionInfo, VTab},
    Result,
};
use std::ffi::CString;
use std::io::{BufRead, BufReader};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

struct HistoryRow {
    line_number: i64,
    timestamp_ms: Option<i64>,
    project: Option<String>,
    session_id: Option<String>,
    display: Option<String>,
    pasted_contents: Option<String>,
}

#[repr(C)]
pub struct HistoryBindData {
    rows: Mutex<Vec<HistoryRow>>,
}

#[repr(C)]
pub struct HistoryInitData {
    offset: AtomicUsize,
}

pub struct ReadHistoryVTab;

impl ReadHistoryVTab {
    fn load_rows(path: Option<&str>) -> Vec<HistoryRow> {
        let base_path = utils::resolve_claude_path(path);
        let history_path = utils::history_file_path(&base_path);
        let mut rows = Vec::new();

        if !history_path.is_file() {
            return rows;
        }

        let file = match std::fs::File::open(&history_path) {
            Ok(f) => f,
            Err(_) => return rows,
        };
        let reader = BufReader::new(file);

        for (line_idx, line_result) in reader.lines().enumerate() {
            let line = match line_result {
                Ok(l) => l,
                Err(_) => continue,
            };
            if line.trim().is_empty() {
                continue;
            }

            match serde_json::from_str::<HistoryEntry>(&line) {
                Ok(entry) => {
                    rows.push(HistoryRow {
                        line_number: (line_idx + 1) as i64,
                        timestamp_ms: entry.timestamp.map(|t| t as i64),
                        project: entry.project,
                        session_id: entry.session_id,
                        display: entry.display,
                        pasted_contents: entry
                            .pasted_contents
                            .map(|v| v.to_string()),
                    });
                }
                Err(e) => {
                    rows.push(HistoryRow {
                        line_number: (line_idx + 1) as i64,
                        timestamp_ms: None,
                        project: None,
                        session_id: None,
                        display: Some(format!("Parse error: {}", e)),
                        pasted_contents: None,
                    });
                }
            }
        }

        rows
    }
}

impl VTab for ReadHistoryVTab {
    type InitData = HistoryInitData;
    type BindData = HistoryBindData;

    fn bind(bind: &BindInfo) -> Result<Self::BindData, Box<dyn std::error::Error>> {
        bind.add_result_column(
            "line_number",
            LogicalTypeHandle::from(LogicalTypeId::Bigint),
        );
        bind.add_result_column(
            "timestamp_ms",
            LogicalTypeHandle::from(LogicalTypeId::Bigint),
        );
        bind.add_result_column("project", LogicalTypeHandle::from(LogicalTypeId::Varchar));
        bind.add_result_column(
            "session_id",
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        );
        bind.add_result_column("display", LogicalTypeHandle::from(LogicalTypeId::Varchar));
        bind.add_result_column(
            "pasted_contents",
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        );

        let path = if bind.get_parameter_count() > 0 {
            let p = bind.get_parameter(0).to_string();
            if p.is_empty() { None } else { Some(p) }
        } else {
            None
        };
        let named_path = bind.get_named_parameter("path").map(|v| v.to_string());
        let effective_path = named_path.or(path);

        let rows = Self::load_rows(effective_path.as_deref());
        Ok(HistoryBindData {
            rows: Mutex::new(rows),
        })
    }

    fn init(_: &InitInfo) -> Result<Self::InitData, Box<dyn std::error::Error>> {
        Ok(HistoryInitData {
            offset: AtomicUsize::new(0),
        })
    }

    fn func(
        func: &TableFunctionInfo<Self>,
        output: &mut DataChunkHandle,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let bind_data = func.get_bind_data();
        let init_data = func.get_init_data();
        let rows = bind_data.rows.lock().unwrap();

        let offset = init_data.offset.load(Ordering::Relaxed);
        if offset >= rows.len() {
            output.set_len(0);
            return Ok(());
        }

        let batch_size = std::cmp::min(2048, rows.len() - offset);

        for i in 0..batch_size {
            let row = &rows[offset + i];

            // line_number
            let mut v0 = output.flat_vector(0);
            v0.as_mut_slice::<i64>()[i] = row.line_number;

            // timestamp_ms
            let mut v1 = output.flat_vector(1);
            match row.timestamp_ms {
                Some(ts) => v1.as_mut_slice::<i64>()[i] = ts,
                None => v1.set_null(i),
            }

            // project
            let mut v2 = output.flat_vector(2);
            match &row.project {
                Some(p) => v2.insert(i, CString::new(p.as_str()).unwrap_or_default()),
                None => v2.set_null(i),
            }

            // session_id
            let mut v3 = output.flat_vector(3);
            match &row.session_id {
                Some(s) => v3.insert(i, CString::new(s.as_str()).unwrap_or_default()),
                None => v3.set_null(i),
            }

            // display
            let mut v4 = output.flat_vector(4);
            match &row.display {
                Some(d) => v4.insert(i, CString::new(d.as_str()).unwrap_or_default()),
                None => v4.set_null(i),
            }

            // pasted_contents
            let mut v5 = output.flat_vector(5);
            match &row.pasted_contents {
                Some(pc) => v5.insert(i, CString::new(pc.as_str()).unwrap_or_default()),
                None => v5.set_null(i),
            }
        }

        output.set_len(batch_size);
        init_data
            .offset
            .store(offset + batch_size, Ordering::Relaxed);

        Ok(())
    }

    fn named_parameters() -> Option<Vec<(String, LogicalTypeHandle)>> {
        Some(vec![(
            "path".to_string(),
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        )])
    }
}
