"""Tokyo Night dark theme for Agent Chronicle TUI.

Uses transparent backgrounds so the terminal wallpaper shows through.
"""

from textual.theme import Theme

THEME = Theme(
    name="tokyo-night",
    primary="#7aa2f7",
    secondary="#bb9af7",
    error="#f7768e",
    success="#9ece6a",
    accent="#e0af68",
    foreground="#c0caf5",
    background="transparent",
    surface="#24283b",
    panel="#16161e",
    dark=True,
    variables={
        "overlay": "#414868",
        "subtext": "#a9b1d6",
        "muted": "#565f89",
        "odd-row": "#1f2030",
        "cursor-bg": "#33467c",
        "focus-cursor": "#414868",
        "border-color": "#414868",
        "header-bg": "#16161e",
    },
)
