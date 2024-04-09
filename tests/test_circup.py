# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
# pylint: disable=too-many-lines,use-implicit-booleaness-not-comparison
# pylint: disable=invalid-name,unnecessary-dunder-call
"""
Unit tests for the circup module.

Copyright (c) 2019 Adafruit Industries

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import os
import ctypes
import json
import pathlib
from unittest import mock
from click.testing import CliRunner
import pytest
import requests

import circup
from circup import DiskBackend
from circup.command_utils import (
    find_device,
    ensure_latest_bundle,
    get_bundle,
    get_bundles_dict,
)
from circup.shared import PLATFORMS
from circup.module import Module
from circup.logging import logger

TEST_BUNDLE_CONFIG_JSON = "tests/test_bundle_config.json"
with open(TEST_BUNDLE_CONFIG_JSON, "rb") as tbc:
    TEST_BUNDLE_DATA = json.load(tbc)
TEST_BUNDLE_NAME = TEST_BUNDLE_DATA["test_bundle"]

TEST_BUNDLE_CONFIG_LOCAL_JSON = "tests/test_bundle_config_local.json"
with open(TEST_BUNDLE_CONFIG_LOCAL_JSON, "rb") as tbc:
    TEST_BUNDLE_LOCAL_DATA = json.load(tbc)


def test_Bundle_init():
    """
    Create a Bundle and check all the strings are set as expected.
    """
    bundle = circup.Bundle(TEST_BUNDLE_NAME)
    assert repr(bundle) == repr(
        {
            "key": TEST_BUNDLE_NAME,
            "url": "https://github.com/" + TEST_BUNDLE_NAME,
            "urlzip": "adafruit-circuitpython-bundle-{platform}-{tag}.zip",
            "dir": circup.shared.DATA_DIR
            + "/adafruit/adafruit-circuitpython-bundle-{platform}",
            "zip": circup.shared.DATA_DIR
            + "/adafruit-circuitpython-bundle-{platform}.zip",
            "url_format": "https://github.com/"
            + TEST_BUNDLE_NAME
            + "/releases/download/{tag}/"
            "adafruit-circuitpython-bundle-{platform}-{tag}.zip",
            "current": None,
            "latest": None,
        }
    )


def test_Bundle_lib_dir():
    """
    Check the return of Bundle.lib_dir with a test tag.
    """
    bundle_data = {TEST_BUNDLE_NAME: "TESTTAG"}
    with mock.patch("circup.bundle.tags_data_load", return_value=bundle_data):
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        assert bundle.current_tag == "TESTTAG"
        assert bundle.lib_dir("py") == (
            circup.shared.DATA_DIR + "/"
            "adafruit/adafruit-circuitpython-bundle-py/"
            "adafruit-circuitpython-bundle-py-TESTTAG/lib"
        )
        assert bundle.lib_dir("8mpy") == (
            circup.shared.DATA_DIR + "/"
            "adafruit/adafruit-circuitpython-bundle-8mpy/"
            "adafruit-circuitpython-bundle-8.x-mpy-TESTTAG/lib"
        )


def test_Bundle_latest_tag():
    """
    Check the latest tag gets through Bundle.latest_tag.
    """
    bundle_data = {TEST_BUNDLE_NAME: "TESTTAG"}
    with mock.patch(
        "circup.bundle.get_latest_release_from_url", return_value="BESTESTTAG"
    ), mock.patch("circup.bundle.tags_data_load", return_value=bundle_data):
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        assert bundle.latest_tag == "BESTESTTAG"


def test_get_bundles_dict():
    """
    Check we are getting the bundles list from BUNDLE_CONFIG_FILE.
    """
    with mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_FILE", TEST_BUNDLE_CONFIG_JSON
    ), mock.patch("circup.shared.BUNDLE_CONFIG_LOCAL", ""):
        bundles_dict = get_bundles_dict()
        assert bundles_dict == TEST_BUNDLE_DATA

    with mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_FILE", TEST_BUNDLE_CONFIG_JSON
    ), mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_LOCAL", TEST_BUNDLE_CONFIG_LOCAL_JSON
    ):
        bundles_dict = get_bundles_dict()
        expected_dict = {**TEST_BUNDLE_LOCAL_DATA, **TEST_BUNDLE_DATA}
        assert bundles_dict == expected_dict


def test_get_bundles_local_dict():
    """
    Check we are getting the bundles list from BUNDLE_CONFIG_LOCAL.
    """
    with mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_FILE", TEST_BUNDLE_CONFIG_JSON
    ), mock.patch("circup.command_utils.BUNDLE_CONFIG_LOCAL", ""):
        bundles_dict = get_bundles_dict()
        assert bundles_dict == TEST_BUNDLE_DATA

    with mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_FILE", TEST_BUNDLE_CONFIG_JSON
    ), mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_LOCAL", TEST_BUNDLE_CONFIG_LOCAL_JSON
    ):
        bundles_dict = get_bundles_dict()
        expected_dict = {**TEST_BUNDLE_LOCAL_DATA, **TEST_BUNDLE_DATA}
        assert bundles_dict == expected_dict


def test_get_bundles_list():
    """
    Check we are getting the bundles list from BUNDLE_CONFIG_FILE.
    """
    with mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_FILE", TEST_BUNDLE_CONFIG_JSON
    ), mock.patch("circup.command_utils.BUNDLE_CONFIG_LOCAL", ""):
        bundles_list = circup.get_bundles_list()
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        assert repr(bundles_list) == repr([bundle])


def test_save_local_bundles():
    """
    Pretend to save local bundles.
    """
    with mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_FILE", TEST_BUNDLE_CONFIG_JSON
    ), mock.patch("circup.command_utils.BUNDLE_CONFIG_LOCAL", ""), mock.patch(
        "circup.os.unlink"
    ) as mock_unlink, mock.patch(
        "circup.command_utils.json.dump"
    ) as mock_dump, mock.patch(
        "circup.command_utils.open", mock.mock_open()
    ) as mock_open:
        final_data = {**TEST_BUNDLE_DATA, **TEST_BUNDLE_LOCAL_DATA}
        circup.save_local_bundles(final_data)
        mock_dump.assert_called_once_with(final_data, mock_open())
        mock_unlink.assert_not_called()


def test_save_local_bundles_reset():
    """
    Pretend to reset the local bundles.
    """
    with mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_FILE", TEST_BUNDLE_CONFIG_JSON
    ), mock.patch(
        "circup.command_utils.BUNDLE_CONFIG_LOCAL", "test/NOTEXISTS"
    ), mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch(
        "circup.os.unlink"
    ) as mock_unlink, mock.patch(
        "circup.command_utils.json.load", return_value=TEST_BUNDLE_DATA
    ), mock.patch(
        "circup.command_utils.open", mock.mock_open()
    ) as mock_open:
        circup.save_local_bundles({})
        mock_open().write.assert_not_called()
        mock_unlink.assert_called_once_with("test/NOTEXISTS")


def test_Module_init_file_module():
    """
    Ensure the Module instance is set up as expected and logged, as if for a
    single file Python module.
    """
    name = "local_module.py"
    path = os.path.join("mock_device", "lib", name)
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "3.2.1"

    with mock.patch("circup.logger.info") as mock_logger, mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch(
        "circup.bundle.Bundle.lib_dir",
        return_value="tests",
    ):
        backend = DiskBackend("mock_device", mock_logger)
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        m = Module(
            name,
            backend,
            repo,
            device_version,
            bundle_version,
            False,
            bundle,
            (None, None),
        )
        mock_logger.assert_called_once_with(m)
        assert m.path == path
        assert m.file == "local_module.py"
        assert m.name == "local_module"
        assert m.repo == repo
        assert m.device_version == device_version
        assert m.bundle_version == bundle_version
        assert m.bundle_path == os.path.join("tests", m.file)
        assert m.mpy is False


def test_Module_init_directory_module():
    """
    Ensure the Module instance is set up as expected and logged, as if for a
    directory based Python module.
    """
    name = "dir_module/"
    path = os.path.join("tests", "mock_device", "lib", f"{name}", "")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "3.2.1"
    mpy = True
    with mock.patch("circup.logger.info") as mock_logger, mock.patch(
        "circup.bundle.Bundle.lib_dir", return_value="tests"
    ):
        backend = DiskBackend("tests/mock_device", mock_logger)
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        m = Module(
            name,
            backend,
            repo,
            device_version,
            bundle_version,
            mpy,
            bundle,
            (None, None),
        )
        mock_logger.assert_called_once_with(m)
        assert m.path == path
        assert m.file is None
        assert m.name == "dir_module"
        assert m.repo == repo
        assert m.device_version == device_version
        assert m.bundle_version == bundle_version
        assert m.bundle_path == os.path.join("tests", m.name)
        assert m.mpy is True


def test_Module_outofdate():
    """
    Ensure the ``outofdate`` property on a Module instance returns the expected
    boolean value to correctly indicate if the referenced module is, in fact,
    out of date.
    """
    bundle = circup.Bundle(TEST_BUNDLE_NAME)
    name = "module.py"
    repo = "https://github.com/adafruit/SomeLibrary.git"
    with mock.patch("circup.logger.info") as mock_logger:
        backend = DiskBackend("tests/mock_device", mock_logger)
        m1 = Module(name, backend, repo, "1.2.3", "3.2.1", False, bundle, (None, None))
        m2 = Module(name, backend, repo, "1.2.3", "1.2.3", False, bundle, (None, None))
        # shouldn't happen!
        m3 = Module(name, backend, repo, "3.2.1", "1.2.3", False, bundle, (None, None))
        assert m1.outofdate is True
        assert m2.outofdate is False
        assert m3.outofdate is False


def test_Module_outofdate_bad_versions():
    """
    Sometimes, the version is not a valid semver value. In this case, the
    ``outofdate`` property assumes the module should be updated (to correct
    this problem). Such a problem should be logged.
    """
    bundle = circup.Bundle(TEST_BUNDLE_NAME)
    name = "module.py"

    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "hello"
    bundle_version = "3.2.1"

    with mock.patch("circup.logger.warning") as mock_logger:
        backend = DiskBackend("tests/mock_device", mock_logger)
        m = Module(
            name,
            backend,
            repo,
            device_version,
            bundle_version,
            False,
            bundle,
            (None, None),
        )

        assert m.outofdate is True
        assert mock_logger.call_count == 2


def test_Module_mpy_mismatch():
    """
    Ensure the ``outofdate`` property on a Module instance returns the expected
    boolean value to correctly indicate if the referenced module is, in fact,
    out of date.
    """
    name = "module.py"
    repo = "https://github.com/adafruit/SomeLibrary.git"
    with mock.patch("circup.logger.warning") as mock_logger:
        backend = DiskBackend("tests/mock_device", mock_logger)
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        m1 = Module(name, backend, repo, "1.2.3", "1.2.3", True, bundle, (None, None))
        m2 = Module(
            name,
            backend,
            repo,
            "1.2.3",
            "1.2.3",
            True,
            bundle,
            ("7.0.0-alpha.1", "8.99.99"),
        )
        m3 = Module(
            name, backend, repo, "1.2.3", "1.2.3", True, bundle, (None, "7.0.0-alpha.1")
        )
    with mock.patch(
        "circup.backends.DiskBackend.get_circuitpython_version",
        return_value=("6.2.0", ""),
    ):
        assert m1.mpy_mismatch is False
        assert m1.outofdate is False
        assert m2.mpy_mismatch is True
        assert m2.outofdate is True
        assert m3.mpy_mismatch is False
        assert m3.outofdate is False
    with mock.patch(
        "circup.backends.DiskBackend.get_circuitpython_version",
        return_value=("8.0.0", ""),
    ):
        assert m1.mpy_mismatch is False
        assert m1.outofdate is False
        assert m2.mpy_mismatch is False
        assert m2.outofdate is False
        assert m3.mpy_mismatch is True
        assert m3.outofdate is True


def test_Module_major_update_bad_versions():
    """
    Sometimes, the version is not a valid semver value. In this case, the
    ``major_update`` property assumes the module is a major update, so as not
    to block the user from getting the latest update.
    Such a problem should be logged.
    """
    bundle = circup.Bundle(TEST_BUNDLE_NAME)
    name = "module.py"
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "version-3"

    with mock.patch("circup.logger.warning") as mock_logger:
        backend = DiskBackend("mock_device", mock_logger)
        m = Module(
            name,
            backend,
            repo,
            device_version,
            bundle_version,
            False,
            bundle,
            (None, None),
        )
        assert m.major_update is True
        assert mock_logger.call_count == 2


def test_Module_row():
    """
    Ensure the tuple contains the expected items to be correctly displayed in
    a table of version-related results.
    """
    bundle = circup.Bundle(TEST_BUNDLE_NAME)
    name = "module.py"
    repo = "https://github.com/adafruit/SomeLibrary.git"
    with mock.patch("circup.os.path.isfile", return_value=True), mock.patch(
        "circup.backends.DiskBackend.get_circuitpython_version",
        return_value=("8.0.0", ""),
    ), mock.patch("circup.logger.warning") as mock_logger:
        backend = DiskBackend("mock_device", mock_logger)
        m = Module(name, backend, repo, "1.2.3", None, False, bundle, (None, None))
        assert m.row == ("module", "1.2.3", "unknown", "Major Version")
        m = Module(name, backend, repo, "1.2.3", "1.3.4", False, bundle, (None, None))
        assert m.row == ("module", "1.2.3", "1.3.4", "Minor Version")
        m = Module(name, backend, repo, "1.2.3", "1.2.3", True, bundle, ("9.0.0", None))
        assert m.row == ("module", "1.2.3", "1.2.3", "MPY Format")


def test_Module_update_dir():
    """
    Ensure if the module is a directory, the expected actions take place to
    update the module on the connected device.
    """
    bundle = circup.Bundle(TEST_BUNDLE_NAME)
    name = "adafruit_waveform"
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = None
    with mock.patch("circup.backends.shutil") as mock_shutil, mock.patch(
        "circup.logger.warning"
    ) as mock_logger:
        backend = DiskBackend("tests/mock_device", mock_logger)
        m = Module(
            name,
            backend,
            repo,
            device_version,
            bundle_version,
            False,
            bundle,
            (None, None),
        )
        backend.update(m)
        mock_shutil.rmtree.assert_called_once_with(m.path, ignore_errors=True)
        mock_shutil.copytree.assert_called_once_with(m.bundle_path, m.path)


def test_Module_update_file():
    """
    Ensure if the module is a file, the expected actions take place to
    update the module on the connected device.
    """
    bundle = circup.Bundle(TEST_BUNDLE_NAME)
    name = "colorsys.py"
    # path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = None

    with mock.patch("circup.backends.shutil") as mock_shutil, mock.patch(
        "circup.os.remove"
    ) as mock_remove, mock.patch("circup.logger.warning") as mock_logger:
        backend = circup.DiskBackend("tests/mock_device", mock_logger)
        m = Module(
            name,
            backend,
            repo,
            device_version,
            bundle_version,
            False,
            bundle,
            (None, None),
        )
        backend.update(m)
        mock_remove.assert_called_once_with(m.path)
        mock_shutil.copyfile.assert_called_once_with(m.bundle_path, m.path)


def test_Module_repr():
    """
    Ensure the repr(dict) is returned (helps when logging).
    """
    name = "local_module.py"
    path = os.path.join("mock_device", "lib", f"{name}")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "3.2.1"
    with mock.patch("circup.os.path.isfile", return_value=True), mock.patch(
        "circup.backends.DiskBackend.get_circuitpython_version",
        return_value=("4.1.2", ""),
    ), mock.patch("circup.Bundle.lib_dir", return_value="tests"), mock.patch(
        "circup.logger.warning"
    ) as mock_logger:
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        backend = circup.DiskBackend("mock_device", mock_logger)
        m = Module(
            name,
            backend,
            repo,
            device_version,
            bundle_version,
            False,
            bundle,
            (None, None),
        )
    assert repr(m) == repr(
        {
            "path": path,
            "file": "local_module.py",
            "name": "local_module",
            "repo": repo,
            "device_version": device_version,
            "bundle_version": bundle_version,
            "bundle_path": os.path.join("tests", m.file),
            "mpy": False,
            "min_version": None,
            "max_version": None,
        }
    )


def test_find_device_posix_exists():
    """
    Simulate being on os.name == 'posix' and a call to "mount" returns a
    record indicating a connected device.
    """
    with open("tests/mount_exists.txt", "rb") as fixture_file:
        fixture = fixture_file.read()
        with mock.patch("os.name", "posix"):
            with mock.patch("circup.command_utils.check_output", return_value=fixture):
                assert find_device() == "/media/ntoll/CIRCUITPY"


def test_find_device_posix_no_mount_command():
    """
    When the user doesn't have administrative privileges on OSX then the mount
    command isn't on their path. In which case, check circup uses the more
    explicit /sbin/mount instead.
    """
    with open("tests/mount_exists.txt", "rb") as fixture_file:
        fixture = fixture_file.read()
    mock_check = mock.MagicMock(side_effect=[FileNotFoundError, fixture])
    with mock.patch("os.name", "posix"), mock.patch(
        "circup.command_utils.check_output", mock_check
    ):
        assert find_device() == "/media/ntoll/CIRCUITPY"
        assert mock_check.call_count == 2
        assert mock_check.call_args_list[0][0][0] == "mount"
        assert mock_check.call_args_list[1][0][0] == "/sbin/mount"


def test_find_device_posix_missing():
    """
    Simulate being on os.name == 'posix' and a call to "mount" returns no
    records associated with an Adafruit device.
    """
    with open("tests/mount_missing.txt", "rb") as fixture_file:
        fixture = fixture_file.read()
        with mock.patch("os.name", "posix"), mock.patch(
            "circup.command_utils.check_output", return_value=fixture
        ):
            assert find_device() is None


def test_find_device_nt_exists():
    """
    Simulate being on os.name == 'nt' and a disk with a volume name 'CIRCUITPY'
    exists indicating a connected device.
    """
    mock_windll = mock.MagicMock()
    mock_windll.kernel32 = mock.MagicMock()
    mock_windll.kernel32.GetVolumeInformationW = mock.MagicMock()
    mock_windll.kernel32.GetVolumeInformationW.return_value = None
    fake_buffer = ctypes.create_unicode_buffer("CIRCUITPY")
    with mock.patch("os.name", "nt"), mock.patch(
        "os.path.exists", return_value=True
    ), mock.patch("ctypes.create_unicode_buffer", return_value=fake_buffer):
        ctypes.windll = mock_windll
        assert find_device() == "A:\\"


def test_find_device_nt_missing():
    """
    Simulate being on os.name == 'nt' and a disk with a volume name 'CIRCUITPY'
    does not exist for a device.
    """
    mock_windll = mock.MagicMock()
    mock_windll.kernel32 = mock.MagicMock()
    mock_windll.kernel32.GetVolumeInformationW = mock.MagicMock()
    mock_windll.kernel32.GetVolumeInformationW.return_value = None
    fake_buffer = ctypes.create_unicode_buffer(1024)
    with mock.patch("os.name", "nt"), mock.patch(
        "os.path.exists", return_value=True
    ), mock.patch("ctypes.create_unicode_buffer", return_value=fake_buffer):
        ctypes.windll = mock_windll
        assert find_device() is None


def test_find_device_unknown_os():
    """
    Raises a NotImplementedError if the host OS is not supported.
    """
    with mock.patch("os.name", "foo"):
        with pytest.raises(NotImplementedError) as ex:
            find_device()
    assert ex.value.args[0] == 'OS "foo" not supported.'


def test_get_latest_release_from_url():
    """
    Ensure the expected tag value is extracted from the returned URL (resulting
    from a call to the expected endpoint).
    """
    response = mock.MagicMock()
    response.headers = {
        "Location": "https://github.com/adafruit"
        "/Adafruit_CircuitPython_Bundle/releases/tag/20190903"
    }
    expected_url = "https://github.com/" + TEST_BUNDLE_NAME + "/releases/latest"
    with mock.patch("circup.shared.requests.head", return_value=response) as mock_get:
        result = circup.get_latest_release_from_url(expected_url, logger)
        assert result == "20190903"
        mock_get.assert_called_once_with(expected_url, timeout=mock.ANY)


def test_extract_metadata_python():
    """
    Ensure the dunder objects assigned in code are extracted into a Python
    dictionary representing such metadata.
    """
    code = (
        "# A comment\n"
        '__version__ = "1.1.4"\n'
        '__repo__ = "https://github.com/adafruit/SomeLibrary.git"\n'
        'print("Hello, world!")\n'
    )
    path = "foo.py"
    with mock.patch(
        "builtins.open", mock.mock_open(read_data=code)
    ) as mock_open, mock.patch("circup.logger.warning") as mock_logger:
        result = circup.extract_metadata(path, mock_logger)
        mock_open.assert_called_once_with(path, "r", encoding="utf-8")
    assert len(result) == 3
    assert result["__version__"] == "1.1.4"
    assert result["__repo__"] == "https://github.com/adafruit/SomeLibrary.git"
    assert result["mpy"] is False
    assert "compatibility" not in result


def test_extract_metadata_byte_code_v6():
    """
    Ensure the __version__ is correctly extracted from the bytecode ".mpy"
    file generated from Circuitpython < 7. Version in test_module is 0.9.2
    """
    with mock.patch("circup.logger.warning") as mock_logger:
        result = circup.extract_metadata("tests/test_module.mpy", mock_logger)
        assert result["__version__"] == "0.9.2"
        assert result["mpy"] is True
        assert result["compatibility"] == (None, "7.0.0-alpha.1")


def test_extract_metadata_byte_code_v7():
    """
    Ensure the __version__ is correctly extracted from the bytecode ".mpy"
    file generated from Circuitpython >= 7. Version in local_module_cp7 is 1.2.3
    """
    with mock.patch("circup.logger.warning") as mock_logger:
        result = circup.extract_metadata("tests/local_module_cp7.mpy", mock_logger)
        assert result["__version__"] == "1.2.3"
        assert result["mpy"] is True
        assert result["compatibility"] == ("7.0.0-alpha.1", "8.99.99")


def test_find_modules():
    """
    Ensure that the expected list of Module instances is returned given the
    metadata dictionary fixtures for device and bundle modules.
    """
    with open("tests/device.json", "rb") as f:
        device_modules = json.load(f)
    with open("tests/bundle.json", "rb") as f:
        bundle_modules = json.load(f)

    with mock.patch(
        "circup.DiskBackend.get_device_versions", return_value=device_modules
    ), mock.patch(
        "circup.command_utils.get_bundle_versions", return_value=bundle_modules
    ), mock.patch(
        "circup.logger.warning"
    ) as mock_logger:
        backend = DiskBackend("mock_device", mock_logger)
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        bundles_list = [bundle]
        for module in bundle_modules:
            bundle_modules[module]["bundle"] = bundle

        result = circup.find_modules(backend, bundles_list)
    assert len(result) == 1
    assert result[0].name == "adafruit_74hc595"
    assert (
        result[0].repo
        == "https://github.com/adafruit/Adafruit_CircuitPython_74HC595.git"
    )


def test_find_modules_goes_bang():
    """
    Ensure if there's a problem getting metadata an error message is displayed
    and the utility exists with an error code of 1.
    """
    with mock.patch(
        "circup.DiskBackend.get_device_versions", side_effect=Exception("BANG!")
    ), mock.patch("circup.command_utils.click") as mock_click, mock.patch(
        "circup.sys.exit"
    ) as mock_exit, mock.patch(
        "circup.logger.warning"
    ) as mock_logger:
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        bundles_list = [bundle]
        backend = DiskBackend("mock_devcie", mock_logger)
        circup.find_modules(backend, bundles_list)
        assert mock_click.echo.call_count == 1
        mock_exit.assert_called_once_with(1)


def test_get_bundle_versions():
    """
    Ensure get_modules is called with the path for the library bundle.
    Ensure ensure_latest_bundle is called even if lib_dir exists.
    """
    with mock.patch(
        "circup.command_utils.ensure_latest_bundle"
    ) as mock_elb, mock.patch(
        "circup.command_utils._get_modules_file", return_value={"ok": {"name": "ok"}}
    ) as mock_gm, mock.patch(
        "circup.backends.DiskBackend.get_circuitpython_version",
        return_value=("4.1.2", ""),
    ), mock.patch(
        "circup.bundle.Bundle.lib_dir", return_value="foo/bar/lib"
    ), mock.patch(
        "circup.os.path.isdir", return_value=True
    ), mock.patch(
        "circup.command_utils.logger"
    ) as mock_logger:
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        bundles_list = [bundle]
        assert circup.get_bundle_versions(bundles_list) == {
            "ok": {"name": "ok", "bundle": bundle}
        }
        mock_elb.assert_called_once_with(bundle)
        mock_gm.assert_called_once_with("foo/bar/lib", mock_logger)


def test_get_bundle_versions_avoid_download():
    """
    When avoid_download is True and lib_dir exists, don't ensure_latest_bundle.
    Testing both cases: lib_dir exists and lib_dir doesn't exists.
    """
    with mock.patch(
        "circup.command_utils.ensure_latest_bundle"
    ) as mock_elb, mock.patch(
        "circup.command_utils._get_modules_file", return_value={"ok": {"name": "ok"}}
    ) as mock_gm, mock.patch(
        "circup.backends.DiskBackend.get_circuitpython_version",
        return_value=("4.1.2", ""),
    ), mock.patch(
        "circup.Bundle.lib_dir", return_value="foo/bar/lib"
    ), mock.patch(
        "circup.command_utils.logger"
    ) as mock_logger:
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        bundles_list = [bundle]
        with mock.patch("circup.os.path.isdir", return_value=True):
            assert circup.get_bundle_versions(bundles_list, avoid_download=True) == {
                "ok": {"name": "ok", "bundle": bundle}
            }
            assert mock_elb.call_count == 0
            mock_gm.assert_called_once_with("foo/bar/lib", mock_logger)
        with mock.patch("circup.os.path.isdir", return_value=False):
            assert circup.get_bundle_versions(bundles_list, avoid_download=True) == {
                "ok": {"name": "ok", "bundle": bundle}
            }
            mock_elb.assert_called_once_with(bundle)
            mock_gm.assert_called_with("foo/bar/lib", mock_logger)


def test_get_circuitpython_version():
    """
    Given valid content of a boot_out.txt file on a connected device, return
    the version number of CircuitPython running on the board.
    """
    with mock.patch("circup.logger.warning") as mock_logger:
        backend = DiskBackend("tests/mock_device", mock_logger)
        assert backend.get_circuitpython_version() == (
            "8.1.0",
            "this_is_a_board",
        )


def test_get_device_versions():
    """
    Ensure get_modules is called with the path for the attached device.
    """
    with mock.patch(
        "circup.DiskBackend.get_modules", return_value="ok"
    ) as mock_gm, mock.patch("circup.logger.warning") as mock_logger:
        backend = circup.DiskBackend("tests/mock_device", mock_logger)
        assert backend.get_device_versions() == "ok"
        mock_gm.assert_called_once_with(os.path.join("tests", "mock_device", "lib"))


def test_get_modules_empty_path():
    """
    Sometimes a path to a device or bundle may be empty. Ensure, if this is the
    case, an empty dictionary is returned.
    """
    with mock.patch("circup.logger.warning") as mock_logger:
        backend = circup.DiskBackend("tests/mock_device", mock_logger)
        assert backend.get_modules("") == {}


def test_get_modules_that_are_files():
    """
    Check the expected dictionary containing metadata is returned given the
    (mocked) results of glob and open on file based Python modules.
    """
    path = "tests"  # mocked away in function.
    mods = [
        os.path.join("tests", "local_module.py"),
        os.path.join("tests", ".hidden_module.py"),
    ]
    with mock.patch("circup.shared.glob.glob", side_effect=[mods, [], []]), mock.patch(
        "circup.logger.warning"
    ) as mock_logger:
        backend = circup.DiskBackend("mock_device", mock_logger)
        result = backend.get_modules(path)
        assert len(result) == 1  # Hidden files are ignored.
        assert "local_module" in result
        assert result["local_module"]["path"] == os.path.join(
            "tests", "local_module.py"
        )
        assert result["local_module"]["__version__"] == "1.2.3"  # from fixture.
        repo = "https://github.com/adafruit/SomeLibrary.git"  # from fixture.
        assert result["local_module"]["__repo__"] == repo


def test_get_modules_that_are_directories():
    """
    Check the expected dictionary containing metadata is returned given the
    (mocked) results of glob and open, on directory based Python modules.
    """
    path = "tests"  # mocked away in function.
    mods = [
        os.path.join("tests", "dir_module", ""),
        os.path.join("tests", ".hidden_dir", ""),
    ]
    mod_files = ["tests/dir_module/my_module.py", "tests/dir_module/__init__.py"]
    with mock.patch(
        "circup.shared.glob.glob", side_effect=[[], [], mods, mod_files, []]
    ), mock.patch("circup.logger.warning") as mock_logger:
        backend = circup.DiskBackend("mock_device", mock_logger)
        result = backend.get_modules(path)
        assert len(result) == 1
        assert "dir_module" in result
        assert result["dir_module"]["path"] == os.path.join("tests", "dir_module", "")
        assert result["dir_module"]["__version__"] == "3.2.1"  # from fixture.
        repo = "https://github.com/adafruit/SomeModule.git"  # from fixture.
        assert result["dir_module"]["__repo__"] == repo


def test_get_modules_that_are_directories_with_no_metadata():
    """
    Check the expected dictionary containing just the path is returned given
    the (mocked) results of glob and open, on directory based Python modules.
    """
    path = "tests"  # mocked away in function.
    mods = [os.path.join("tests", "bad_module", "")]
    mod_files = ["tests/bad_module/my_module.py", "tests/bad_module/__init__.py"]
    with mock.patch(
        "circup.shared.glob.glob", side_effect=[[], [], mods, mod_files, []]
    ), mock.patch("circup.logger.warning") as mock_logger:
        backend = circup.DiskBackend("mock_device", mock_logger)
        result = backend.get_modules(path)
        assert len(result) == 1
        assert "bad_module" in result
        assert result["bad_module"]["path"] == os.path.join("tests", "bad_module", "")
        assert "__version__" not in result["bad_module"]
        assert "__repo__" not in result["bad_module"]


def test_ensure_latest_bundle_no_bundle_data():
    """
    If there's no BUNDLE_DATA file (containing previous current version of the
    bundle) then default to update.
    """
    with mock.patch("circup.bundle.Bundle.latest_tag", "12345"), mock.patch(
        "circup.os.path.isfile", return_value=False
    ), mock.patch("circup.command_utils.get_bundle") as mock_gb, mock.patch(
        "circup.command_utils.json"
    ) as mock_json, mock.patch(
        "circup.command_utils.open"
    ):
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        ensure_latest_bundle(bundle)
        mock_gb.assert_called_once_with(bundle, "12345")
        assert mock_json.dump.call_count == 1  # Current version saved to file.


def test_ensure_latest_bundle_bad_bundle_data():
    """
    If there's a BUNDLE_DATA file (containing previous current version of the
    bundle) but it has been corrupted (which has sometimes happened during
    manual testing) then default to update.
    """
    with mock.patch("circup.bundle.Bundle.latest_tag", "12345"), mock.patch(
        "circup.command_utils.open"
    ), mock.patch("circup.command_utils.get_bundle") as mock_gb, mock.patch(
        "builtins.open", mock.mock_open(read_data="}{INVALID_JSON")
    ), mock.patch(
        "circup.command_utils.json.dump"
    ), mock.patch(
        "circup.bundle.logger"
    ) as mock_logger:
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        ensure_latest_bundle(bundle)
        mock_gb.assert_called_once_with(bundle, "12345")

        assert mock_logger.error.call_count == 1
        assert mock_logger.exception.call_count == 1


def test_ensure_latest_bundle_to_update():
    """
    If the version found in the BUNDLE_DATA is out of date, then cause an
    update to the bundle.
    """
    with mock.patch("circup.bundle.Bundle.latest_tag", "54321"), mock.patch(
        "circup.command_utils.open"
    ), mock.patch("circup.command_utils.get_bundle") as mock_gb, mock.patch(
        "circup.command_utils.json"
    ) as mock_json:
        mock_json.load.return_value = {TEST_BUNDLE_NAME: "12345"}
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        ensure_latest_bundle(bundle)
        mock_gb.assert_called_once_with(bundle, "54321")
        assert mock_json.dump.call_count == 1  # Current version saved to file.


def test_ensure_latest_bundle_to_update_http_error():
    """
    If an HTTP error happens during a bundle update, print a friendly
    error message, and use existing bundle.
    """
    tags_data = {TEST_BUNDLE_NAME: "12345"}
    with mock.patch("circup.Bundle.latest_tag", "54321"), mock.patch(
        #         "circup.tags_data_load", return_value=tags_data
        #     ), mock.patch(
        "circup.os.path.isfile",
        return_value=True,
    ), mock.patch("circup.command_utils.open"), mock.patch(
        "circup.command_utils.get_bundle",
        side_effect=requests.exceptions.HTTPError("404"),
    ) as mock_gb, mock.patch(
        "circup.command_utils.json"
    ) as mock_json, mock.patch(
        "circup.click.secho"
    ) as mock_click:
        circup.Bundle.tags_data = dict()
        mock_json.load.return_value = tags_data
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        ensure_latest_bundle(bundle)
        mock_gb.assert_called_once_with(bundle, "54321")
        assert mock_json.dump.call_count == 0  # not saved.
        assert mock_click.call_count == 1  # friendly message.


def test_ensure_latest_bundle_no_update():
    """
    If the version found in the BUNDLE_DATA is NOT out of date, just log the
    fact and don't update.
    """
    with mock.patch("circup.bundle.Bundle.latest_tag", "12345"), mock.patch(
        "circup.command_utils.os.path.isdir", return_value=True
    ), mock.patch("circup.command_utils.open"), mock.patch(
        "circup.command_utils.get_bundle"
    ) as mock_gb, mock.patch(
        "circup.command_utils.os.path.isfile", return_value=True
    ), mock.patch(
        "circup.bundle.Bundle.current_tag", "12345"
    ), mock.patch(
        "circup.command_utils.logger"
    ) as mock_logger:

        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        ensure_latest_bundle(bundle)
        assert mock_gb.call_count == 0
        assert mock_logger.info.call_count == 2


def test_get_bundle():
    """
    Ensure the expected calls are made to get the referenced bundle and the
    result is unzipped to the expected location.
    """
    # All these mocks stop IO side effects and allow us to spy on the code to
    # ensure the expected calls are made with the correct values. Warning! Here
    # Be Dragons! (If in doubt, ask ntoll for details).
    mock_progress = mock.MagicMock()
    mock_progress().__enter__ = mock.MagicMock(return_value=["a", "b", "c"])
    mock_progress().__exit__ = mock.MagicMock()
    with mock.patch("circup.command_utils.requests") as mock_requests, mock.patch(
        "circup.click"
    ) as mock_click, mock.patch(
        "circup.command_utils.open", mock.mock_open()
    ) as mock_open, mock.patch(
        "circup.os.path.isdir", return_value=True
    ), mock.patch(
        "circup.command_utils.shutil"
    ) as mock_shutil, mock.patch(
        "circup.command_utils.zipfile"
    ) as mock_zipfile:
        mock_click.progressbar = mock_progress
        mock_requests.get().status_code = mock_requests.codes.ok
        mock_requests.get.reset_mock()
        tag = "12345"
        bundle = circup.Bundle(TEST_BUNDLE_NAME)
        get_bundle(bundle, tag)
        # how many bundles currently supported. i.e. 6x.mpy, 7x.mpy, py = 3 bundles
        _bundle_count = len(PLATFORMS)
        assert mock_requests.get.call_count == _bundle_count
        assert mock_open.call_count == _bundle_count
        assert mock_shutil.rmtree.call_count == _bundle_count
        assert mock_zipfile.ZipFile.call_count == _bundle_count
        assert mock_zipfile.ZipFile().__enter__().extractall.call_count == _bundle_count


def test_get_bundle_network_error():
    """
    Ensure that if there is a network related error when grabbing the bundle
    then the error is logged and re-raised for the HTTP status code.
    """
    with mock.patch("circup.command_utils.requests") as mock_requests, mock.patch(
        "circup.shared.tags_data_load", return_value=dict()
    ), mock.patch("circup.command_utils.logger") as mock_logger:
        # Force failure with != requests.codes.ok
        mock_requests.get().status_code = mock_requests.codes.BANG
        # Ensure raise_for_status actually raises an exception.
        mock_requests.get().raise_for_status.return_value = Exception("Bang!")
        mock_requests.get.reset_mock()
        tag = "12345"
        with pytest.raises(Exception) as ex:
            bundle = circup.Bundle(TEST_BUNDLE_NAME)
            get_bundle(bundle, tag)
            assert ex.value.args[0] == "Bang!"
        url = (
            "https://github.com/" + TEST_BUNDLE_NAME + "/releases/download"
            "/{tag}/adafruit-circuitpython-bundle-py-{tag}.zip".format(tag=tag)
        )
        mock_requests.get.assert_called_once_with(url, stream=True, timeout=mock.ANY)
        assert mock_logger.warning.call_count == 1
        mock_requests.get().raise_for_status.assert_called_once_with()


def test_show_command():
    """
    test_show_command
    """
    runner = CliRunner()
    test_bundle_modules = ["one.py", "two.py", "three.py"]
    with mock.patch(
        "circup.commands.get_bundle_versions", return_value=test_bundle_modules
    ):
        result = runner.invoke(circup.show)
    assert result.exit_code == 0
    assert all(m.replace(".py", "") in result.output for m in test_bundle_modules)


def test_show_match_command():
    """
    test_show_match_command
    """
    runner = CliRunner()
    test_bundle_modules = ["one.py", "two.py", "three.py"]
    with mock.patch(
        "circup.commands.get_bundle_versions", return_value=test_bundle_modules
    ):
        result = runner.invoke(circup.show, ["t"])
    assert result.exit_code == 0
    assert "one" not in result.output


def test_show_match_py_command():
    """
    Check that py does not match the .py extension in the module names
    """
    runner = CliRunner()
    test_bundle_modules = ["one.py", "two.py", "three.py"]
    with mock.patch(
        "circup.commands.get_bundle_versions", return_value=test_bundle_modules
    ):
        result = runner.invoke(circup.show, ["py"])
    assert result.exit_code == 0
    assert "0 shown" in result.output


def test_libraries_from_imports():
    """Ensure that various styles of import all work"""
    mod_names = [
        "adafruit_bus_device",
        "adafruit_button",
        "adafruit_display_shapes",
        "adafruit_display_text",
        "adafruit_esp32spi",
        "adafruit_hid",
        "adafruit_oauth2",
        "adafruit_requests",
        "adafruit_touchscreen",
    ]
    test_file = str(pathlib.Path(__file__).parent / "import_styles.py")

    result = circup.libraries_from_code_py(test_file, mod_names)
    assert result == [
        "adafruit_bus_device",
        "adafruit_button",
        "adafruit_esp32spi",
        "adafruit_hid",
    ]


def test_libraries_from_imports_bad():
    """Ensure that we catch an import error"""
    TEST_BUNDLE_MODULES = {"one.py": {}, "two.py": {}, "three.py": {}}
    runner = CliRunner()

    with mock.patch(
        "circup.commands.get_bundle_versions", return_value=TEST_BUNDLE_MODULES
    ):
        result = runner.invoke(
            circup.main,
            [
                "--path",
                "./tests/mock_device/",
                "install",
                "--auto-file",
                "./tests/bad_python.py",
            ],
        )
    assert result.exit_code == 2
