use crate::types::StatsCache;
use crate::utils;
use duckdb::{
    core::{DataChunkHandle, Inserter, LogicalTypeHandle, LogicalTypeId},
    vtab::{BindInfo, InitInfo, TableFunctionInfo, VTab},
    Result,
};
use std::ffi::CString;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

struct StatsRow {
    date: String,
    message_count: i64,
    session_count: i64,
    tool_call_count: i64,
}

#[repr(C)]
pub struct StatsBindData {
    rows: Mutex<Vec<StatsRow>>,
}

#[repr(C)]
pub struct StatsInitData {
    offset: AtomicUsize,
}

pub struct ReadStatsVTab;

impl ReadStatsVTab {
    fn load_rows(path: Option<&str>) -> Vec<StatsRow> {
        let base_path = utils::resolve_claude_path(path);
        let stats_path = utils::stats_file_path(&base_path);
        let mut rows = Vec::new();

        if !stats_path.is_file() {
            return rows;
        }

        let content = match std::fs::read_to_string(&stats_path) {
            Ok(c) => c,
            Err(_) => return rows,
        };

        let cache: StatsCache = match serde_json::from_str(&content) {
            Ok(c) => c,
            Err(_) => return rows,
        };

        if let Some(daily) = cache.daily_activity {
            for day in daily {
                rows.push(StatsRow {
                    date: day.date.unwrap_or_default(),
                    message_count: day.message_count.unwrap_or(0),
                    session_count: day.session_count.unwrap_or(0),
                    tool_call_count: day.tool_call_count.unwrap_or(0),
                });
            }
        }

        rows
    }
}

impl VTab for ReadStatsVTab {
    type InitData = StatsInitData;
    type BindData = StatsBindData;

    fn bind(bind: &BindInfo) -> Result<Self::BindData, Box<dyn std::error::Error>> {
        bind.add_result_column("date", LogicalTypeHandle::from(LogicalTypeId::Varchar));
        bind.add_result_column(
            "message_count",
            LogicalTypeHandle::from(LogicalTypeId::Bigint),
        );
        bind.add_result_column(
            "session_count",
            LogicalTypeHandle::from(LogicalTypeId::Bigint),
        );
        bind.add_result_column(
            "tool_call_count",
            LogicalTypeHandle::from(LogicalTypeId::Bigint),
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
        Ok(StatsBindData {
            rows: Mutex::new(rows),
        })
    }

    fn init(_: &InitInfo) -> Result<Self::InitData, Box<dyn std::error::Error>> {
        Ok(StatsInitData {
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

            let mut v0 = output.flat_vector(0);
            v0.insert(i, CString::new(row.date.as_str()).unwrap_or_default());

            let mut v1 = output.flat_vector(1);
            v1.as_mut_slice::<i64>()[i] = row.message_count;

            let mut v2 = output.flat_vector(2);
            v2.as_mut_slice::<i64>()[i] = row.session_count;

            let mut v3 = output.flat_vector(3);
            v3.as_mut_slice::<i64>()[i] = row.tool_call_count;
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
