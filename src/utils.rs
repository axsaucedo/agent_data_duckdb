use std::path::{Path, PathBuf};

/// Resolve a data directory path.
/// If path is provided, expand ~ and return it.
/// If no path, default to ~/.claude (legacy default).
pub fn resolve_data_path(path: Option<&str>) -> PathBuf {
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
/// Returns (project_dir_encoded, is_agent, file_path) tuples sorted deterministically.
/// project_dir_encoded is the raw folder name (e.g., "-Users-testuser-project-alpha").
pub fn discover_conversation_files(base_path: &Path) -> Vec<(String, bool, PathBuf)> {
    let projects_dir = base_path.join("projects");
    discover_project_jsonl_files(&projects_dir)
}

/// Discover all conversation JSONL files under a `projects/` directory.
/// Walks both the main transcripts directly inside `projects/<enc>/` and the
/// subagent transcripts nested at `projects/<enc>/<session-id>/subagents/agent-*.jsonl`.
/// Returns (project_dir_encoded, is_agent, file_path) tuples sorted deterministically.
fn discover_project_jsonl_files(projects_dir: &Path) -> Vec<(String, bool, PathBuf)> {
    let mut results = Vec::new();

    if !projects_dir.is_dir() {
        return results;
    }

    let mut project_dirs: Vec<_> = std::fs::read_dir(projects_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    project_dirs.sort_by_key(|e| e.file_name());

    for project_entry in project_dirs {
        let project_encoded = project_entry.file_name().to_string_lossy().to_string();

        // Main transcripts directly inside projects/<enc>/. A leading "agent-"
        // filename marks an agent transcript.
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
            results.push((project_encoded.clone(), is_agent, file_entry.path()));
        }

        // Subagent transcripts nested at projects/<enc>/<session-id>/subagents/agent-*.jsonl.
        // These were previously skipped, so is_agent was never set for them.
        for subagent_file in discover_subagent_files(&project_entry.path()) {
            results.push((project_encoded.clone(), true, subagent_file));
        }
    }

    results
}

/// Discover subagent transcripts nested under a project directory.
/// Layout: `<project_dir>/<session-id>/subagents/agent-*.jsonl`.
/// Returns file paths sorted deterministically by session-id then file name.
fn discover_subagent_files(project_dir: &Path) -> Vec<PathBuf> {
    let mut results = Vec::new();

    let mut session_dirs: Vec<_> = std::fs::read_dir(project_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    session_dirs.sort_by_key(|e| e.file_name());

    for session_entry in session_dirs {
        let subagents_dir = session_entry.path().join("subagents");
        if !subagents_dir.is_dir() {
            continue;
        }

        let mut jsonl_files: Vec<_> = std::fs::read_dir(&subagents_dir)
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
            results.push(file_entry.path());
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

/// Derive the fallback session id for a transcript file (used when a JSONL row
/// carries no `sessionId` of its own — summary rows, parse errors, future
/// variants without base fields).
///
/// Main transcripts use the file stem. Nested subagent transcripts live at
/// `projects/<enc>/<parent-session-id>/subagents/agent-*.jsonl`, where the file
/// stem is `agent-*` — NOT a session id — so the parent session directory name
/// is used instead. This keeps `session_id` a valid join key across
/// conversations/history/todos and never invents an `agent-*` session.
pub fn fallback_session_id(file_path: &Path) -> String {
    let file_name = file_path
        .file_name()
        .map(|f| f.to_string_lossy().to_string())
        .unwrap_or_default();

    let in_subagents = file_path
        .parent()
        .and_then(|d| d.file_name())
        .map_or(false, |n| n == "subagents");

    if in_subagents {
        if let Some(parent_session) = file_path
            .parent()
            .and_then(|d| d.parent())
            .and_then(|d| d.file_name())
        {
            return parent_session.to_string_lossy().to_string();
        }
    }

    extract_session_id_from_filename(&file_name)
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

// ─── Copilot Discovery Functions ───

/// Discover all Copilot session event files (events.jsonl) under session-state/.
/// Returns (session_id, file_path) tuples sorted by session_id.
pub fn discover_copilot_event_files(base_path: &Path) -> Vec<(String, PathBuf)> {
    let session_dir = base_path.join("session-state");
    let mut results = Vec::new();

    if !session_dir.is_dir() {
        return results;
    }

    let mut entries: Vec<_> = std::fs::read_dir(&session_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let name = entry.file_name().to_string_lossy().to_string();
        if entry.path().is_dir() {
            let events_path = entry.path().join("events.jsonl");
            if events_path.is_file() {
                results.push((name, events_path));
            }
        } else if name.ends_with(".jsonl") {
            let session_id = name.strip_suffix(".jsonl").unwrap_or(&name).to_string();
            results.push((session_id, entry.path()));
        }
    }
    results
}

/// Discover Copilot plan.md files under session-state/*/.
/// Returns (session_id, file_path) tuples.
pub fn discover_copilot_plan_files(base_path: &Path) -> Vec<(String, PathBuf)> {
    let session_dir = base_path.join("session-state");
    let mut results = Vec::new();

    if !session_dir.is_dir() {
        return results;
    }

    let mut entries: Vec<_> = std::fs::read_dir(&session_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let plan_path = entry.path().join("plan.md");
        if plan_path.is_file() {
            let session_id = entry.file_name().to_string_lossy().to_string();
            results.push((session_id, plan_path));
        }
    }
    results
}

/// Discover Copilot checkpoint files with markdown checklists.
/// Returns (session_id, file_name, file_path) tuples.
pub fn discover_copilot_checkpoint_files(base_path: &Path) -> Vec<(String, String, PathBuf)> {
    let session_dir = base_path.join("session-state");
    let mut results = Vec::new();

    if !session_dir.is_dir() {
        return results;
    }

    let mut entries: Vec<_> = std::fs::read_dir(&session_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let checkpoints_dir = entry.path().join("checkpoints");
        if !checkpoints_dir.is_dir() {
            continue;
        }
        let session_id = entry.file_name().to_string_lossy().to_string();
        let mut md_files: Vec<_> = std::fs::read_dir(&checkpoints_dir)
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .filter(|e| {
                let name = e.file_name().to_string_lossy().to_string();
                name.ends_with(".md") && name != "index.md"
            })
            .collect();
        md_files.sort_by_key(|e| e.file_name());

        for f in md_files {
            let fname = f.file_name().to_string_lossy().to_string();
            results.push((session_id.clone(), fname, f.path()));
        }
    }
    results
}

/// Get the Copilot command-history-state.json path.
pub fn copilot_history_file_path(base_path: &Path) -> PathBuf {
    base_path.join("command-history-state.json")
}

/// Read workspace.yaml for a session directory to get metadata.
pub fn read_workspace_yaml(session_dir: &Path) -> Option<crate::types::copilot::WorkspaceYaml> {
    let yaml_path = session_dir.join("workspace.yaml");
    let content = std::fs::read_to_string(&yaml_path).ok()?;
    serde_yaml::from_str(&content).ok()
}
