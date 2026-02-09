#include "duckdb_extension.h"
#include "file_utils.h"
#include "third_party/cJSON.h"
#include <string.h>

DUCKDB_EXTENSION_EXTERN

typedef struct {
    char *base_path;
} StatsBindData;

typedef struct {
    cJSON *json;
    cJSON *daily_activity;
    int current_idx;
    int done;
} StatsInitData;

static void destroy_stats_bind(void *data) {
    StatsBindData *bind = (StatsBindData *)data;
    if (bind) {
        free(bind->base_path);
        free(bind);
    }
}

static void destroy_stats_init(void *data) {
    StatsInitData *init = (StatsInitData *)data;
    if (init) {
        if (init->json) cJSON_Delete(init->json);
        free(init);
    }
}

static void stats_bind(duckdb_bind_info info) {
    duckdb_value path_val = duckdb_bind_get_parameter(info, 0);
    char *path = duckdb_get_varchar(path_val);
    
    StatsBindData *bind_data = malloc(sizeof(StatsBindData));
    bind_data->base_path = strdup(path);
    duckdb_bind_set_bind_data(info, bind_data, destroy_stats_bind);
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_logical_type bigint_type = duckdb_create_logical_type(DUCKDB_TYPE_BIGINT);
    
    duckdb_bind_add_result_column(info, "date", varchar_type);
    duckdb_bind_add_result_column(info, "message_count", bigint_type);
    duckdb_bind_add_result_column(info, "session_count", bigint_type);
    duckdb_bind_add_result_column(info, "tool_call_count", bigint_type);
    
    duckdb_destroy_logical_type(&varchar_type);
    duckdb_destroy_logical_type(&bigint_type);
    duckdb_destroy_value(&path_val);
    duckdb_free(path);
}

static void stats_init(duckdb_init_info info) {
    StatsBindData *bind = (StatsBindData *)duckdb_init_get_bind_data(info);
    
    char *stats_path = path_join(bind->base_path, "stats-cache.json");
    char *content = read_file_content(stats_path);
    free(stats_path);
    
    StatsInitData *init = malloc(sizeof(StatsInitData));
    init->json = NULL;
    init->daily_activity = NULL;
    init->current_idx = 0;
    init->done = 1;
    
    if (content) {
        init->json = cJSON_Parse(content);
        free(content);
        
        if (init->json) {
            init->daily_activity = cJSON_GetObjectItem(init->json, "dailyActivity");
            if (cJSON_IsArray(init->daily_activity)) {
                init->done = 0;
            }
        }
    }
    
    duckdb_init_set_init_data(info, init, destroy_stats_init);
}

static void stats_function(duckdb_function_info info, duckdb_data_chunk output) {
    StatsInitData *init = (StatsInitData *)duckdb_function_get_init_data(info);
    
    if (init->done) {
        duckdb_data_chunk_set_size(output, 0);
        return;
    }
    
    duckdb_vector vec_date = duckdb_data_chunk_get_vector(output, 0);
    duckdb_vector vec_msg = duckdb_data_chunk_get_vector(output, 1);
    duckdb_vector vec_session = duckdb_data_chunk_get_vector(output, 2);
    duckdb_vector vec_tool = duckdb_data_chunk_get_vector(output, 3);
    
    int64_t *msg_data = (int64_t *)duckdb_vector_get_data(vec_msg);
    int64_t *session_data = (int64_t *)duckdb_vector_get_data(vec_session);
    int64_t *tool_data = (int64_t *)duckdb_vector_get_data(vec_tool);
    
    idx_t row = 0;
    idx_t max_rows = 2048;
    int array_size = cJSON_GetArraySize(init->daily_activity);
    
    while (row < max_rows && init->current_idx < array_size) {
        cJSON *item = cJSON_GetArrayItem(init->daily_activity, init->current_idx);
        
        cJSON *date_obj = cJSON_GetObjectItem(item, "date");
        cJSON *msg_obj = cJSON_GetObjectItem(item, "messageCount");
        cJSON *session_obj = cJSON_GetObjectItem(item, "sessionCount");
        cJSON *tool_obj = cJSON_GetObjectItem(item, "toolCallCount");
        
        const char *date = cJSON_IsString(date_obj) ? date_obj->valuestring : "unknown";
        int64_t msg_count = cJSON_IsNumber(msg_obj) ? (int64_t)msg_obj->valuedouble : 0;
        int64_t session_count = cJSON_IsNumber(session_obj) ? (int64_t)session_obj->valuedouble : 0;
        int64_t tool_count = cJSON_IsNumber(tool_obj) ? (int64_t)tool_obj->valuedouble : 0;
        
        duckdb_vector_assign_string_element(vec_date, row, date);
        msg_data[row] = msg_count;
        session_data[row] = session_count;
        tool_data[row] = tool_count;
        
        init->current_idx++;
        row++;
    }
    
    if (init->current_idx >= array_size) {
        init->done = 1;
    }
    
    duckdb_data_chunk_set_size(output, row);
}

void RegisterReadClaudeStats(duckdb_connection connection) {
    duckdb_table_function function = duckdb_create_table_function();
    duckdb_table_function_set_name(function, "read_claude_stats");
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_table_function_add_parameter(function, varchar_type);
    duckdb_destroy_logical_type(&varchar_type);
    
    duckdb_table_function_set_bind(function, stats_bind);
    duckdb_table_function_set_init(function, stats_init);
    duckdb_table_function_set_function(function, stats_function);
    
    duckdb_register_table_function(connection, function);
    duckdb_destroy_table_function(&function);
}
