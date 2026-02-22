"""Entry point for `python -m agent_chronicle`."""

import argparse
from agent_chronicle.app import AgentChronicle
from agent_chronicle.themes import THEME_NAMES, DEFAULT_THEME


def main():
    parser = argparse.ArgumentParser(description="Agent Chronicle TUI")
    parser.add_argument("--claude-path", default="~/.claude", help="Path to Claude data directory")
    parser.add_argument("--copilot-path", default="~/.copilot", help="Path to Copilot data directory")
    parser.add_argument("--theme", default=DEFAULT_THEME, choices=THEME_NAMES,
                        help=f"Color theme (default: {DEFAULT_THEME})")
    args = parser.parse_args()

    app = AgentChronicle(claude_path=args.claude_path, copilot_path=args.copilot_path, theme_name=args.theme)
    app.run()


if __name__ == "__main__":
    main()
