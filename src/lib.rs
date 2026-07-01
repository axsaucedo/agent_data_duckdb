mod conversations;
mod detect;
mod history;
mod plans;
mod stats;
mod todos;
mod types;
mod utils;
#[cfg(feature = "cursor")]
mod vscdb;
mod vtab;

use duckdb::{duckdb_entrypoint_c_api, Connection, Result};
use std::error::Error;
use vtab::GenericVTab;

#[duckdb_entrypoint_c_api()]
pub unsafe fn extension_entrypoint(con: Connection) -> Result<(), Box<dyn Error>> {
    con.register_table_function::<GenericVTab<conversations::Conversations>>("read_conversations")
        .expect("Failed to register read_conversations");
    con.register_table_function::<GenericVTab<plans::Plans>>("read_plans")
        .expect("Failed to register read_plans");
    con.register_table_function::<GenericVTab<todos::Todos>>("read_todos")
        .expect("Failed to register read_todos");
    con.register_table_function::<GenericVTab<history::History>>("read_history")
        .expect("Failed to register read_history");
    con.register_table_function::<GenericVTab<stats::Stats>>("read_stats")
        .expect("Failed to register read_stats");
    Ok(())
}
