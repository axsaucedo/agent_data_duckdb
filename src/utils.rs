use std::path::{Path, PathBuf};

/// Resolve the Claude data directory path.
/// If path is provided, expand ~ and return it.
/// If no path, default to ~/.claude.
pub fn resolve_claude_path(path: Option<&str>) -> PathBuf {
    match path {
        Some(p) => expand_tilde(p),
        None => {
            let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
            home.join(".claude")
        }
    }
}

/// Expand ~ at the start of a path to the user's home directory.
fn expand_tilde(path: &str) -> PathBuf {
    if path.starts_with("~/") || path == "~" {
        let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
        if path == "~" {
            home
        } else {
            home.join(&path[2..])
        }
    } else {
        PathBuf::from(path)
    }
}

/// Discover all JSONL conversation files under projects/ directory.
/// Returns (project_path_decoded, is_agent, file_path) tuples sorted deterministically.
pub fn discover_conversation_files(base_path: &Path) -> Vec<(String, bool, PathBuf)> {
    let projects_dir = base_path.join("projects");
    let mut results = Vec::new();

    if !projects_dir.is_dir() {
        return results;
    }

    let mut project_dirs: Vec<_> = std::fs::read_dir(&projects_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    project_dirs.sort_by_key(|e| e.file_name());

    for project_entry in project_dirs {
        let project_encoded = project_entry.file_name().to_string_lossy().to_string();
        let project_decoded = decode_project_path(&project_encoded);

        let mut jsonl_files: Vec<_> = std::fs::read_dir(project_entry.path())
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .filter(|e| {
                e.path()
                    .extension()
                    .map_or(false, |ext| ext == "jsonl")
            })
            .collect();
        jsonl_files.sort_by_key(|e| e.file_name());

        for file_entry in jsonl_files {
            let fname = file_entry.file_name().to_string_lossy().to_string();
            let is_agent = fname.starts_with("agent-");
            results.push((project_decoded.clone(), is_agent, file_entry.path()));
        }
    }

    results
}

/// Decode project path: `-Users-username-project` → `/Users/username/project`
pub fn decode_project_path(encoded: &str) -> String {
    if encoded.starts_with('-') {
        format!("/{}", encoded[1..].replace('-', "/"))
    } else {
        encoded.replace('-', "/")
    }
}

/// Extract session_id from a conversation filename.
/// For main sessions: `<uuid>.jsonl` → the UUID
/// For agents: `agent-<short-id>.jsonl` → the short ID
pub fn extract_session_id_from_filename(filename: &str) -> String {
    let stem = filename.strip_suffix(".jsonl").unwrap_or(filename);
    stem.to_string()
}

/// Discover plan markdown files under plans/ directory.
pub fn discover_plan_files(base_path: &Path) -> Vec<PathBuf> {
    let plans_dir = base_path.join("plans");
    let mut results = Vec::new();

    if !plans_dir.is_dir() {
        return results;
    }

    let mut files: Vec<_> = std::fs::read_dir(&plans_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| {
            e.path()
                .extension()
                .map_or(false, |ext| ext == "md")
        })
        .collect();
    files.sort_by_key(|e| e.file_name());

    for f in files {
        results.push(f.path());
    }
    results
}

/// Discover todo JSON files under todos/ directory.
/// Returns (session_id, agent_id, file_path) tuples.
pub fn discover_todo_files(base_path: &Path) -> Vec<(String, String, PathBuf)> {
    let todos_dir = base_path.join("todos");
    let mut results = Vec::new();

    if !todos_dir.is_dir() {
        return results;
    }

    let mut files: Vec<_> = std::fs::read_dir(&todos_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| {
            e.path()
                .extension()
                .map_or(false, |ext| ext == "json")
        })
        .collect();
    files.sort_by_key(|e| e.file_name());

    for f in files {
        let fname = f.file_name().to_string_lossy().to_string();
        let stem = fname.strip_suffix(".json").unwrap_or(&fname);
        // Pattern: <session-uuid>-agent-<agent-uuid>
        if let Some(idx) = stem.find("-agent-") {
            let session_id = stem[..idx].to_string();
            let agent_id = stem[idx + 7..].to_string();
            results.push((session_id, agent_id, f.path()));
        }
    }
    results
}

/// Get the history.jsonl path.
pub fn history_file_path(base_path: &Path) -> PathBuf {
    base_path.join("history.jsonl")
}

/// Get the stats-cache.json path.
pub fn stats_file_path(base_path: &Path) -> PathBuf {
    base_path.join("stats-cache.json")
}

/// Extract text content from a serde_json::Value that could be a string or array.
pub fn extract_text_content(value: &serde_json::Value) -> String {
    match value {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Array(arr) => {
            let mut parts = Vec::new();
            for item in arr {
                if let Some(text) = item.get("text").and_then(|t| t.as_str()) {
                    parts.push(text.to_string());
                }
            }
            parts.join("\n")
        }
        _ => value.to_string(),
    }
}
