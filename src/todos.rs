use crate::types::TodoItem;
use crate::utils;
use duckdb::{
    core::{DataChunkHandle, Inserter, LogicalTypeHandle, LogicalTypeId},
    vtab::{BindInfo, InitInfo, TableFunctionInfo, VTab},
    Result,
};
use std::ffi::CString;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

struct TodoRow {
    session_id: String,
    agent_id: String,
    item_index: i64,
    content: String,
    status: String,
    active_form: Option<String>,
}

#[repr(C)]
pub struct TodosBindData {
    rows: Mutex<Vec<TodoRow>>,
}

#[repr(C)]
pub struct TodosInitData {
    offset: AtomicUsize,
}

pub struct ReadTodosVTab;

impl ReadTodosVTab {
    fn load_rows(path: Option<&str>) -> Vec<TodoRow> {
        let base_path = utils::resolve_claude_path(path);
        let files = utils::discover_todo_files(&base_path);
        let mut rows = Vec::new();

        for (session_id, agent_id, file_path) in files {
            let content = match std::fs::read_to_string(&file_path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            let items: Vec<TodoItem> = match serde_json::from_str(&content) {
                Ok(items) => items,
                Err(_) => continue,
            };

            for (idx, item) in items.into_iter().enumerate() {
                rows.push(TodoRow {
                    session_id: session_id.clone(),
                    agent_id: agent_id.clone(),
                    item_index: idx as i64,
                    content: item.content.unwrap_or_default(),
                    status: item.status.unwrap_or_default(),
                    active_form: item.active_form,
                });
            }
        }
        rows
    }
}

impl VTab for ReadTodosVTab {
    type InitData = TodosInitData;
    type BindData = TodosBindData;

    fn bind(bind: &BindInfo) -> Result<Self::BindData, Box<dyn std::error::Error>> {
        bind.add_result_column(
            "session_id",
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        );
        bind.add_result_column(
            "agent_id",
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        );
        bind.add_result_column(
            "item_index",
            LogicalTypeHandle::from(LogicalTypeId::Bigint),
        );
        bind.add_result_column("content", LogicalTypeHandle::from(LogicalTypeId::Varchar));
        bind.add_result_column("status", LogicalTypeHandle::from(LogicalTypeId::Varchar));
        bind.add_result_column(
            "active_form",
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        );

        let path = if bind.get_parameter_count() > 0 {
            Some(bind.get_parameter(0).to_string())
        } else {
            None
        };

        let rows = Self::load_rows(path.as_deref());
        Ok(TodosBindData {
            rows: Mutex::new(rows),
        })
    }

    fn init(_: &InitInfo) -> Result<Self::InitData, Box<dyn std::error::Error>> {
        Ok(TodosInitData {
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
            v0.insert(i, CString::new(row.session_id.as_str()).unwrap_or_default());

            let mut v1 = output.flat_vector(1);
            v1.insert(i, CString::new(row.agent_id.as_str()).unwrap_or_default());

            let mut v2 = output.flat_vector(2);
            v2.as_mut_slice::<i64>()[i] = row.item_index;

            let mut v3 = output.flat_vector(3);
            v3.insert(i, CString::new(row.content.as_str()).unwrap_or_default());

            let mut v4 = output.flat_vector(4);
            v4.insert(i, CString::new(row.status.as_str()).unwrap_or_default());

            let mut v5 = output.flat_vector(5);
            match &row.active_form {
                Some(af) => v5.insert(i, CString::new(af.as_str()).unwrap_or_default()),
                None => v5.set_null(i),
            }
        }

        output.set_len(batch_size);
        init_data
            .offset
            .store(offset + batch_size, Ordering::Relaxed);

        Ok(())
    }

    fn parameters() -> Option<Vec<LogicalTypeHandle>> {
        Some(vec![LogicalTypeHandle::from(LogicalTypeId::Varchar)])
    }
}
