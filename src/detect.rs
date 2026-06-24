use std::path::Path;

/// Supported data providers.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Provider {
    Claude,
    ClaudeDesktop,
    Copilot,
    Codex,
    Unknown,
}

/// Auto-detect provider from directory structure.
/// - `local-agent-mode-sessions/` directory → Claude Desktop
/// - `projects/` directory → Claude
/// - `session-state/` directory → Copilot
/// - `sessions/` with `YYYY/` date partitions (rollout files) → Codex
pub fn detect_provider(path: &Path) -> Provider {
    if path.join("local-agent-mode-sessions").is_dir() {
        return Provider::ClaudeDesktop;
    }
    if path.join("projects").is_dir() {
        return Provider::Claude;
    }
    if path.join("session-state").is_dir() {
        return Provider::Copilot;
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
    Provider::Unknown
}

/// Parse an explicit source string into a Provider.
pub fn parse_source(source: &str) -> Provider {
    match source.to_lowercase().as_str() {
        "claude" => Provider::Claude,
        "claude-desktop" => Provider::ClaudeDesktop,
        "copilot" => Provider::Copilot,
        "codex" => Provider::Codex,
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
