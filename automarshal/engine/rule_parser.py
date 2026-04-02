"""YAML-based rule parser for the AutoMarshal DSL.

Rule format (rules.yaml):
    - name: "Hazard Turn 4"
      if: "car.velocity < 10 and car.track_position == 'Turn 4'"
      then:
        light: "Sector_4_Yellow"
        radio_drivers: "Caution Turn 4. Caution Turn 4."
        radio_rc: "Sector 4 stopped car."

The ``if`` expression is evaluated against a *safe sandbox* that only exposes
the ``car`` namespace (a CarTelemetry instance) plus a small set of
comparison helpers.  No builtins other than a curated whitelist are available,
so user-supplied YAML cannot execute arbitrary code.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from automarshal.models.car import CarTelemetry

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Safe expression evaluator
# ──────────────────────────────────────────────────────────────────────────────

# Allowed names inside a rule expression (prevent arbitrary code injection)
_SAFE_BUILTINS: dict[str, Any] = {
    "True": True,
    "False": False,
    "None": None,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}

# Guard against dunder access (e.g. __class__, __import__)
_DUNDER_RE = re.compile(r"__\w+__")


def _safe_eval(expression: str, car: CarTelemetry) -> bool:
    """Evaluate *expression* with ``car`` in scope.

    Only a curated set of builtins is accessible; dunder names are blocked at
    parse time to prevent attribute traversal attacks.

    Args:
        expression: Python boolean expression string from the YAML rule.
        car: The CarTelemetry instance to expose as ``car``.

    Returns:
        True if the expression evaluates to a truthy value, False otherwise.

    Raises:
        ValueError: If the expression contains forbidden patterns.
    """
    if _DUNDER_RE.search(expression):
        raise ValueError(f"Forbidden pattern in rule expression: {expression!r}")

    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS, "car": car}
    try:
        result = eval(expression, namespace)  # noqa: S307  # safe: restricted namespace
    except Exception as exc:
        logger.warning("Rule expression %r raised %s: %s", expression, type(exc).__name__, exc)
        return False
    return bool(result)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class RuleAction:
    """Actions to execute when a rule fires.

    Attributes:
        light: Light panel / sector identifier to activate.
        radio_drivers: Message to broadcast on the Drivers channel.
        radio_rc: Message to initiate on the Race Control channel.
    """

    light: str = ""
    radio_drivers: str = ""
    radio_rc: str = ""


@dataclass
class Rule:
    """A single parsed marshalling rule.

    Attributes:
        name: Human-readable rule name.
        condition: Raw Python expression string.
        action: Actions to execute when the condition is met.
    """

    name: str
    condition: str
    action: RuleAction = field(default_factory=RuleAction)

    def evaluate(self, car: CarTelemetry) -> bool:
        """Return True if this rule's condition holds for *car*."""
        return _safe_eval(self.condition, car)


# ──────────────────────────────────────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────────────────────────────────────


class RuleParser:
    """Load and expose a list of :class:`Rule` objects from a YAML file.

    Usage::

        parser = RuleParser("rules/rules.yaml")
        parser.load()
        for rule in parser.rules:
            if rule.evaluate(car):
                handle_action(rule.action)
    """

    def __init__(self, rules_path: str | Path) -> None:
        self._path = Path(rules_path)
        self.rules: list[Rule] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Parse the YAML file and populate :attr:`rules`.

        Raises:
            FileNotFoundError: If the rules file does not exist.
            yaml.YAMLError: If the file cannot be parsed as valid YAML.
        """
        raw = self._path.read_text(encoding="utf-8")
        documents: list[dict] = yaml.safe_load(raw) or []
        if not isinstance(documents, list):
            raise ValueError(f"Expected a YAML list in {self._path}; got {type(documents)}")

        self.rules = []
        for doc in documents:
            rule = self._parse_rule(doc)
            if rule is not None:
                self.rules.append(rule)

        logger.info("Loaded %d rule(s) from %s", len(self.rules), self._path)

    def evaluate_all(self, car: CarTelemetry) -> list[Rule]:
        """Return all rules whose condition is True for *car*."""
        return [r for r in self.rules if r.evaluate(car)]

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_rule(doc: dict) -> Rule | None:
        """Convert a raw YAML dict into a :class:`Rule`."""
        name = doc.get("name", "<unnamed>")
        condition = doc.get("if", "")
        if not condition:
            logger.warning("Rule %r has no 'if' clause; skipping.", name)
            return None

        then_block: dict = doc.get("then", {}) or {}
        action = RuleAction(
            light=str(then_block.get("light", "")),
            radio_drivers=str(then_block.get("radio_drivers", "")),
            radio_rc=str(then_block.get("radio_rc", "")),
        )
        return Rule(name=name, condition=condition, action=action)
