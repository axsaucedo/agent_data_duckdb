#include "duckdb_extension.h"
#include "file_utils.h"
#include <string.h>

DUCKDB_EXTENSION_EXTERN

typedef struct {
    char *base_path;
} PlansBindData;

typedef struct {
    FileList *files;
    size_t current_idx;
    int done;
} PlansInitData;

static void destroy_plans_bind(void *data) {
    PlansBindData *bind = (PlansBindData *)data;
    if (bind) {
        free(bind->base_path);
        free(bind);
    }
}

static void destroy_plans_init(void *data) {
    PlansInitData *init = (PlansInitData *)data;
    if (init) {
        file_list_free(init->files);
        free(init);
    }
}

static char *extract_plan_name(const char *path) {
    const char *last_slash = strrchr(path, '/');
    if (!last_slash) return strdup(path);
    
    const char *filename = last_slash + 1;
    const char *dot = strrchr(filename, '.');
    if (!dot) return strdup(filename);
    
    size_t len = dot - filename;
    char *name = malloc(len + 1);
    if (!name) return strdup(filename);
    
    strncpy(name, filename, len);
    name[len] = '\0';
    return name;
}

static void plans_bind(duckdb_bind_info info) {
    duckdb_value path_val = duckdb_bind_get_parameter(info, 0);
    char *path = duckdb_get_varchar(path_val);
    
    PlansBindData *bind_data = malloc(sizeof(PlansBindData));
    bind_data->base_path = strdup(path);
    duckdb_bind_set_bind_data(info, bind_data, destroy_plans_bind);
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    
    duckdb_bind_add_result_column(info, "plan_name", varchar_type);
    duckdb_bind_add_result_column(info, "file_path", varchar_type);
    duckdb_bind_add_result_column(info, "content", varchar_type);
    
    duckdb_destroy_logical_type(&varchar_type);
    duckdb_destroy_value(&path_val);
    duckdb_free(path);
}

static void plans_init(duckdb_init_info info) {
    PlansBindData *bind = (PlansBindData *)duckdb_init_get_bind_data(info);
    
    PlansInitData *init = malloc(sizeof(PlansInitData));
    init->files = find_files(bind->base_path, "plans", ".md");
    init->current_idx = 0;
    init->done = 0;
    
    duckdb_init_set_init_data(info, init, destroy_plans_init);
}

static void plans_function(duckdb_function_info info, duckdb_data_chunk output) {
    PlansInitData *init = (PlansInitData *)duckdb_function_get_init_data(info);
    
    if (init->done) {
        duckdb_data_chunk_set_size(output, 0);
        return;
    }
    
    duckdb_vector vec_name = duckdb_data_chunk_get_vector(output, 0);
    duckdb_vector vec_path = duckdb_data_chunk_get_vector(output, 1);
    duckdb_vector vec_content = duckdb_data_chunk_get_vector(output, 2);
    
    idx_t row = 0;
    idx_t max_rows = 2048;
    
    while (row < max_rows && init->current_idx < init->files->count) {
        const char *file_path = init->files->paths[init->current_idx];
        char *plan_name = extract_plan_name(file_path);
        char *content = read_file_content(file_path);
        
        duckdb_vector_assign_string_element(vec_name, row, plan_name);
        duckdb_vector_assign_string_element(vec_path, row, file_path);
        
        if (content) {
            duckdb_vector_assign_string_element(vec_content, row, content);
            free(content);
        } else {
            duckdb_vector_ensure_validity_writable(vec_content);
            uint64_t *validity = duckdb_vector_get_validity(vec_content);
            duckdb_validity_set_row_invalid(validity, row);
        }
        
        free(plan_name);
        init->current_idx++;
        row++;
    }
    
    if (init->current_idx >= init->files->count) {
        init->done = 1;
    }
    
    duckdb_data_chunk_set_size(output, row);
}

void RegisterReadClaudePlans(duckdb_connection connection) {
    duckdb_table_function function = duckdb_create_table_function();
    duckdb_table_function_set_name(function, "read_claude_plans");
    
    duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
    duckdb_table_function_add_parameter(function, varchar_type);
    duckdb_destroy_logical_type(&varchar_type);
    
    duckdb_table_function_set_bind(function, plans_bind);
    duckdb_table_function_set_init(function, plans_init);
    duckdb_table_function_set_function(function, plans_function);
    
    duckdb_register_table_function(connection, function);
    duckdb_destroy_table_function(&function);
}
