"""Tests for the YAML rule parser."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from automarshal.engine.rule_parser import RuleParser, RuleAction, _safe_eval
from automarshal.models.car import CarTelemetry


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _write_rules(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def _car(**kwargs) -> CarTelemetry:
    defaults = dict(
        car_id="42",
        car_class="GT3",
        track_position="Turn 4",
        sector_id=3,
        velocity_kmh=50.0,
        current_sector_time=30.0,
        last_sector_time=28.0,
        gap_to_car_ahead=5.0,
    )
    defaults.update(kwargs)
    return CarTelemetry(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# safe_eval
# ──────────────────────────────────────────────────────────────────────────────


def test_safe_eval_simple_true():
    car = _car(velocity_kmh=5.0)
    assert _safe_eval("car.velocity_kmh < 10", car) is True


def test_safe_eval_simple_false():
    car = _car(velocity_kmh=50.0)
    assert _safe_eval("car.velocity_kmh < 10", car) is False


def test_safe_eval_string_comparison():
    car = _car(track_position="Turn 4")
    assert _safe_eval("car.track_position == 'Turn 4'", car) is True


def test_safe_eval_compound():
    car = _car(velocity_kmh=8.0, track_position="Turn 4")
    assert _safe_eval("car.velocity_kmh < 10 and car.track_position == 'Turn 4'", car) is True


def test_safe_eval_dunder_blocked():
    car = _car()
    with pytest.raises(ValueError, match="Forbidden pattern"):
        _safe_eval("car.__class__", car)


def test_safe_eval_exception_returns_false():
    car = _car()
    # division by zero – should not propagate, should return False
    result = _safe_eval("1 / 0 > 0", car)
    assert result is False


# ──────────────────────────────────────────────────────────────────────────────
# RuleParser.load
# ──────────────────────────────────────────────────────────────────────────────


def test_load_valid_file(tmp_path):
    path = _write_rules(
        tmp_path,
        """
        - name: "Test rule"
          if: "car.velocity_kmh < 10"
          then:
            light: "Sector_1_Yellow"
            radio_drivers: "Caution Sector 1."
            radio_rc: "Slow car sector 1."
        """,
    )
    parser = RuleParser(path)
    parser.load()
    assert len(parser.rules) == 1
    rule = parser.rules[0]
    assert rule.name == "Test rule"
    assert rule.condition == "car.velocity_kmh < 10"
    assert rule.action.light == "Sector_1_Yellow"
    assert rule.action.radio_drivers == "Caution Sector 1."
    assert rule.action.radio_rc == "Slow car sector 1."


def test_load_missing_if_skips_rule(tmp_path, caplog):
    path = _write_rules(
        tmp_path,
        """
        - name: "No condition"
          then:
            light: "Sector_1_Yellow"
        """,
    )
    parser = RuleParser(path)
    parser.load()
    assert len(parser.rules) == 0


def test_load_file_not_found():
    parser = RuleParser("/nonexistent/path/rules.yaml")
    with pytest.raises(FileNotFoundError):
        parser.load()


def test_load_multiple_rules(tmp_path):
    path = _write_rules(
        tmp_path,
        """
        - name: "Rule A"
          if: "car.velocity_kmh < 10"
          then:
            light: "Sector_1_Yellow"
        - name: "Rule B"
          if: "car.sector_id == 2"
          then:
            light: "Sector_3_Yellow"
        """,
    )
    parser = RuleParser(path)
    parser.load()
    assert len(parser.rules) == 2


# ──────────────────────────────────────────────────────────────────────────────
# evaluate_all
# ──────────────────────────────────────────────────────────────────────────────


def test_evaluate_all_matches_correct_rules(tmp_path):
    path = _write_rules(
        tmp_path,
        """
        - name: "Slow car"
          if: "car.velocity_kmh < 10"
          then:
            light: "Sector_1_Yellow"
        - name: "Fast car"
          if: "car.velocity_kmh > 100"
          then:
            light: "Sector_1_Green"
        """,
    )
    parser = RuleParser(path)
    parser.load()

    slow_car = _car(velocity_kmh=5.0)
    matches = parser.evaluate_all(slow_car)
    assert len(matches) == 1
    assert matches[0].name == "Slow car"


def test_evaluate_all_no_matches(tmp_path):
    path = _write_rules(
        tmp_path,
        """
        - name: "Slow car"
          if: "car.velocity_kmh < 10"
          then:
            light: "Sector_1_Yellow"
        """,
    )
    parser = RuleParser(path)
    parser.load()

    fast_car = _car(velocity_kmh=150.0)
    assert parser.evaluate_all(fast_car) == []
