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

/// Best-effort percent-decode for Grok session cwd folder names (`%2FUsers%2F…`).
pub fn percent_decode_loose(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let h = |c: u8| -> Option<u8> {
                match c {
                    b'0'..=b'9' => Some(c - b'0'),
                    b'a'..=b'f' => Some(c - b'a' + 10),
                    b'A'..=b'F' => Some(c - b'A' + 10),
                    _ => None,
                }
            };
            if let (Some(a), Some(b)) = (h(bytes[i + 1]), h(bytes[i + 2])) {
                out.push((a << 4) | b);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
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

/// Discover all Claude Desktop ("Cowork") conversation JSONL files.
/// Desktop stores each session's transcript using the same camelCase schema as
/// Claude Code, nested under
/// `local-agent-mode-sessions/**/.claude/projects/<enc>/<session-id>.jsonl`
/// (plus subagent transcripts one level deeper). The set of `projects/`
/// directories is discovered by walking the tree, then each is processed by the
/// shared `discover_project_jsonl_files` walk so the subagent fix applies here too.
/// Returns (project_dir_encoded, is_agent, file_path) tuples sorted deterministically.
pub fn discover_claude_desktop_files(base_path: &Path) -> Vec<(String, bool, PathBuf)> {
    let root = base_path.join("local-agent-mode-sessions");
    let mut projects_dirs = Vec::new();
    collect_projects_dirs(&root, &mut projects_dirs);
    projects_dirs.sort();

    let mut results = Vec::new();
    for projects_dir in projects_dirs {
        results.extend(discover_project_jsonl_files(&projects_dir));
    }
    results
}

/// Recursively collect every `.claude/projects` directory beneath `dir`.
fn collect_projects_dirs(dir: &Path, out: &mut Vec<PathBuf>) {
    if !dir.is_dir() {
        return;
    }

    // A `.claude/projects` directory here is a transcript container.
    let candidate = dir.join(".claude").join("projects");
    if candidate.is_dir() {
        out.push(candidate);
    }

    let mut entries: Vec<_> = std::fs::read_dir(dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        // Avoid descending back into the `.claude` dir we already handled above.
        if entry.file_name() == ".claude" {
            continue;
        }
        collect_projects_dirs(&entry.path(), out);
    }
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

/// Convert epoch milliseconds to an ISO-8601 UTC string (e.g. "2026-06-10T12:34:56Z").
/// Minimal, dependency-free; sufficient for Cursor `createdAt` timestamps.
/// Only used by the Cursor parser, so gated to avoid a dead-code warning when the
/// `cursor` feature is disabled.
#[cfg(feature = "cursor")]
pub fn epoch_ms_to_iso(ms: i64) -> String {
    let secs = ms / 1000;
    let days = secs.div_euclid(86_400);
    let rem = secs.rem_euclid(86_400);
    let (hh, mm, ss) = (rem / 3600, (rem % 3600) / 60, rem % 60);

    // Civil-from-days algorithm (Howard Hinnant), epoch 1970-01-01.
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = if m <= 2 { y + 1 } else { y };

    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        year, m, d, hh, mm, ss
    )
}

// ─── Codex Discovery Functions ───

/// Discover Codex rollout-*.jsonl transcripts under sessions/YYYY/MM/DD/.
/// Returns (session_uuid, file_path) tuples sorted by path.
pub fn discover_codex_rollout_files(base_path: &Path) -> Vec<(String, PathBuf)> {
    let sessions_dir = base_path.join("sessions");
    let mut results = Vec::new();
    if !sessions_dir.is_dir() {
        return results;
    }
    walk_codex(&sessions_dir, &mut results);
    results.sort_by(|a, b| a.1.cmp(&b.1));
    results
}

fn walk_codex(dir: &Path, out: &mut Vec<(String, PathBuf)>) {
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            walk_codex(&path, out);
        } else {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.starts_with("rollout-") && name.ends_with(".jsonl") {
                // session uuid is the trailing UUID (5 hyphen-delimited groups)
                // before `.jsonl`.
                let stem = name.strip_suffix(".jsonl").unwrap_or(&name);
                let session_uuid = stem
                    .rsplit('-')
                    .take(5)
                    .collect::<Vec<_>>()
                    .into_iter()
                    .rev()
                    .collect::<Vec<_>>()
                    .join("-");
                out.push((session_uuid, path));
            }
        }
    }
}

// ─── Gemini Discovery Functions ───

/// Discover all Gemini CLI chat session files.
/// Layout: `tmp/<project-hash>/chats/session-<ts>-<id>.json`. The `<project-hash>`
/// folder may be a SHA-256 of the project path or a short human-readable alias
/// (mapped in `projects.json`).
/// Returns (project_hash, file_path) tuples sorted deterministically by
/// project-hash then file name.
pub fn discover_gemini_chat_files(base_path: &Path) -> Vec<(String, PathBuf)> {
    let tmp_dir = base_path.join("tmp");
    let mut results = Vec::new();

    if !tmp_dir.is_dir() {
        return results;
    }

    let mut project_dirs: Vec<_> = std::fs::read_dir(&tmp_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    project_dirs.sort_by_key(|e| e.file_name());

    for project_entry in project_dirs {
        let project_hash = project_entry.file_name().to_string_lossy().to_string();
        let chats_dir = project_entry.path().join("chats");
        if !chats_dir.is_dir() {
            continue;
        }

        let mut json_files: Vec<_> = std::fs::read_dir(&chats_dir)
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .filter(|e| {
                let name = e.file_name().to_string_lossy().to_string();
                name.starts_with("session-") && name.ends_with(".json")
            })
            .collect();
        json_files.sort_by_key(|e| e.file_name());

        for f in json_files {
            results.push((project_hash.clone(), f.path()));
        }
    }
    results
}

/// Resolve a Gemini project hash to its real filesystem path using the
/// `projects.json` alias map (`{ "projects": { "<abs-path>": "<alias>" } }`).
/// Hashes that are SHA-256 of an unknown path (no alias) return `None`.
pub fn read_gemini_project_map(base_path: &Path) -> std::collections::HashMap<String, String> {
    let mut map = std::collections::HashMap::new();
    let path = base_path.join("projects.json");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return map,
    };
    let value: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(_) => return map,
    };
    if let Some(projects) = value.get("projects").and_then(|p| p.as_object()) {
        for (abs_path, alias) in projects {
            if let Some(alias) = alias.as_str() {
                // Map alias → absolute path so a project_hash alias resolves back.
                map.insert(alias.to_string(), abs_path.clone());
            }
        }
    }
    map
}
