use duckdb::{
    core::{DataChunkHandle, Inserter, LogicalTypeHandle, LogicalTypeId},
    vtab::{BindInfo, InitInfo, TableFunctionInfo, VTab},
    Result,
};
use std::ffi::CString;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

// ─── Column definition helpers ───

pub enum ColType {
    Varchar,
    Bigint,
    Boolean,
}

pub struct ColDef {
    pub name: &'static str,
    pub typ: ColType,
}

pub fn varchar(name: &'static str) -> ColDef {
    ColDef { name, typ: ColType::Varchar }
}

pub fn bigint(name: &'static str) -> ColDef {
    ColDef { name, typ: ColType::Bigint }
}

pub fn boolean(name: &'static str) -> ColDef {
    ColDef { name, typ: ColType::Boolean }
}

// ─── Vector output helpers ───

pub fn set_varchar(output: &mut DataChunkHandle, col: usize, row: usize, val: &str) {
    let vec = output.flat_vector(col);
    vec.insert(row, CString::new(val).unwrap_or_default());
}

pub fn set_varchar_opt(output: &mut DataChunkHandle, col: usize, row: usize, val: Option<&str>) {
    let mut vec = output.flat_vector(col);
    match val {
        Some(v) => vec.insert(row, CString::new(v).unwrap_or_default()),
        None => vec.set_null(row),
    }
}

pub fn set_bool(output: &mut DataChunkHandle, col: usize, row: usize, val: bool) {
    let mut vec = output.flat_vector(col);
    // SAFETY: DuckDB owns this output vector for the current callback, `row` is
    // within the batch we are writing, and the column is declared as BOOLEAN.
    unsafe { vec.as_mut_slice::<bool>()[row] = val };
}

pub fn set_i64(output: &mut DataChunkHandle, col: usize, row: usize, val: i64) {
    let mut vec = output.flat_vector(col);
    // SAFETY: DuckDB owns this output vector for the current callback, `row` is
    // within the batch we are writing, and the column is declared as BIGINT.
    unsafe { vec.as_mut_slice::<i64>()[row] = val };
}

pub fn set_i64_opt(output: &mut DataChunkHandle, col: usize, row: usize, val: Option<i64>) {
    let mut vec = output.flat_vector(col);
    match val {
        Some(v) => {
            // SAFETY: DuckDB owns this output vector for the current callback,
            // `row` is within the batch we are writing, and the column is BIGINT.
            unsafe { vec.as_mut_slice::<i64>()[row] = v };
        }
        None => vec.set_null(row),
    }
}

// ─── Generic VTab implementation ───

/// Trait that each table function implements to define its schema, loading, and row writing.
pub trait TableFunc: Sized + 'static {
    type Row: Send + 'static;

    fn columns() -> Vec<ColDef>;
    fn load_rows(path: Option<&str>, source: Option<&str>) -> Vec<Self::Row>;
    fn write_row(output: &mut DataChunkHandle, idx: usize, row: &Self::Row);
}

#[repr(C)]
pub struct GenericBindData<R: Send + 'static> {
    path: Option<String>,
    source: Option<String>,
    rows: Mutex<Option<Vec<R>>>,
}

#[repr(C)]
pub struct GenericInitData {
    offset: AtomicUsize,
}

pub struct GenericVTab<T: TableFunc>(std::marker::PhantomData<T>);

/// Resolve the optional `path` named parameter from bind info.
fn resolve_path(bind: &BindInfo) -> Option<String> {
    let named = bind.get_named_parameter("path").map(|v| v.to_string());
    let positional = if bind.get_parameter_count() > 0 {
        let p = bind.get_parameter(0).to_string();
        if p.is_empty() { None } else { Some(p) }
    } else {
        None
    };
    named.or(positional)
}

/// Resolve the optional `source` named parameter from bind info.
pub fn resolve_source(bind: &BindInfo) -> Option<String> {
    bind.get_named_parameter("source").map(|v| v.to_string())
}

impl<T: TableFunc> VTab for GenericVTab<T> {
    type InitData = GenericInitData;
    type BindData = GenericBindData<T::Row>;

    fn bind(bind: &BindInfo) -> Result<Self::BindData, Box<dyn std::error::Error>> {
        for col in T::columns() {
            let logical_type = match col.typ {
                ColType::Varchar => LogicalTypeHandle::from(LogicalTypeId::Varchar),
                ColType::Bigint => LogicalTypeHandle::from(LogicalTypeId::Bigint),
                ColType::Boolean => LogicalTypeHandle::from(LogicalTypeId::Boolean),
            };
            bind.add_result_column(col.name, logical_type);
        }

        let path = resolve_path(bind);
        let source = resolve_source(bind);
        Ok(GenericBindData { path, source, rows: Mutex::new(None) })
    }

    fn init(_: &InitInfo) -> Result<Self::InitData, Box<dyn std::error::Error>> {
        Ok(GenericInitData { offset: AtomicUsize::new(0) })
    }

    fn func(
        func: &TableFunctionInfo<Self>,
        output: &mut DataChunkHandle,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let bind_data = func.get_bind_data();
        let init_data = func.get_init_data();
        let mut guard = bind_data.rows.lock().unwrap();

        // Lazy load: defer I/O from bind (planning) to first func() call (execution)
        if guard.is_none() {
            *guard = Some(T::load_rows(
                bind_data.path.as_deref(),
                bind_data.source.as_deref(),
            ));
        }
        let rows = guard.as_ref().unwrap();

        let offset = init_data.offset.load(Ordering::Relaxed);
        if offset >= rows.len() {
            output.set_len(0);
            return Ok(());
        }

        let batch_size = std::cmp::min(2048, rows.len() - offset);
        for i in 0..batch_size {
            T::write_row(output, i, &rows[offset + i]);
        }

        output.set_len(batch_size);
        init_data.offset.store(offset + batch_size, Ordering::Relaxed);
        Ok(())
    }

    fn named_parameters() -> Option<Vec<(String, LogicalTypeHandle)>> {
        Some(vec![
            ("path".to_string(), LogicalTypeHandle::from(LogicalTypeId::Varchar)),
            ("source".to_string(), LogicalTypeHandle::from(LogicalTypeId::Varchar)),
        ])
    }
}
