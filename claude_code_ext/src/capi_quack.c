#include "duckdb_extension.h"
#include "claude_code_ext.h"

DUCKDB_EXTENSION_ENTRYPOINT(duckdb_connection connection, duckdb_extension_info info, struct duckdb_extension_access *access) {
	// Register all Claude Code functions
	RegisterReadClaudeConversations(connection);
	RegisterReadClaudePlans(connection);
	RegisterReadClaudeTodos(connection);
	RegisterReadClaudeHistory(connection);
	RegisterReadClaudeStats(connection);

	// Return true to indicate successful initialization
	return true;
}
