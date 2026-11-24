# SPDX-FileCopyrightText: 2026 Shiva Birudaraju
#
# SPDX-License-Identifier: MIT
"""Exercise example-name resolution against a real in-memory bundle index."""

import os

import pytest

from circup.command_utils import resolve_example_name


@pytest.mark.parametrize(
    "name",
    [
        "ble/ble_uart_echo_test",
        "ble/ble_uart_echo_test.py",
        "adafruit_ble/ble_uart_echo_test",
        "adafruit_ble/ble_uart_echo_test.py",
        "adafruit_ble/examples/ble_uart_echo_test",
        "adafruit_ble/examples/ble_uart_echo_test.py",
    ],
)
def test_reported_example_spellings(name):
    """The one-argument forms from #251 resolve without device/network mocks."""
    key = os.path.join("ble", "ble_uart_echo_test")
    assert resolve_example_name(name, {key: "unused.py"}) == key


def test_preserve_prefix_inside_filename_and_nested_directory():
    """Only the library prefix is removable, not text inside the example path."""
    key = os.path.join("ble", "subdir", "adafruit_ble_demo")
    assert (
        resolve_example_name("adafruit_ble/subdir/adafruit_ble_demo.py", {key: ""})
        == key
    )


def test_exact_match_wins_over_normalized_name():
    """A real prefixed library's entry must not be replaced by a short-name match."""
    key = os.path.join("adafruit_ble", "demo.py")
    fallback = os.path.join("ble", "demo")
    assert resolve_example_name(key, {key: "original", fallback: "other"}) == key


def test_exact_examples_directory_wins_over_stripped_directory():
    """Preserve genuine nested examples directories when both entries exist."""
    key = os.path.join("ble", "examples", "demo")
    fallback = os.path.join("ble", "demo")
    assert resolve_example_name(key, {key: "original", fallback: "other"}) == key


@pytest.mark.parametrize("name", ["missing/demo.py", "adafruit_ble/missing.py", ""])
def test_unknown_names_remain_unchanged(name):
    """Fallbacks never invent an example or turn an unknown name into a file path."""
    assert (
        resolve_example_name(name, {os.path.join("ble", "demo"): "unused.py"}) == name
    )
