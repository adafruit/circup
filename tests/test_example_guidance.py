# SPDX-FileCopyrightText: 2026 Shiva Birudaraju
#
# SPDX-License-Identifier: MIT
"""Exercise example discovery guidance without device or network IO."""

import os
from unittest import mock

from click.testing import CliRunner

from circup.commands import example


def test_no_arguments_shows_help_without_loading_bundles():
    """An empty invocation should explain how to select an example."""
    with mock.patch("circup.commands.get_bundle_examples") as get_examples:
        result = CliRunner().invoke(example, [], obj={})
    assert result.exit_code == 2, result.output
    assert "Usage:" in result.output
    assert "circup example --list" in result.output
    get_examples.assert_not_called()


def test_unknown_example_explains_how_to_find_names():
    """A missing example should point to the supported discovery command."""
    with mock.patch("circup.commands.get_bundles_list", return_value=[]), mock.patch(
        "circup.commands.get_bundle_examples", return_value={}
    ):
        result = CliRunner().invoke(
            example, ["missing/example.py"], obj={"BUNDLE_TAGS": {}}
        )
    assert "missing/example.py was not found" in result.output
    assert "circup example --list" in result.output
    assert "circup example [searchterm] --list" in result.output


def test_list_without_names_still_lists_libraries():
    """The empty-argument help must not swallow the --list operation."""
    with mock.patch("circup.commands.get_bundles_list", return_value=[]), mock.patch(
        "circup.commands.get_bundle_examples",
        return_value={os.path.join("ble", "ble_uart_echo_test"): "unused.py"},
    ):
        result = CliRunner().invoke(example, ["--list"], obj={"BUNDLE_TAGS": {}})
    assert result.exit_code == 0, result.output
    assert "Available example libraries:\nble" in result.output


def test_named_example_still_copies_to_device():
    """Guidance changes must preserve copying an existing named example."""
    backend = mock.Mock()
    backend.file_exists.return_value = False
    path = os.path.join("examples", "ble_uart_echo_test.py")
    name = os.path.join("ble", "ble_uart_echo_test")
    with mock.patch("circup.commands.get_bundles_list", return_value=[]), mock.patch(
        "circup.commands.get_bundle_examples", return_value={name: path}
    ):
        result = CliRunner().invoke(
            example, [name], obj={"BUNDLE_TAGS": {}, "backend": backend}
        )
    assert result.exit_code == 0, result.output
    backend.install_module_py.assert_called_once_with({"path": path}, location="")
