use std::path::Path;

/// Supported data providers.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Provider {
    Claude,
    ClaudeDesktop,
    Copilot,
    Cursor,
    Unknown,
}

/// Auto-detect provider from directory structure.
/// - `local-agent-mode-sessions/` directory → Claude Desktop
/// - `projects/` directory → Claude
/// - `session-state/` directory → Copilot
/// - `state.vscdb` file (passed directly or found in the directory) → Cursor
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
    // Cursor: the vscdb file may be passed directly, or its parent directory.
    if path.extension().map_or(false, |e| e == "vscdb") || path.join("state.vscdb").is_file() {
        return Provider::Cursor;
    }
    Provider::Unknown
}

/// Parse an explicit source string into a Provider.
pub fn parse_source(source: &str) -> Provider {
    match source.to_lowercase().as_str() {
        "claude" => Provider::Claude,
        "claude-desktop" => Provider::ClaudeDesktop,
        "copilot" => Provider::Copilot,
        "cursor" => Provider::Cursor,
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
