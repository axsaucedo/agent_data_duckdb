.PHONY: run dev test install clean

run:
	uv run python -m agent_chronicle

dev:
	uv run textual run --dev agent_chronicle.app:AgentChronicle

test:
	uv run pytest tests/ -v

install:
	uv sync

clean:
	rm -rf __pycache__ .pytest_cache agent_chronicle/__pycache__ tests/__pycache__
