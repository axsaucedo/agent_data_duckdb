"""Entry point for `python -m agent_chronicle`."""

import argparse
from agent_chronicle.app import AgentChronicle


def main():
    parser = argparse.ArgumentParser(description="Agent Chronicle TUI")
    parser.add_argument("--claude-path", default="~/.claude", help="Path to Claude data directory")
    parser.add_argument("--copilot-path", default="~/.copilot", help="Path to Copilot data directory")
    args = parser.parse_args()

    app = AgentChronicle(claude_path=args.claude_path, copilot_path=args.copilot_path)
    app.run()


if __name__ == "__main__":
    main()
