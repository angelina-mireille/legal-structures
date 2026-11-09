"""Strict YAML loading shared by the graph and rule loaders.

Safe loading only, plus two guards: a key that appears twice in a mapping is an error
(instead of the last value silently winning), and YAML floats are read as exact
Decimals from their written text.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Final

import yaml
from yaml.constructor import ConstructorError

_YAML_SPECIAL_FLOATS: Final[dict[str, str]] = {
    ".inf": "Infinity",
    "+.inf": "Infinity",
    "-.inf": "-Infinity",
    ".nan": "NaN",
}


class StrictYAMLError(Exception):
    """Raised when text is not valid YAML or breaks a strict-loading guard."""


class StrictLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys and reads floats as Decimal."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        """Build a mapping, failing on any key that appears twice."""
        self.flatten_mapping(node)
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError:
                continue  # unhashable key: the base constructor reports it
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _construct_decimal(loader: StrictLoader, node: yaml.ScalarNode) -> Decimal:
    """Read a YAML float from its written text, so 33.3 is exactly Decimal("33.3")."""
    text = str(loader.construct_scalar(node)).replace("_", "").lower()
    try:
        return Decimal(_YAML_SPECIAL_FLOATS.get(text, text))
    except InvalidOperation as err:
        raise ConstructorError(
            None, None, f"cannot read {text!r} as a number", node.start_mark
        ) from err


StrictLoader.add_constructor("tag:yaml.org,2002:float", _construct_decimal)


def load_yaml(text: str) -> Any:
    """Parse text with StrictLoader; any YAML problem raises StrictYAMLError."""
    try:
        return yaml.load(text, Loader=StrictLoader)  # safe: a SafeLoader subclass
    except yaml.YAMLError as err:
        raise StrictYAMLError(str(err)) from err
