#include "duckdb_extension.h"
#include "file_utils.h"
#include "third_party/cJSON.h"
#include <string.h>

DUCKDB_EXTENSION_EXTERN

// Bind data - stores the path parameter
typedef struct {
    char *base_path;
} ConversationsBindData;

// Init data - stores iteration state
typedef struct {
    FileList *files;
    size_t current_file_idx;
    FILE *current_file;
    char *current_project;
    int done;
} ConversationsInitData;

static void destroy_bind_data(void *data) {
    ConversationsBindData *bind = (ConversationsBindData *)data;
    if (bind) {
        free(bind->base_path);
        free(bind);
    }
}

static void destroy_init_data(void *data) {
    ConversationsInitData *init = (ConversationsInitData *)data;
    if (init) {
        if (init->current_file) fclose(init->current_file);
        file_list_free(init->files);
        free(init->current_project);
        free(init);
    }
}

// Extract project path from file path
static char *extract_project_from_path(const char *file_path) {
    // Path format: .../projects/<encoded-project>/<session>.jsonl
    const char *projects = strstr(file_path, "/projects/");
    if (!projects) return strdup("unknown");
    
    const char *start = projects + strlen("/projects/");
    const char *end = strchr(start, '/');
    if (!end) return strdup("unknown");
    
    size_t len = end - start;
    char *encoded = malloc(len + 1);
    if (!encoded) return strdup("unknown");
    
    strncpy(encoded, start, len);
    encoded[len] = '\0';
    
    char *decoded = decode_project_path(encoded);
    free(encoded);
    return decoded ? decoded : strdup("unknown");
}

// Extract session ID from file path
static char *extract_session_id(const char *file_path) {
    const char *last_slash = strrchr(file_path, '/');
    if (!last_slash) return strdup("unknown");
    
    const char *filename = last_slash + 1;
    const char *dot = strrchr(filename, '.');
    if (!dot) return strdup(filename);
    
    size_t len = dot - filename;
    char *session_id = malloc(len + 1);
    if (!session_id) return strdup("unknown");
    
    strncpy(session_id, filename, len);
    session_id[len] = '\0';
    return session_id;
}

// Check if file is an agent file
static int is_agent_file(const char *filename) {
    const char *last_slash = strrchr(filename, '/');
    const char *name = last_slash ? last_slash + 1 : filename;
    return strncmp(name, "agent-", 6) == 0;
}

// Bind function
static void conversations_bind(duckdb_bind_info info) {
    // Get path parameter
    duckdb_value path_val = duckdb_bind_get_parameter(info, 0);
    char *path = duckdb_get_varchar(path_val);
    
    // Store bind data
    ConversationsBindData *bind_data = malloc(sizeof(ConversationsBindData));
    bind_data->base_path = strdup(path);
    duckdb_bind_set_bind_data(info, bind_data, destroy_bind_data);
    
    // Define result columns
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_logical_type bigint_type = duckdb_create_logical_type(DUCKDB_TYPE_BIGINT);
    duckdb_logical_type bool_type = duckdb_create_logical_type(DUCKDB_TYPE_BOOLEAN);
    
    duckdb_bind_add_result_column(info, "project", varchar_type);
    duckdb_bind_add_result_column(info, "session_id", varchar_type);
    duckdb_bind_add_result_column(info, "is_agent", bool_type);
    duckdb_bind_add_result_column(info, "type", varchar_type);
    duckdb_bind_add_result_column(info, "uuid", varchar_type);
    duckdb_bind_add_result_column(info, "parent_uuid", varchar_type);
    duckdb_bind_add_result_column(info, "timestamp", varchar_type);
    duckdb_bind_add_result_column(info, "version", varchar_type);
    duckdb_bind_add_result_column(info, "slug", varchar_type);
    duckdb_bind_add_result_column(info, "git_branch", varchar_type);
    duckdb_bind_add_result_column(info, "user_type", varchar_type);
    duckdb_bind_add_result_column(info, "message_role", varchar_type);
    duckdb_bind_add_result_column(info, "message_content", varchar_type);
    duckdb_bind_add_result_column(info, "tool_use_id", varchar_type);
    duckdb_bind_add_result_column(info, "tool_name", varchar_type);
    duckdb_bind_add_result_column(info, "tool_input", varchar_type);
    duckdb_bind_add_result_column(info, "line_number", bigint_type);
    
    duckdb_destroy_logical_type(&varchar_type);
    duckdb_destroy_logical_type(&bigint_type);
    duckdb_destroy_logical_type(&bool_type);
    
    duckdb_destroy_value(&path_val);
    duckdb_free(path);
}

// Forward declaration
extern FileList *find_files_recursive(const char *base_dir, const char *subdir, const char *extension);

// Init function
static void conversations_init(duckdb_init_info info) {
    ConversationsBindData *bind = (ConversationsBindData *)duckdb_init_get_bind_data(info);
    
    ConversationsInitData *init = malloc(sizeof(ConversationsInitData));
    init->files = find_files_recursive(bind->base_path, "projects", ".jsonl");
    init->current_file_idx = 0;
    init->current_file = NULL;
    init->current_project = NULL;
    init->done = 0;
    
    duckdb_init_set_init_data(info, init, destroy_init_data);
}

// Helper to set string or NULL
static void set_string_or_null(duckdb_vector vec, idx_t row, const char *str) {
    if (str && strlen(str) > 0) {
        duckdb_vector_assign_string_element(vec, row, str);
    } else {
        uint64_t *validity = duckdb_vector_get_validity(vec);
        if (!validity) {
            duckdb_vector_ensure_validity_writable(vec);
            validity = duckdb_vector_get_validity(vec);
        }
        duckdb_validity_set_row_invalid(validity, row);
    }
}

// Main function
static void conversations_function(duckdb_function_info info, duckdb_data_chunk output) {
    ConversationsInitData *init = (ConversationsInitData *)duckdb_function_get_init_data(info);
    
    if (init->done) {
        duckdb_data_chunk_set_size(output, 0);
        return;
    }
    
    // Get output vectors
    duckdb_vector vec_project = duckdb_data_chunk_get_vector(output, 0);
    duckdb_vector vec_session = duckdb_data_chunk_get_vector(output, 1);
    duckdb_vector vec_is_agent = duckdb_data_chunk_get_vector(output, 2);
    duckdb_vector vec_type = duckdb_data_chunk_get_vector(output, 3);
    duckdb_vector vec_uuid = duckdb_data_chunk_get_vector(output, 4);
    duckdb_vector vec_parent_uuid = duckdb_data_chunk_get_vector(output, 5);
    duckdb_vector vec_timestamp = duckdb_data_chunk_get_vector(output, 6);
    duckdb_vector vec_version = duckdb_data_chunk_get_vector(output, 7);
    duckdb_vector vec_slug = duckdb_data_chunk_get_vector(output, 8);
    duckdb_vector vec_git_branch = duckdb_data_chunk_get_vector(output, 9);
    duckdb_vector vec_user_type = duckdb_data_chunk_get_vector(output, 10);
    duckdb_vector vec_message_role = duckdb_data_chunk_get_vector(output, 11);
    duckdb_vector vec_message_content = duckdb_data_chunk_get_vector(output, 12);
    duckdb_vector vec_tool_use_id = duckdb_data_chunk_get_vector(output, 13);
    duckdb_vector vec_tool_name = duckdb_data_chunk_get_vector(output, 14);
    duckdb_vector vec_tool_input = duckdb_data_chunk_get_vector(output, 15);
    duckdb_vector vec_line_number = duckdb_data_chunk_get_vector(output, 16);
    
    bool *is_agent_data = (bool *)duckdb_vector_get_data(vec_is_agent);
    int64_t *line_number_data = (int64_t *)duckdb_vector_get_data(vec_line_number);
    
    idx_t row = 0;
    idx_t max_rows = 2048;  // DuckDB standard vector size
    
    while (row < max_rows) {
        // Open next file if needed
        if (!init->current_file) {
            if (init->current_file_idx >= init->files->count) {
                init->done = 1;
                break;
            }
            
            const char *path = init->files->paths[init->current_file_idx];
            init->current_file = fopen(path, "r");
            if (!init->current_file) {
                init->current_file_idx++;
                continue;
            }
            
            free(init->current_project);
            init->current_project = extract_project_from_path(path);
        }
        
        // Read next line
        char *line = read_line(init->current_file);
        if (!line) {
            fclose(init->current_file);
            init->current_file = NULL;
            init->current_file_idx++;
            continue;
        }
        
        // Parse JSON
        cJSON *json = cJSON_Parse(line);
        if (!json) {
            free(line);
            continue;
        }
        
        // Get current file path for metadata
        const char *current_path = init->files->paths[init->current_file_idx];
        char *session_id = extract_session_id(current_path);
        int file_is_agent = is_agent_file(current_path);
        
        // Extract fields
        cJSON *type_obj = cJSON_GetObjectItem(json, "type");
        cJSON *uuid_obj = cJSON_GetObjectItem(json, "uuid");
        cJSON *parent_uuid_obj = cJSON_GetObjectItem(json, "parentUuid");
        cJSON *timestamp_obj = cJSON_GetObjectItem(json, "timestamp");
        cJSON *version_obj = cJSON_GetObjectItem(json, "version");
        cJSON *slug_obj = cJSON_GetObjectItem(json, "slug");
        cJSON *git_branch_obj = cJSON_GetObjectItem(json, "gitBranch");
        cJSON *user_type_obj = cJSON_GetObjectItem(json, "userType");
        cJSON *message_obj = cJSON_GetObjectItem(json, "message");
        
        const char *type_str = cJSON_IsString(type_obj) ? type_obj->valuestring : NULL;
        const char *uuid_str = cJSON_IsString(uuid_obj) ? uuid_obj->valuestring : NULL;
        const char *parent_uuid_str = cJSON_IsString(parent_uuid_obj) ? parent_uuid_obj->valuestring : NULL;
        const char *timestamp_str = cJSON_IsString(timestamp_obj) ? timestamp_obj->valuestring : NULL;
        const char *version_str = cJSON_IsString(version_obj) ? version_obj->valuestring : NULL;
        const char *slug_str = cJSON_IsString(slug_obj) ? slug_obj->valuestring : NULL;
        const char *git_branch_str = cJSON_IsString(git_branch_obj) ? git_branch_obj->valuestring : NULL;
        const char *user_type_str = cJSON_IsString(user_type_obj) ? user_type_obj->valuestring : NULL;
        
        // Extract message content
        const char *message_role = NULL;
        char *message_content = NULL;
        const char *tool_use_id = NULL;
        const char *tool_name = NULL;
        char *tool_input = NULL;
        
        if (cJSON_IsObject(message_obj)) {
            cJSON *role_obj = cJSON_GetObjectItem(message_obj, "role");
            message_role = cJSON_IsString(role_obj) ? role_obj->valuestring : NULL;
            
            cJSON *content_obj = cJSON_GetObjectItem(message_obj, "content");
            if (cJSON_IsString(content_obj)) {
                message_content = strdup(content_obj->valuestring);
            } else if (cJSON_IsArray(content_obj)) {
                // Extract text and tool_use from content blocks
                cJSON *block;
                cJSON_ArrayForEach(block, content_obj) {
                    cJSON *block_type = cJSON_GetObjectItem(block, "type");
                    if (cJSON_IsString(block_type)) {
                        if (strcmp(block_type->valuestring, "text") == 0) {
                            cJSON *text_obj = cJSON_GetObjectItem(block, "text");
                            if (cJSON_IsString(text_obj)) {
                                if (message_content) {
                                    size_t new_len = strlen(message_content) + strlen(text_obj->valuestring) + 2;
                                    char *new_content = malloc(new_len);
                                    snprintf(new_content, new_len, "%s\n%s", message_content, text_obj->valuestring);
                                    free(message_content);
                                    message_content = new_content;
                                } else {
                                    message_content = strdup(text_obj->valuestring);
                                }
                            }
                        } else if (strcmp(block_type->valuestring, "tool_use") == 0) {
                            cJSON *id_obj = cJSON_GetObjectItem(block, "id");
                            cJSON *name_obj = cJSON_GetObjectItem(block, "name");
                            cJSON *input_obj = cJSON_GetObjectItem(block, "input");
                            
                            tool_use_id = cJSON_IsString(id_obj) ? id_obj->valuestring : NULL;
                            tool_name = cJSON_IsString(name_obj) ? name_obj->valuestring : NULL;
                            if (input_obj) {
                                tool_input = cJSON_PrintUnformatted(input_obj);
                            }
                        }
                    }
                }
            }
        }
        
        // Set output values
        set_string_or_null(vec_project, row, init->current_project);
        set_string_or_null(vec_session, row, session_id);
        is_agent_data[row] = file_is_agent ? true : false;
        set_string_or_null(vec_type, row, type_str);
        set_string_or_null(vec_uuid, row, uuid_str);
        set_string_or_null(vec_parent_uuid, row, parent_uuid_str);
        set_string_or_null(vec_timestamp, row, timestamp_str);
        set_string_or_null(vec_version, row, version_str);
        set_string_or_null(vec_slug, row, slug_str);
        set_string_or_null(vec_git_branch, row, git_branch_str);
        set_string_or_null(vec_user_type, row, user_type_str);
        set_string_or_null(vec_message_role, row, message_role);
        set_string_or_null(vec_message_content, row, message_content);
        set_string_or_null(vec_tool_use_id, row, tool_use_id);
        set_string_or_null(vec_tool_name, row, tool_name);
        set_string_or_null(vec_tool_input, row, tool_input);
        line_number_data[row] = (int64_t)(row + 1);
        
        row++;
        
        // Cleanup
        free(session_id);
        free(message_content);
        free(tool_input);
        cJSON_Delete(json);
        free(line);
    }
    
    duckdb_data_chunk_set_size(output, row);
}

void RegisterReadClaudeConversations(duckdb_connection connection) {
    duckdb_table_function function = duckdb_create_table_function();
    duckdb_table_function_set_name(function, "read_claude_conversations");
    
    // Add path parameter
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_table_function_add_parameter(function, varchar_type);
    duckdb_destroy_logical_type(&varchar_type);
    
    // Set callbacks
    duckdb_table_function_set_bind(function, conversations_bind);
    duckdb_table_function_set_init(function, conversations_init);
    duckdb_table_function_set_function(function, conversations_function);
    
    // Register
    duckdb_register_table_function(connection, function);
    duckdb_destroy_table_function(&function);
}
