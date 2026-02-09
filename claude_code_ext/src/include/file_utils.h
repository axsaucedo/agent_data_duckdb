#ifndef FILE_UTILS_H
#define FILE_UTILS_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>

// File list structure for iterating files
typedef struct {
    char **paths;
    size_t count;
    size_t capacity;
} FileList;

// Initialize a file list
FileList *file_list_create(void);

// Free a file list
void file_list_free(FileList *list);

// Add a path to the file list
void file_list_add(FileList *list, const char *path);

// Find all files matching a pattern in a directory
// pattern: glob pattern like "*.jsonl" or "*.md"
FileList *find_files(const char *base_dir, const char *subdir, const char *extension);

// Read a line from file (returns NULL at EOF, caller must free)
char *read_line(FILE *fp);

// Read entire file content (caller must free)
char *read_file_content(const char *path);

// Join paths safely
char *path_join(const char *base, const char *sub);

// Decode Claude project path (replace leading - and internal - with /)
char *decode_project_path(const char *encoded);

#endif // FILE_UTILS_H
