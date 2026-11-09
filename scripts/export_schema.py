"""Write schemas/graph.schema.json from the graph model.

Run with: uv run python scripts/export_schema.py
A test fails if the committed file differs from a fresh export.
"""

import json
from pathlib import Path

from core.graph import Graph

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "graph.schema.json"


def build_schema() -> str:
    """Return the graph JSON Schema as text: sorted keys, 2-space indent, trailing newline."""
    return json.dumps(Graph.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    """Write the schema to SCHEMA_PATH."""
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(build_schema(), encoding="utf-8")
    print(f"wrote {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
