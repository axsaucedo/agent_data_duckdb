use std::path::Path;

/// Supported data providers.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Provider {
    Claude,
    ClaudeDesktop,
    Copilot,
    Cursor,
    Codex,
    Gemini,
    Grok,
    Unknown,
}

/// Auto-detect provider from directory structure.
/// - `local-agent-mode-sessions/` directory → Claude Desktop
/// - Cursor IDE: `state.vscdb` file (direct or in dir) → Cursor
/// - Cursor CLI: `projects/*/agent-transcripts/` → Cursor (before Claude `projects/`)
/// - Claude Code: `projects/` with session `*.jsonl` at projects/<enc>/*.jsonl → Claude
/// - `session-state/` directory → Copilot
/// - Grok Build: `sessions/<cwd-enc>/<session-id>/summary.json` (or chat_history.jsonl)
/// - Codex: `sessions/YYYY/` date partitions (rollout files)
/// - Gemini CLI: `tmp/` + `installation_id` → Gemini (`~/.gemini`)
pub fn detect_provider(path: &Path) -> Provider {
    if path.join("local-agent-mode-sessions").is_dir() {
        return Provider::ClaudeDesktop;
    }
    // Cursor: the vscdb file may be passed directly, or its parent directory.
    if path.extension().map_or(false, |e| e == "vscdb") || path.join("state.vscdb").is_file() {
        return Provider::Cursor;
    }
    // Cursor agent-transcripts under projects/ — must run BEFORE Claude's projects/ check
    // because ~/.cursor also has a projects/ tree.
    if has_cursor_agent_transcripts(path) {
        return Provider::Cursor;
    }
    if path.join("session-state").is_dir() {
        return Provider::Copilot;
    }
    // Claude Code: projects/<enc>/*.jsonl (not agent-transcripts nested layout)
    if path.join("projects").is_dir() && has_claude_project_jsonl(path) {
        return Provider::Claude;
    }
    // Grok Build before Codex: both use sessions/, different shapes
    if is_grok_home(path) {
        return Provider::Grok;
    }
    // Codex partitions transcripts by date: sessions/YYYY/MM/DD/rollout-*.jsonl.
    let sessions = path.join("sessions");
    if sessions.is_dir() {
        let has_year_dir = std::fs::read_dir(&sessions)
            .into_iter()
            .flatten()
            .flatten()
            .any(|e| {
                e.path().is_dir()
                    && e.file_name()
                        .to_string_lossy()
                        .chars()
                        .all(|c| c.is_ascii_digit())
            });
        if has_year_dir {
            return Provider::Codex;
        }
    }
    // Gemini CLI keeps chats under `tmp/<project-hash>/chats/`.
    if path.join("tmp").is_dir() && path.join("installation_id").is_file() {
        return Provider::Gemini;
    }
    Provider::Unknown
}

/// Cursor CLI / IDE agent transcripts: projects/<name>/agent-transcripts/<id>/<id>.jsonl
fn has_cursor_agent_transcripts(path: &Path) -> bool {
    let projects = path.join("projects");
    if !projects.is_dir() {
        return false;
    }
    std::fs::read_dir(&projects)
        .into_iter()
        .flatten()
        .flatten()
        .any(|e| e.path().join("agent-transcripts").is_dir())
}

/// Claude Code: at least one projects/<enc>/*.jsonl (files directly in project dir).
fn has_claude_project_jsonl(path: &Path) -> bool {
    let projects = path.join("projects");
    if !projects.is_dir() {
        return false;
    }
    for pe in std::fs::read_dir(&projects).into_iter().flatten().flatten() {
        if !pe.path().is_dir() {
            continue;
        }
        let has_jsonl = std::fs::read_dir(pe.path())
            .into_iter()
            .flatten()
            .flatten()
            .any(|f| f.path().extension().map_or(false, |e| e == "jsonl"));
        if has_jsonl {
            return true;
        }
    }
    false
}

/// Grok Build home: sessions/<url-encoded-cwd>/<session-uuid>/summary.json
/// or chat_history.jsonl / updates.jsonl.
fn is_grok_home(path: &Path) -> bool {
    // Direct path to a single session dir
    if path.join("summary.json").is_file() || path.join("chat_history.jsonl").is_file() {
        return true;
    }
    let sessions = path.join("sessions");
    if !sessions.is_dir() {
        return false;
    }
    // Prefer marker that is not Codex year partitions
    for cwd_ent in std::fs::read_dir(&sessions).into_iter().flatten().flatten() {
        let cwd_path = cwd_ent.path();
        if !cwd_path.is_dir() {
            continue;
        }
        let name = cwd_ent.file_name().to_string_lossy().to_string();
        // Codex year folders are pure digits (YYYY)
        if name.chars().all(|c| c.is_ascii_digit()) && name.len() == 4 {
            continue;
        }
        for sess in std::fs::read_dir(&cwd_path).into_iter().flatten().flatten() {
            let sp = sess.path();
            if sp.join("summary.json").is_file()
                || sp.join("chat_history.jsonl").is_file()
                || sp.join("updates.jsonl").is_file()
            {
                return true;
            }
        }
    }
    false
}

/// Parse an explicit source string into a Provider.
pub fn parse_source(source: &str) -> Provider {
    match source.to_lowercase().as_str() {
        "claude" => Provider::Claude,
        "claude-desktop" => Provider::ClaudeDesktop,
        "copilot" => Provider::Copilot,
        "cursor" => Provider::Cursor,
        "codex" => Provider::Codex,
        "gemini" => Provider::Gemini,
        "grok" | "grok-build" => Provider::Grok,
        _ => Provider::Unknown,
    }
}

/// Resolve provider: explicit source overrides auto-detection.
pub fn resolve_provider(path: &Path, source: Option<&str>) -> Provider {
    if let Some(s) = source {
        let p = parse_source(s);
        if p != Provider::Unknown {
            return p;
        }
    }
    detect_provider(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn tmp(label: &str) -> PathBuf {
        let p = std::env::temp_dir().join(format!(
            "agent_data_detect_{}_{}_{}",
            std::process::id(),
            label,
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&p).unwrap();
        p
    }

    #[test]
    fn cursor_agent_transcripts_not_claude() {
        let root = tmp("cursor");
        let at = root
            .join("projects")
            .join("foo")
            .join("agent-transcripts")
            .join("sid");
        fs::create_dir_all(&at).unwrap();
        fs::write(at.join("sid.jsonl"), "{}\n").unwrap();
        assert_eq!(detect_provider(&root), Provider::Cursor);
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn grok_sessions_layout() {
        let root = tmp("grok");
        let sess = root
            .join("sessions")
            .join("%2FUsers%2Ftest")
            .join("019f-session-id");
        fs::create_dir_all(&sess).unwrap();
        fs::write(sess.join("summary.json"), "{}").unwrap();
        assert_eq!(detect_provider(&root), Provider::Grok);
        let _ = fs::remove_dir_all(&root);
    }
}
