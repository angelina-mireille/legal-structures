"""Write schemas/graph.schema.json and schemas/rule.schema.json from the models.

Run with: uv run python scripts/export_schema.py
Tests fail if either committed file differs from a fresh export.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from core.graph import Graph
from core.rules import Rule

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_PATH = SCHEMA_DIR / "graph.schema.json"
RULE_SCHEMA_PATH = SCHEMA_DIR / "rule.schema.json"


def _dump(model: type[BaseModel]) -> str:
    """Return a model's JSON Schema as text: sorted keys, 2-space indent, trailing newline."""
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def build_schema() -> str:
    """Return the graph JSON Schema as text."""
    return _dump(Graph)


def build_rule_schema() -> str:
    """Return the rule JSON Schema as text (one rule file)."""
    return _dump(Rule)


def main() -> None:
    """Write both schemas."""
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in ((SCHEMA_PATH, build_schema()), (RULE_SCHEMA_PATH, build_rule_schema())):
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
