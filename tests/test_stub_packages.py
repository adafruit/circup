# SPDX-FileCopyrightText: 2026 Shiva Birudaraju
#
# SPDX-License-Identifier: MIT
"""Regression coverage for the host-side package names used by --stubs."""

from unittest import mock

import pytest
from click.testing import CliRunner

from circup.commands import install
from circup.command_utils import clean_library_name, get_pypi_name


@pytest.mark.parametrize(
    "library,package",
    [
        ("adafruit_io", "adafruit-circuitpython-adafruitio"),
        ("asyncio", "adafruit-circuitpython-asyncio"),
        ("adafruit_connection_manager", "adafruit-circuitpython-connectionmanager"),
        ("neopixel", "adafruit-circuitpython-neopixel"),
    ],
)
def test_distribution_names_round_trip(library, package):
    """Known Adafruit aliases share the forward and reverse naming rules."""
    assert get_pypi_name(library) == package
    assert clean_library_name(package) == library


def test_community_name_fallback_is_unchanged():
    """The fix does not guess new PyPI distributions for community libraries."""
    assert (
        get_pypi_name("pimoroni_circuitpython_ltr559")
        == "adafruit-circuitpython-pimoroni_circuitpython_ltr559"
    )


@pytest.mark.parametrize(
    "library,package",
    [
        ("adafruit_button", "adafruit-circuitpython-display_button"),
        ("adafruit_bus_device", "adafruit-circuitpython-busdevice"),
        ("adafruit_bme280", "adafruit-circuitpython-bme280"),
    ],
)
def test_install_stubs_uses_distribution_name(library, package):
    """Resolve irregular names before invoking pip, without device/network IO."""
    backend = mock.Mock()
    context = {
        "backend": backend,
        "DEVICE_PATH": "unused-test-device",
        "DEVICE_PLATFORM_VERSION": "10mpy",
        "BUNDLE_TAGS": {},
    }
    with mock.patch("circup.commands.get_bundles_list", return_value=[]), mock.patch(
        "circup.commands.get_bundle_versions", return_value={library + ".py": {}}
    ), mock.patch(
        "circup.commands.get_dependencies", return_value=[library]
    ), mock.patch(
        "circup.commands.is_virtual_env_active", return_value=True
    ), mock.patch(
        "circup.commands.Bundle.offline", False
    ), mock.patch(
        "circup.commands.subprocess.check_output", return_value=b""
    ) as pip_install:
        result = CliRunner().invoke(install, ["--stubs", library], obj=context)

    assert result.exit_code == 0, result.output
    pip_install.assert_called_once_with(["pip", "install", package])
