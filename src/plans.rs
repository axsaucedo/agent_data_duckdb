use crate::utils;
use duckdb::{
    core::{DataChunkHandle, Inserter, LogicalTypeHandle, LogicalTypeId},
    vtab::{BindInfo, InitInfo, TableFunctionInfo, VTab},
    Result,
};
use std::ffi::CString;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

struct PlanRow {
    plan_name: String,
    file_path: String,
    content: String,
    file_size: i64,
}

#[repr(C)]
pub struct PlansBindData {
    rows: Mutex<Vec<PlanRow>>,
}

#[repr(C)]
pub struct PlansInitData {
    offset: AtomicUsize,
}

pub struct ReadPlansVTab;

impl ReadPlansVTab {
    fn load_rows(path: Option<&str>) -> Vec<PlanRow> {
        let base_path = utils::resolve_claude_path(path);
        let files = utils::discover_plan_files(&base_path);
        let mut rows = Vec::new();

        for file_path in files {
            let plan_name = file_path
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default();

            let content = match std::fs::read_to_string(&file_path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            let file_size = std::fs::metadata(&file_path)
                .map(|m| m.len() as i64)
                .unwrap_or(0);

            rows.push(PlanRow {
                plan_name,
                file_path: file_path.to_string_lossy().to_string(),
                content,
                file_size,
            });
        }
        rows
    }
}

impl VTab for ReadPlansVTab {
    type InitData = PlansInitData;
    type BindData = PlansBindData;

    fn bind(bind: &BindInfo) -> Result<Self::BindData, Box<dyn std::error::Error>> {
        bind.add_result_column(
            "plan_name",
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        );
        bind.add_result_column(
            "file_path",
            LogicalTypeHandle::from(LogicalTypeId::Varchar),
        );
        bind.add_result_column("content", LogicalTypeHandle::from(LogicalTypeId::Varchar));
        bind.add_result_column(
            "file_size",
            LogicalTypeHandle::from(LogicalTypeId::Bigint),
        );

        let path = if bind.get_parameter_count() > 0 {
            Some(bind.get_parameter(0).to_string())
        } else {
            None
        };

        let rows = Self::load_rows(path.as_deref());
        Ok(PlansBindData {
            rows: Mutex::new(rows),
        })
    }

    fn init(_: &InitInfo) -> Result<Self::InitData, Box<dyn std::error::Error>> {
        Ok(PlansInitData {
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

            let vec0 = output.flat_vector(0);
            vec0.insert(i, CString::new(row.plan_name.as_str()).unwrap_or_default());

            let vec1 = output.flat_vector(1);
            vec1.insert(i, CString::new(row.file_path.as_str()).unwrap_or_default());

            let vec2 = output.flat_vector(2);
            vec2.insert(i, CString::new(row.content.as_str()).unwrap_or_default());

            let mut vec3 = output.flat_vector(3);
            vec3.as_mut_slice::<i64>()[i] = row.file_size;
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
