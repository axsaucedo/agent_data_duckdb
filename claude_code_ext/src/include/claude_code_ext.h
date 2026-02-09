#ifndef CLAUDE_CODE_EXT_H
#define CLAUDE_CODE_EXT_H

#include "duckdb_extension.h"

// Register all Claude Code table functions
void RegisterClaudeCodeFunctions(duckdb_connection connection);

// Individual function registrations
void RegisterReadClaudeConversations(duckdb_connection connection);
void RegisterReadClaudePlans(duckdb_connection connection);
void RegisterReadClaudeTodos(duckdb_connection connection);
void RegisterReadClaudeHistory(duckdb_connection connection);
void RegisterReadClaudeStats(duckdb_connection connection);

#endif // CLAUDE_CODE_EXT_H
