#include "file_utils.h"

FileList *file_list_create(void) {
    FileList *list = malloc(sizeof(FileList));
    if (!list) return NULL;
    list->paths = NULL;
    list->count = 0;
    list->capacity = 0;
    return list;
}

void file_list_free(FileList *list) {
    if (!list) return;
    for (size_t i = 0; i < list->count; i++) {
        free(list->paths[i]);
    }
    free(list->paths);
    free(list);
}

void file_list_add(FileList *list, const char *path) {
    if (!list || !path) return;
    
    if (list->count >= list->capacity) {
        size_t new_cap = list->capacity == 0 ? 16 : list->capacity * 2;
        char **new_paths = realloc(list->paths, new_cap * sizeof(char *));
        if (!new_paths) return;
        list->paths = new_paths;
        list->capacity = new_cap;
    }
    
    list->paths[list->count] = strdup(path);
    if (list->paths[list->count]) {
        list->count++;
    }
}

char *path_join(const char *base, const char *sub) {
    if (!base || !sub) return NULL;
    
    size_t base_len = strlen(base);
    size_t sub_len = strlen(sub);
    size_t total = base_len + sub_len + 2;
    
    char *result = malloc(total);
    if (!result) return NULL;
    
    if (base_len > 0 && base[base_len - 1] == '/') {
        snprintf(result, total, "%s%s", base, sub);
    } else {
        snprintf(result, total, "%s/%s", base, sub);
    }
    return result;
}

FileList *find_files(const char *base_dir, const char *subdir, const char *extension) {
    FileList *list = file_list_create();
    if (!list) return NULL;
    
    char *dir_path;
    if (subdir) {
        dir_path = path_join(base_dir, subdir);
    } else {
        dir_path = strdup(base_dir);
    }
    if (!dir_path) {
        file_list_free(list);
        return NULL;
    }
    
    DIR *dir = opendir(dir_path);
    if (!dir) {
        free(dir_path);
        return list;  // Return empty list, not NULL
    }
    
    size_t ext_len = extension ? strlen(extension) : 0;
    struct dirent *entry;
    
    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_name[0] == '.') continue;  // Skip hidden files
        
        // Check extension if specified
        if (extension) {
            size_t name_len = strlen(entry->d_name);
            if (name_len < ext_len) continue;
            if (strcmp(entry->d_name + name_len - ext_len, extension) != 0) continue;
        }
        
        char *full_path = path_join(dir_path, entry->d_name);
        if (full_path) {
            struct stat st;
            if (stat(full_path, &st) == 0 && S_ISREG(st.st_mode)) {
                file_list_add(list, full_path);
            }
            free(full_path);
        }
    }
    
    closedir(dir);
    free(dir_path);
    return list;
}

// Find files recursively in subdirectories (for projects)
FileList *find_files_recursive(const char *base_dir, const char *subdir, const char *extension) {
    FileList *list = file_list_create();
    if (!list) return NULL;
    
    char *dir_path;
    if (subdir) {
        dir_path = path_join(base_dir, subdir);
    } else {
        dir_path = strdup(base_dir);
    }
    if (!dir_path) {
        file_list_free(list);
        return NULL;
    }
    
    DIR *dir = opendir(dir_path);
    if (!dir) {
        free(dir_path);
        return list;
    }
    
    size_t ext_len = extension ? strlen(extension) : 0;
    struct dirent *entry;
    
    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_name[0] == '.') continue;
        
        char *full_path = path_join(dir_path, entry->d_name);
        if (!full_path) continue;
        
        struct stat st;
        if (stat(full_path, &st) != 0) {
            free(full_path);
            continue;
        }
        
        if (S_ISDIR(st.st_mode)) {
            // Recurse into subdirectory
            DIR *subdir_handle = opendir(full_path);
            if (subdir_handle) {
                struct dirent *subentry;
                while ((subentry = readdir(subdir_handle)) != NULL) {
                    if (subentry->d_name[0] == '.') continue;
                    
                    if (extension) {
                        size_t name_len = strlen(subentry->d_name);
                        if (name_len < ext_len) continue;
                        if (strcmp(subentry->d_name + name_len - ext_len, extension) != 0) continue;
                    }
                    
                    char *sub_full_path = path_join(full_path, subentry->d_name);
                    if (sub_full_path) {
                        struct stat sub_st;
                        if (stat(sub_full_path, &sub_st) == 0 && S_ISREG(sub_st.st_mode)) {
                            file_list_add(list, sub_full_path);
                        }
                        free(sub_full_path);
                    }
                }
                closedir(subdir_handle);
            }
        } else if (S_ISREG(st.st_mode)) {
            if (extension) {
                size_t name_len = strlen(entry->d_name);
                if (name_len >= ext_len && 
                    strcmp(entry->d_name + name_len - ext_len, extension) == 0) {
                    file_list_add(list, full_path);
                }
            } else {
                file_list_add(list, full_path);
            }
        }
        free(full_path);
    }
    
    closedir(dir);
    free(dir_path);
    return list;
}

char *read_line(FILE *fp) {
    if (!fp) return NULL;
    
    size_t capacity = 1024;
    size_t length = 0;
    char *line = malloc(capacity);
    if (!line) return NULL;
    
    int c;
    while ((c = fgetc(fp)) != EOF && c != '\n') {
        if (length + 1 >= capacity) {
            capacity *= 2;
            char *new_line = realloc(line, capacity);
            if (!new_line) {
                free(line);
                return NULL;
            }
            line = new_line;
        }
        line[length++] = (char)c;
    }
    
    if (length == 0 && c == EOF) {
        free(line);
        return NULL;
    }
    
    line[length] = '\0';
    return line;
}

char *read_file_content(const char *path) {
    if (!path) return NULL;
    
    FILE *fp = fopen(path, "r");
    if (!fp) return NULL;
    
    fseek(fp, 0, SEEK_END);
    long size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    if (size < 0 || size > 100 * 1024 * 1024) {  // Max 100MB
        fclose(fp);
        return NULL;
    }
    
    char *content = malloc((size_t)size + 1);
    if (!content) {
        fclose(fp);
        return NULL;
    }
    
    size_t read = fread(content, 1, (size_t)size, fp);
    content[read] = '\0';
    fclose(fp);
    return content;
}

char *decode_project_path(const char *encoded) {
    if (!encoded) return NULL;
    
    size_t len = strlen(encoded);
    char *decoded = malloc(len + 1);
    if (!decoded) return NULL;
    
    // Convert leading '-' and subsequent '-' to '/'
    // e.g., "-Users-foo-bar" -> "/Users/foo/bar"
    for (size_t i = 0; i < len; i++) {
        decoded[i] = (encoded[i] == '-') ? '/' : encoded[i];
    }
    decoded[len] = '\0';
    return decoded;
}
