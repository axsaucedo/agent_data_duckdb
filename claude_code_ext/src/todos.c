#include "duckdb_extension.h"
#include "file_utils.h"
#include "third_party/cJSON.h"
#include <string.h>

DUCKDB_EXTENSION_EXTERN

typedef struct {
    char *base_path;
} TodosBindData;

typedef struct {
    FileList *files;
    size_t current_file_idx;
    cJSON *current_json;
    int current_item_idx;
    char *current_session;
    char *current_agent;
    int done;
} TodosInitData;

static void destroy_todos_bind(void *data) {
    TodosBindData *bind = (TodosBindData *)data;
    if (bind) {
        free(bind->base_path);
        free(bind);
    }
}

static void destroy_todos_init(void *data) {
    TodosInitData *init = (TodosInitData *)data;
    if (init) {
        file_list_free(init->files);
        if (init->current_json) cJSON_Delete(init->current_json);
        free(init->current_session);
        free(init->current_agent);
        free(init);
    }
}

// Parse todo filename: <session-id>-agent-<agent-id>.json
static void parse_todo_filename(const char *path, char **session, char **agent) {
    const char *last_slash = strrchr(path, '/');
    const char *filename = last_slash ? last_slash + 1 : path;
    
    // Remove .json extension
    char *name = strdup(filename);
    char *dot = strrchr(name, '.');
    if (dot) *dot = '\0';
    
    // Find -agent-
    char *agent_marker = strstr(name, "-agent-");
    if (agent_marker) {
        *agent_marker = '\0';
        *session = strdup(name);
        *agent = strdup(agent_marker + 7);  // Skip "-agent-"
    } else {
        *session = strdup(name);
        *agent = NULL;
    }
    free(name);
}

static void todos_bind(duckdb_bind_info info) {
    duckdb_value path_val = duckdb_bind_get_parameter(info, 0);
    char *path = duckdb_get_varchar(path_val);
    
    TodosBindData *bind_data = malloc(sizeof(TodosBindData));
    bind_data->base_path = strdup(path);
    duckdb_bind_set_bind_data(info, bind_data, destroy_todos_bind);
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_logical_type int_type = duckdb_create_logical_type(DUCKDB_TYPE_INTEGER);
    
    duckdb_bind_add_result_column(info, "session_id", varchar_type);
    duckdb_bind_add_result_column(info, "agent_id", varchar_type);
    duckdb_bind_add_result_column(info, "file_path", varchar_type);
    duckdb_bind_add_result_column(info, "item_index", int_type);
    duckdb_bind_add_result_column(info, "content", varchar_type);
    duckdb_bind_add_result_column(info, "status", varchar_type);
    duckdb_bind_add_result_column(info, "active_form", varchar_type);
    
    duckdb_destroy_logical_type(&varchar_type);
    duckdb_destroy_logical_type(&int_type);
    duckdb_destroy_value(&path_val);
    duckdb_free(path);
}

static void todos_init(duckdb_init_info info) {
    TodosBindData *bind = (TodosBindData *)duckdb_init_get_bind_data(info);
    
    TodosInitData *init = malloc(sizeof(TodosInitData));
    init->files = find_files(bind->base_path, "todos", ".json");
    init->current_file_idx = 0;
    init->current_json = NULL;
    init->current_item_idx = 0;
    init->current_session = NULL;
    init->current_agent = NULL;
    init->done = 0;
    
    duckdb_init_set_init_data(info, init, destroy_todos_init);
}

static void set_string_or_null(duckdb_vector vec, idx_t row, const char *str) {
    if (str && strlen(str) > 0) {
        duckdb_vector_assign_string_element(vec, row, str);
    } else {
        duckdb_vector_ensure_validity_writable(vec);
        uint64_t *validity = duckdb_vector_get_validity(vec);
        duckdb_validity_set_row_invalid(validity, row);
    }
}

static void todos_function(duckdb_function_info info, duckdb_data_chunk output) {
    TodosInitData *init = (TodosInitData *)duckdb_function_get_init_data(info);
    
    if (init->done) {
        duckdb_data_chunk_set_size(output, 0);
        return;
    }
    
    duckdb_vector vec_session = duckdb_data_chunk_get_vector(output, 0);
    duckdb_vector vec_agent = duckdb_data_chunk_get_vector(output, 1);
    duckdb_vector vec_path = duckdb_data_chunk_get_vector(output, 2);
    duckdb_vector vec_idx = duckdb_data_chunk_get_vector(output, 3);
    duckdb_vector vec_content = duckdb_data_chunk_get_vector(output, 4);
    duckdb_vector vec_status = duckdb_data_chunk_get_vector(output, 5);
    duckdb_vector vec_active_form = duckdb_data_chunk_get_vector(output, 6);
    
    int32_t *idx_data = (int32_t *)duckdb_vector_get_data(vec_idx);
    
    idx_t row = 0;
    idx_t max_rows = 2048;
    
    while (row < max_rows) {
        // Load next file if needed
        if (!init->current_json) {
            if (init->current_file_idx >= init->files->count) {
                init->done = 1;
                break;
            }
            
            const char *path = init->files->paths[init->current_file_idx];
            char *content = read_file_content(path);
            if (!content) {
                init->current_file_idx++;
                continue;
            }
            
            init->current_json = cJSON_Parse(content);
            free(content);
            
            if (!init->current_json || !cJSON_IsArray(init->current_json)) {
                if (init->current_json) cJSON_Delete(init->current_json);
                init->current_json = NULL;
                init->current_file_idx++;
                continue;
            }
            
            free(init->current_session);
            free(init->current_agent);
            parse_todo_filename(path, &init->current_session, &init->current_agent);
            init->current_item_idx = 0;
        }
        
        int array_size = cJSON_GetArraySize(init->current_json);
        if (init->current_item_idx >= array_size) {
            cJSON_Delete(init->current_json);
            init->current_json = NULL;
            init->current_file_idx++;
            continue;
        }
        
        cJSON *item = cJSON_GetArrayItem(init->current_json, init->current_item_idx);
        
        cJSON *content_obj = cJSON_GetObjectItem(item, "content");
        cJSON *status_obj = cJSON_GetObjectItem(item, "status");
        cJSON *active_form_obj = cJSON_GetObjectItem(item, "activeForm");
        
        const char *content = cJSON_IsString(content_obj) ? content_obj->valuestring : NULL;
        const char *status = cJSON_IsString(status_obj) ? status_obj->valuestring : NULL;
        const char *active_form = cJSON_IsString(active_form_obj) ? active_form_obj->valuestring : NULL;
        
        set_string_or_null(vec_session, row, init->current_session);
        set_string_or_null(vec_agent, row, init->current_agent);
        duckdb_vector_assign_string_element(vec_path, row, init->files->paths[init->current_file_idx]);
        idx_data[row] = init->current_item_idx;
        set_string_or_null(vec_content, row, content);
        set_string_or_null(vec_status, row, status);
        set_string_or_null(vec_active_form, row, active_form);
        
        init->current_item_idx++;
        row++;
    }
    
    duckdb_data_chunk_set_size(output, row);
}

void RegisterReadClaudeTodos(duckdb_connection connection) {
    duckdb_table_function function = duckdb_create_table_function();
    duckdb_table_function_set_name(function, "read_claude_todos");
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_table_function_add_parameter(function, varchar_type);
    duckdb_destroy_logical_type(&varchar_type);
    
    duckdb_table_function_set_bind(function, todos_bind);
    duckdb_table_function_set_init(function, todos_init);
    duckdb_table_function_set_function(function, todos_function);
    
    duckdb_register_table_function(connection, function);
    duckdb_destroy_table_function(&function);
}
