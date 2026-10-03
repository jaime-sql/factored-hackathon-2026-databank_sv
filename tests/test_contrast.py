"""Score, badge, and draft-label colors meet WCAG AA on the light packet card."""

from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "static" / "css" / "app.css").read_text(
    encoding="utf-8"
)

SELECTORS = (
    '.score-line[data-band="high"]',
    '.score-line[data-band="review"]',
    '.score-line[data-band="low"]',
    '.score-line[data-band="out_of_scope"]',
    ".draft-label",
    '.grounded[data-grounded="1"]',
    '.grounded[data-grounded="0"]',
)


def _channel(value: int) -> float:
    color = value / 255
    if color <= 0.04045:
        return color / 12.92
    return ((color + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    raw = hex_color.removeprefix("#")
    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(left: str, right: str) -> float:
    lighter = max(_luminance(left), _luminance(right))
    darker = min(_luminance(left), _luminance(right))
    return (lighter + 0.05) / (darker + 0.05)


def _block(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS, re.S)
    assert match, selector
    return match.group(1)


def _color(selector: str, prop: str) -> str:
    match = re.search(prop + r":\s*(#[0-9a-fA-F]{6})", _block(selector))
    assert match, selector
    return match.group(1).lower()


def test_light_card_colors_are_aa() -> None:
    background = _color(".packet-panel", "background")
    assert background == "#fffdf8"
    for selector in SELECTORS:
        color = _color(selector, "color")
        ratio = contrast(color, background)
        assert ratio >= 4.5, f"{selector} {color} on {background} is {ratio:.2f}"


def test_trail_flag_chip_is_aa() -> None:
    color = _color("pre .flag-chip", "color")
    background = _color("pre", "background")
    assert color == "#e8e0d4"
    assert background == "#241f1a"
    ratio = contrast(color, background)
    assert ratio >= 4.5, f"trail chip {color} on {background} is {ratio:.2f}"


def test_fairness_gap_row_is_aa() -> None:
    color = _color("#fairness tr.fair-gap", "color")
    background = _color("#fairness tr.fair-gap", "background")
    assert color == "#7a5200"
    assert background == "#fffdf8"
    ratio = contrast(color, background)
    assert ratio >= 4.5, f"fairness gap {color} on {background} is {ratio:.2f}"
