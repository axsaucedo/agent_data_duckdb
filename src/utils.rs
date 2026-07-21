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
/// Minimal, dependency-free. Used by Cursor (`createdAt`) and Grok (`updates.jsonl`
/// timestamps, which are unix seconds — call `epoch_secs_to_iso`).
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

/// Unix seconds → ISO-8601 UTC (Grok `updates.jsonl` top-level `timestamp`).
pub fn epoch_secs_to_iso(secs: i64) -> String {
    epoch_ms_to_iso(secs.saturating_mul(1000))
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

// ─── Grok Discovery Functions ───

/// Discover Grok chat_history.jsonl files.
/// Layout: <base>/sessions/<url-encoded-cwd>/<session-uuid>/chat_history.jsonl
/// Returns (session_uuid, decoded_cwd, encoded_cwd, file_path) tuples, sorted.
/// Nested `subagents/` directories are not sessions themselves (the child has
/// its own top-level session dir under the same encoded cwd).
pub fn discover_grok_session_files(base_path: &Path) -> Vec<(String, String, String, PathBuf)> {
    let sessions_dir = base_path.join("sessions");
    let mut results = Vec::new();
    if !sessions_dir.is_dir() {
        return results;
    }

    let mut cwd_dirs: Vec<_> = std::fs::read_dir(&sessions_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .collect();
    cwd_dirs.sort_by_key(|e| e.file_name());

    for cwd_entry in cwd_dirs {
        let encoded_cwd = cwd_entry.file_name().to_string_lossy().to_string();
        let decoded_cwd = url_decode(&encoded_cwd);

        let mut session_dirs: Vec<_> = std::fs::read_dir(cwd_entry.path())
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().is_dir())
            .filter(|e| e.file_name() != "subagents")
            .collect();
        session_dirs.sort_by_key(|e| e.file_name());

        for session_entry in session_dirs {
            let chat = session_entry.path().join("chat_history.jsonl");
            if chat.is_file() {
                let session_uuid = session_entry.file_name().to_string_lossy().to_string();
                results.push((session_uuid, decoded_cwd.clone(), encoded_cwd.clone(), chat));
            }
        }
    }
    results
}

/// Map child_session_id → parent_session_id from
/// `sessions/<cwd>/<parent>/subagents/<child>/meta.json`.
/// Used to set `is_agent` (and optional session-level `parent_uuid`) on child rows.
pub fn discover_grok_subagent_parents(
    base_path: &Path,
) -> std::collections::HashMap<String, String> {
    use crate::types::grok::GrokSubagentMeta;

    let sessions_dir = base_path.join("sessions");
    let mut map = std::collections::HashMap::new();
    if !sessions_dir.is_dir() {
        return map;
    }

    let cwd_dirs = std::fs::read_dir(&sessions_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir());

    for cwd_entry in cwd_dirs {
        let parent_dirs = std::fs::read_dir(cwd_entry.path())
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().is_dir());

        for parent_entry in parent_dirs {
            let subagents = parent_entry.path().join("subagents");
            if !subagents.is_dir() {
                continue;
            }
            let child_dirs = std::fs::read_dir(&subagents)
                .into_iter()
                .flatten()
                .filter_map(|e| e.ok())
                .filter(|e| e.path().is_dir());

            for child_entry in child_dirs {
                let meta_path = child_entry.path().join("meta.json");
                let content = match std::fs::read_to_string(&meta_path) {
                    Ok(c) => c,
                    Err(_) => continue,
                };
                let meta: GrokSubagentMeta = match serde_json::from_str(&content) {
                    Ok(m) => m,
                    Err(_) => continue,
                };
                let parent = meta
                    .parent_session_id
                    .or_else(|| {
                        Some(parent_entry.file_name().to_string_lossy().to_string())
                    });
                let child = meta.child_session_id.or_else(|| {
                    Some(child_entry.file_name().to_string_lossy().to_string())
                });
                if let (Some(p), Some(c)) = (parent, child) {
                    map.insert(c, p);
                }
            }
        }
    }
    map
}

/// Read a Grok session's summary.json (sibling of chat_history.jsonl).
pub fn read_grok_summary(session_dir: &Path) -> Option<crate::types::grok::GrokSummary> {
    let content = std::fs::read_to_string(session_dir.join("summary.json")).ok()?;
    serde_json::from_str(&content).ok()
}

/// Last `turn_completed` usage snapshot from `updates.jsonl` (sibling of chat_history).
///
/// Returns `None` if the file is missing, unreadable, or has no usable usage block.
/// Callers stamp this onto conversation rows as a session/prompt aggregate (not
/// per-message); see README Grok field map.
pub fn read_grok_last_turn_usage(
    session_dir: &Path,
) -> Option<crate::types::grok::GrokUsage> {
    use crate::types::grok::{GrokUpdatesLine, GrokUsage};
    use std::io::{BufRead, BufReader};

    let file = std::fs::File::open(session_dir.join("updates.jsonl")).ok()?;
    let mut last: Option<GrokUsage> = None;
    for line_result in BufReader::new(file).lines() {
        let line = match line_result {
            Ok(l) if !l.trim().is_empty() => l,
            _ => continue,
        };
        let env: GrokUpdatesLine = match serde_json::from_str(&line) {
            Ok(e) => e,
            Err(_) => continue,
        };
        let update = match env.params.and_then(|p| p.update) {
            Some(u) => u,
            None => continue,
        };
        if update.session_update.as_deref() != Some("turn_completed") {
            continue;
        }
        if let Some(usage) = update.usage {
            if usage.has_any_tokens() {
                last = Some(usage);
            }
        }
    }
    last
}

/// Ordered timeline of semantic updates.jsonl events (with ISO timestamps).
///
/// Skips noise (hooks, memory flushes). Used to fill `ConversationRow.timestamp`
/// so Grok rows look like Claude (ISO string per message) even though
/// chat_history.jsonl has no time fields.
pub fn read_grok_update_timeline(
    session_dir: &Path,
) -> Vec<crate::types::grok::GrokTimedEvent> {
    use crate::types::grok::{GrokTimedEvent, GrokUpdatesLine};
    use std::io::{BufRead, BufReader};

    let file = match std::fs::File::open(session_dir.join("updates.jsonl")) {
        Ok(f) => f,
        Err(_) => return Vec::new(),
    };
    let mut out = Vec::new();
    for line_result in BufReader::new(file).lines() {
        let line = match line_result {
            Ok(l) if !l.trim().is_empty() => l,
            _ => continue,
        };
        let env: GrokUpdatesLine = match serde_json::from_str(&line) {
            Ok(e) => e,
            Err(_) => continue,
        };
        let secs = match env.timestamp {
            Some(t) => t,
            None => continue,
        };
        let kind = env
            .params
            .and_then(|p| p.update)
            .and_then(|u| u.session_update)
            .unwrap_or_default();
        // Keep events that map onto transcript rows.
        match kind.as_str() {
            "user_message_chunk"
            | "agent_thought_chunk"
            | "agent_message_chunk"
            | "tool_call"
            | "tool_call_update"
            | "turn_completed" => {
                out.push(GrokTimedEvent {
                    kind,
                    timestamp_iso: epoch_secs_to_iso(secs),
                });
            }
            _ => {}
        }
    }
    out
}

/// Cursor over [`read_grok_update_timeline`] — next matching event, else fallback.
pub struct GrokTimeCursor {
    events: Vec<crate::types::grok::GrokTimedEvent>,
    idx: usize,
}

impl GrokTimeCursor {
    pub fn new(events: Vec<crate::types::grok::GrokTimedEvent>) -> Self {
        Self { events, idx: 0 }
    }

    /// Advance to the next event whose kind is in `candidates` (skipping others).
    pub fn next_for(&mut self, candidates: &[&str]) -> Option<String> {
        while self.idx < self.events.len() {
            let ev = &self.events[self.idx];
            if candidates.iter().any(|c| *c == ev.kind) {
                let iso = ev.timestamp_iso.clone();
                self.idx += 1;
                return Some(iso);
            }
            self.idx += 1;
        }
        None
    }

    /// Like `next_for`, but fall back when the stream is exhausted / missing.
    pub fn next_or(&mut self, candidates: &[&str], fallback: &Option<String>) -> Option<String> {
        self.next_for(candidates).or_else(|| fallback.clone())
    }
}

/// Read a Grok session's signals.json (optional sibling of chat_history.jsonl).
pub fn read_grok_signals(session_dir: &Path) -> Option<crate::types::grok::GrokSignals> {
    let content = std::fs::read_to_string(session_dir.join("signals.json")).ok()?;
    serde_json::from_str(&content).ok()
}

/// Session-level timestamp for Grok rows: prefer last activity, then update,
/// then created (floor). chat_history has no per-message timestamps; updates.jsonl
/// timestamps do not 1:1-align with transcript lines.
pub fn grok_session_timestamp(summary: &crate::types::grok::GrokSummary) -> Option<String> {
    summary
        .last_active_at
        .clone()
        .or_else(|| summary.updated_at.clone())
        .or_else(|| summary.created_at.clone())
}

/// YYYY-MM-DD from an ISO-ish summary timestamp (first 10 chars when well-formed).
pub fn grok_date_from_timestamp(ts: &str) -> Option<String> {
    if ts.len() >= 10 {
        let date = &ts[..10];
        if date.as_bytes()[4] == b'-' && date.as_bytes()[7] == b'-' {
            return Some(date.to_string());
        }
    }
    None
}

/// Minimal percent-decoding for Grok's url-encoded cwd directory names
/// (`%2FUsers%2F...` → `/Users/...`). Handles the `%2F` case Grok actually emits.
pub fn url_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hex = std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or("");
            if let Ok(b) = u8::from_str_radix(hex, 16) {
                out.push(b);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).to_string()
}
