mod conversations;
mod history;
mod plans;
mod stats;
mod todos;
mod types;
mod utils;

use duckdb::{duckdb_entrypoint_c_api, Connection, Result};
use std::error::Error;

const EXTENSION_NAME: &str = "agent_data";

#[duckdb_entrypoint_c_api()]
pub unsafe fn extension_entrypoint(con: Connection) -> Result<(), Box<dyn Error>> {
    con.register_table_function::<conversations::ReadConversationsVTab>("read_conversations")
        .expect("Failed to register read_conversations");
    con.register_table_function::<plans::ReadPlansVTab>("read_plans")
        .expect("Failed to register read_plans");
    con.register_table_function::<todos::ReadTodosVTab>("read_todos")
        .expect("Failed to register read_todos");
    con.register_table_function::<history::ReadHistoryVTab>("read_history")
        .expect("Failed to register read_history");
    con.register_table_function::<stats::ReadStatsVTab>("read_stats")
        .expect("Failed to register read_stats");
    Ok(())
}
