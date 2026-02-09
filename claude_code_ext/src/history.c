#include "duckdb_extension.h"
#include "file_utils.h"
#include "third_party/cJSON.h"
#include <string.h>

DUCKDB_EXTENSION_EXTERN

typedef struct {
    char *base_path;
} HistoryBindData;

typedef struct {
    FILE *fp;
    int done;
} HistoryInitData;

static void destroy_history_bind(void *data) {
    HistoryBindData *bind = (HistoryBindData *)data;
    if (bind) {
        free(bind->base_path);
        free(bind);
    }
}

static void destroy_history_init(void *data) {
    HistoryInitData *init = (HistoryInitData *)data;
    if (init) {
        if (init->fp) fclose(init->fp);
        free(init);
    }
}

static void history_bind(duckdb_bind_info info) {
    duckdb_value path_val = duckdb_bind_get_parameter(info, 0);
    char *path = duckdb_get_varchar(path_val);
    
    HistoryBindData *bind_data = malloc(sizeof(HistoryBindData));
    bind_data->base_path = strdup(path);
    duckdb_bind_set_bind_data(info, bind_data, destroy_history_bind);
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_logical_type bigint_type = duckdb_create_logical_type(DUCKDB_TYPE_BIGINT);
    
    duckdb_bind_add_result_column(info, "display", varchar_type);
    duckdb_bind_add_result_column(info, "timestamp_ms", bigint_type);
    duckdb_bind_add_result_column(info, "project", varchar_type);
    duckdb_bind_add_result_column(info, "session_id", varchar_type);
    
    duckdb_destroy_logical_type(&varchar_type);
    duckdb_destroy_logical_type(&bigint_type);
    duckdb_destroy_value(&path_val);
    duckdb_free(path);
}

static void history_init(duckdb_init_info info) {
    HistoryBindData *bind = (HistoryBindData *)duckdb_init_get_bind_data(info);
    
    char *history_path = path_join(bind->base_path, "history.jsonl");
    
    HistoryInitData *init = malloc(sizeof(HistoryInitData));
    init->fp = fopen(history_path, "r");
    init->done = init->fp == NULL ? 1 : 0;
    
    free(history_path);
    duckdb_init_set_init_data(info, init, destroy_history_init);
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

static void history_function(duckdb_function_info info, duckdb_data_chunk output) {
    HistoryInitData *init = (HistoryInitData *)duckdb_function_get_init_data(info);
    
    if (init->done) {
        duckdb_data_chunk_set_size(output, 0);
        return;
    }
    
    duckdb_vector vec_display = duckdb_data_chunk_get_vector(output, 0);
    duckdb_vector vec_timestamp = duckdb_data_chunk_get_vector(output, 1);
    duckdb_vector vec_project = duckdb_data_chunk_get_vector(output, 2);
    duckdb_vector vec_session = duckdb_data_chunk_get_vector(output, 3);
    
    int64_t *timestamp_data = (int64_t *)duckdb_vector_get_data(vec_timestamp);
    
    idx_t row = 0;
    idx_t max_rows = 2048;
    
    while (row < max_rows) {
        char *line = read_line(init->fp);
        if (!line) {
            init->done = 1;
            break;
        }
        
        cJSON *json = cJSON_Parse(line);
        if (!json) {
            free(line);
            continue;
        }
        
        cJSON *display_obj = cJSON_GetObjectItem(json, "display");
        cJSON *timestamp_obj = cJSON_GetObjectItem(json, "timestamp");
        cJSON *project_obj = cJSON_GetObjectItem(json, "project");
        cJSON *session_obj = cJSON_GetObjectItem(json, "sessionId");
        
        const char *display = cJSON_IsString(display_obj) ? display_obj->valuestring : NULL;
        int64_t timestamp = cJSON_IsNumber(timestamp_obj) ? (int64_t)timestamp_obj->valuedouble : 0;
        const char *project = cJSON_IsString(project_obj) ? project_obj->valuestring : NULL;
        const char *session = cJSON_IsString(session_obj) ? session_obj->valuestring : NULL;
        
        set_string_or_null(vec_display, row, display);
        timestamp_data[row] = timestamp;
        set_string_or_null(vec_project, row, project);
        set_string_or_null(vec_session, row, session);
        
        row++;
        cJSON_Delete(json);
        free(line);
    }
    
    duckdb_data_chunk_set_size(output, row);
}

void RegisterReadClaudeHistory(duckdb_connection connection) {
    duckdb_table_function function = duckdb_create_table_function();
    duckdb_table_function_set_name(function, "read_claude_history");
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_table_function_add_parameter(function, varchar_type);
    duckdb_destroy_logical_type(&varchar_type);
    
    duckdb_table_function_set_bind(function, history_bind);
    duckdb_table_function_set_init(function, history_init);
    duckdb_table_function_set_function(function, history_function);
    
    duckdb_register_table_function(connection, function);
    duckdb_destroy_table_function(&function);
}
