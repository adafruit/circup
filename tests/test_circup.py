# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
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
from unittest import mock


from click.testing import CliRunner
import pytest
import requests

import circup


def test_Module_init_file_module():
    """
    Ensure the Module instance is set up as expected and logged, is if for a
    single file Python module.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "3.2.1"
    with mock.patch("circup.logger.info") as mock_logger, mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch("circup.CPY_VERSION", "4.1.2"), mock.patch(
        "circup.os.walk", return_value=[["lib", "", ""]]
    ) as mock_walk:
        m = circup.Module(path, repo, device_version, bundle_version, False)
        mock_logger.assert_called_once_with(m)
        assert m.path == path
        assert m.file == "module.py"
        assert m.name == "module"
        assert m.repo == repo
        assert m.device_version == device_version
        assert m.bundle_version == bundle_version
        assert m.bundle_path == os.path.join("lib", m.file)
        assert m.mpy is False
        mock_walk.assert_called_once_with(circup.BUNDLE_DIR.format("py"))


def test_Module_init_directory_module():
    """
    Ensure the Module instance is set up as expected and logged, as if for a
    directory based Python module.
    """
    path = os.path.join("foo", "bar", "modulename", "")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "3.2.1"
    mpy = True
    with mock.patch("circup.logger.info") as mock_logger, mock.patch(
        "circup.os.path.isfile", return_value=False
    ), mock.patch("circup.CPY_VERSION", "4.1.2"), mock.patch(
        "circup.os.walk", return_value=[["lib", "", ""]]
    ) as mock_walk:
        m = circup.Module(path, repo, device_version, bundle_version, mpy)
        mock_logger.assert_called_once_with(m)
        assert m.path == path
        assert m.file is None
        assert m.name == "modulename"
        assert m.repo == repo
        assert m.device_version == device_version
        assert m.bundle_version == bundle_version
        assert m.bundle_path == os.path.join("lib", m.name)
        assert m.mpy is True
        mock_walk.assert_called_once_with(circup.BUNDLE_DIR.format("4mpy"))


def test_Module_outofdate():
    """
    Ensure the ``outofdate`` property on a Module instance returns the expected
    boolean value to correctly indicate if the referenced module is, in fact,
    out of date.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    m1 = circup.Module(path, repo, "1.2.3", "3.2.1", bundle_path)
    m2 = circup.Module(path, repo, "1.2.3", "1.2.3", bundle_path)
    # shouldn't happen!
    m3 = circup.Module(path, repo, "3.2.1", "1.2.3", bundle_path)
    assert m1.outofdate is True
    assert m2.outofdate is False
    assert m3.outofdate is False


def test_Module_outofdate_bad_versions():
    """
    Sometimes, the version is not a valid semver value. In this case, the
    ``outofdate`` property assumes the module should be updated (to correct
    this problem). Such a problem should be logged.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "hello"
    bundle_version = "3.2.1"
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    m = circup.Module(path, repo, device_version, bundle_version, bundle_path)
    with mock.patch("circup.logger.warning") as mock_logger:
        assert m.outofdate is True
        assert mock_logger.call_count == 2


def test_Module_major_update_bad_versions():
    """
    Sometimes, the version is not a valid semver value. In this case, the
    ``major_update`` property assumes the module is a major update, so as not
    to block the user from getting the latest update.
    Such a problem should be logged.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "version-3"
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    m = circup.Module(path, repo, device_version, bundle_version, bundle_path)
    with mock.patch("circup.logger.warning") as mock_logger:
        assert m.major_update is True
        assert mock_logger.call_count == 2


def test_Module_row():
    """
    Ensure the tuple contains the expected items to be correctly displayed in
    a table of version-related results.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = None
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    with mock.patch("circup.os.path.isfile", return_value=True):
        m = circup.Module(path, repo, device_version, bundle_version, bundle_path)
    # print(m.__dict__)
    # print(m.row)
    assert m.row == ("module", "1.2.3", "unknown", "True")


def test_Module_update_dir():
    """
    Ensure if the module is a directory, the expected actions take place to
    update the module on the connected device.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = None
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    m = circup.Module(path, repo, device_version, bundle_version, bundle_path)
    with mock.patch("circup.shutil") as mock_shutil, mock.patch(
        "circup.os.path.isdir", return_value=True
    ):
        m.update()
        mock_shutil.rmtree.assert_called_once_with(m.path, ignore_errors=True)
        mock_shutil.copytree.assert_called_once_with(m.bundle_path, m.path)


def test_Module_update_file():
    """
    Ensure if the module is a file, the expected actions take place to
    update the module on the connected device.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = None
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    m = circup.Module(path, repo, device_version, bundle_version, bundle_path)
    with mock.patch("circup.shutil") as mock_shutil, mock.patch(
        "circup.os.remove"
    ) as mock_remove, mock.patch("circup.os.path.isdir", return_value=False):
        m.update()
        mock_remove.assert_called_once_with(m.path)
        mock_shutil.copyfile.assert_called_once_with(m.bundle_path, m.path)


def test_Module_repr():
    """
    Ensure the repr(dict) is returned (helps when logging).
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "3.2.1"
    with mock.patch("circup.os.path.isfile", return_value=True), mock.patch(
        "circup.CPY_VERSION", "4.1.2"
    ), mock.patch("circup.os.walk", return_value=[["lib", "", ""]]):
        m = circup.Module(path, repo, device_version, bundle_version, False)
    assert repr(m) == repr(
        {
            "path": path,
            "file": "module.py",
            "name": "module",
            "repo": repo,
            "device_version": device_version,
            "bundle_version": bundle_version,
            "bundle_path": os.path.join("lib", m.file),
            "mpy": False,
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
            with mock.patch("circup.check_output", return_value=fixture):
                assert circup.find_device() == "/media/ntoll/CIRCUITPY"


def test_find_device_posix_no_mount_command():
    """
    When the user doesn't have administrative privileges on OSX then the mount
    command isn't on their path. In which case, check circup uses the more
    explicit /sbin/mount instead.
    """
    with open("tests/mount_exists.txt", "rb") as fixture_file:
        fixture = fixture_file.read()
    mock_check = mock.MagicMock(side_effect=[FileNotFoundError, fixture])
    with mock.patch("os.name", "posix"), mock.patch("circup.check_output", mock_check):
        assert circup.find_device() == "/media/ntoll/CIRCUITPY"
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
            "circup.check_output", return_value=fixture
        ):
            assert circup.find_device() is None


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
        assert circup.find_device() == "A:\\"


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
        assert circup.find_device() is None


def test_find_device_unknown_os():
    """
    Raises a NotImplementedError if the host OS is not supported.
    """
    with mock.patch("os.name", "foo"):
        with pytest.raises(NotImplementedError) as ex:
            circup.find_device()
    assert ex.value.args[0] == 'OS "foo" not supported.'


def test_get_latest_tag():
    """
    Ensure the expected tag value is extracted from the returned URL (resulting
    from a call to the expected endpoint).
    """
    response = mock.MagicMock()
    response.url = (
        "https://github.com/adafruit"
        "/Adafruit_CircuitPython_Bundle/releases/tag/20190903"
    )
    expected_url = (
        "https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/latest"
    )
    with mock.patch("circup.requests.get", return_value=response) as mock_get:
        result = circup.get_latest_tag()
        assert result == "20190903"
        mock_get.assert_called_once_with(expected_url)


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
    with mock.patch("builtins.open", mock.mock_open(read_data=code)) as mock_open:
        result = circup.extract_metadata(path)
        mock_open.assert_called_once_with(path, encoding="utf-8")
    assert len(result) == 3
    assert result["__version__"] == "1.1.4"
    assert result["__repo__"] == "https://github.com/adafruit/SomeLibrary.git"
    assert result["mpy"] is False


def test_extract_metadata_byte_code():
    """
    Ensure the __version__ is correctly extracted from the bytecode ".mpy"
    file. Version in test_module is 0.9.2
    """
    result = circup.extract_metadata("tests/test_module.mpy")
    assert result["__version__"] == "0.9.2"
    assert result["mpy"] is True


def test_find_modules():
    """
    Ensure that the expected list of Module instances is returned given the
    metadata dictionary fixtures for device and bundle modules.
    """
    with open("tests/device.json") as f:
        device_modules = json.load(f)
    with open("tests/bundle.json") as f:
        bundle_modules = json.load(f)
    with mock.patch(
        "circup.get_device_versions", return_value=device_modules
    ), mock.patch(
        "circup.get_bundle_versions", return_value=bundle_modules
    ), mock.patch(
        "circup.os.path.isfile", return_value=True
    ):
        result = circup.find_modules("")
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
        "circup.get_device_versions", side_effect=Exception("BANG!")
    ), mock.patch("circup.click") as mock_click, mock.patch(
        "circup.sys.exit"
    ) as mock_exit:
        circup.find_modules("")
        assert mock_click.echo.call_count == 1
        mock_exit.assert_called_once_with(1)


def test_get_bundle_versions():
    """
    Ensure get_modules is called with the path for the library bundle.
    """
    dirs = (("foo/bar/lib", "", ""),)
    with mock.patch("circup.ensure_latest_bundle"), mock.patch(
        "circup.os.walk", return_value=dirs
    ) as mock_walk, mock.patch("circup.get_modules", return_value="ok") as mock_gm:
        assert circup.get_bundle_versions() == "ok"
        mock_walk.assert_called_once_with(circup.BUNDLE_DIR.format("py"))
        mock_gm.assert_called_once_with("foo/bar/lib")


def test_get_circuitpython_version():
    """
    Given valid content of a boot_out.txt file on a connected device, return
    the version number of CircuitPython running on the board.
    """
    data = (
        "Adafruit CircuitPython 4.1.0 on 2019-08-02; "
        "Adafruit CircuitPlayground Express with samd21g18"
    )
    mock_open = mock.mock_open(read_data=data)
    device_path = "device"
    with mock.patch("builtins.open", mock_open):
        assert circup.get_circuitpython_version(device_path) == "4.1.0"
        mock_open.assert_called_once_with(os.path.join(device_path, "boot_out.txt"))


def test_get_device_versions():
    """
    Ensure get_modules is called with the path for the attached device.
    """
    with mock.patch("circup.get_modules", return_value="ok") as mock_gm:
        assert circup.get_device_versions("TESTDIR") == "ok"
        mock_gm.assert_called_once_with(os.path.join("TESTDIR", "lib"))


def test_get_modules_empty_path():
    """
    Sometimes a path to a device or bundle may be empty. Ensure, if this is the
    case, an empty dictionary is returned.
    """
    assert circup.get_modules("") == {}


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
    with mock.patch("circup.glob.glob", side_effect=[mods, [], []]):
        result = circup.get_modules(path)
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
    with mock.patch("circup.glob.glob", side_effect=[[], [], mods, mod_files, []]):
        result = circup.get_modules(path)
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
    with mock.patch("circup.glob.glob", side_effect=[[], [], mods, mod_files, []]):
        result = circup.get_modules(path)
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
    with mock.patch("circup.get_latest_tag", return_value="12345"), mock.patch(
        "circup.os.path.isfile", return_value=False
    ), mock.patch("circup.get_bundle") as mock_gb, mock.patch(
        "circup.json"
    ) as mock_json:
        circup.ensure_latest_bundle()
        mock_gb.assert_called_once_with("12345")
        assert mock_json.dump.call_count == 1  # Current version saved to file.


def test_ensure_latest_bundle_bad_bundle_data():
    """
    If there's a BUNDLE_DATA file (containing previous current version of the
    bundle) but it has been corrupted (which has sometimes happened during
    manual testing) then default to update.
    """
    with mock.patch("circup.get_latest_tag", return_value="12345"), mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch("circup.open"), mock.patch(
        "circup.get_bundle"
    ) as mock_gb, mock.patch(
        "circup.json.load", side_effect=json.decoder.JSONDecodeError("BANG!", "doc", 1)
    ), mock.patch(
        "circup.json.dump"
    ), mock.patch(
        "circup.logger"
    ) as mock_logger:
        circup.ensure_latest_bundle()
        mock_gb.assert_called_once_with("12345")
        assert mock_logger.error.call_count == 1
        assert mock_logger.exception.call_count == 1


def test_ensure_latest_bundle_to_update():
    """
    If the version found in the BUNDLE_DATA is out of date, then cause an
    update to the bundle.
    """
    with mock.patch("circup.get_latest_tag", return_value="54321"), mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch("circup.open"), mock.patch(
        "circup.get_bundle"
    ) as mock_gb, mock.patch(
        "circup.json"
    ) as mock_json:
        mock_json.load.return_value = {"tag": "12345"}
        circup.ensure_latest_bundle()
        mock_gb.assert_called_once_with("54321")
        assert mock_json.dump.call_count == 1  # Current version saved to file.


def test_ensure_latest_bundle_to_update_http_error():
    # pylint: disable=pointless-statement
    # 2nd to last line is deemed pointless.
    # Don't understand but for now this is an accpetable workaround
    # Tracking issue will be opened.
    """
    If an HTTP error happens during a bundle update, print a friendly
    error message and exit 1.
    """
    with mock.patch("circup.get_latest_tag", return_value="54321"), mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch("circup.open"), mock.patch(
        "circup.get_bundle", side_effect=requests.exceptions.HTTPError("404")
    ) as mock_gb, mock.patch(
        "circup.json"
    ) as mock_json, mock.patch(
        "circup.click.secho"
    ) as mock_click, mock.patch(
        "circup.sys.exit"
    ) as mock_exit:
        mock_json.load.return_value = {"tag": "12345"}
        circup.ensure_latest_bundle()
        mock_gb.assert_called_once_with("54321")
        assert mock_json.dump.call_count == 0  # not saved.
        mock_click.call_count == 1  # friendly message.
        mock_exit.assert_called_once_with(1)  # exit 1.


def test_ensure_latest_bundle_no_update():
    """
    If the version found in the BUNDLE_DATA is NOT out of date, just log the
    fact and don't update.
    """
    with mock.patch("circup.get_latest_tag", return_value="12345"), mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch("circup.open"), mock.patch(
        "circup.get_bundle"
    ) as mock_gb, mock.patch(
        "circup.json"
    ) as mock_json, mock.patch(
        "circup.logger"
    ) as mock_logger:
        mock_json.load.return_value = {"tag": "12345"}
        circup.ensure_latest_bundle()
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
    with mock.patch("circup.requests") as mock_requests, mock.patch(
        "circup.click"
    ) as mock_click, mock.patch(
        "circup.open", mock.mock_open()
    ) as mock_open, mock.patch(
        "circup.os.path.isdir", return_value=True
    ), mock.patch(
        "circup.shutil"
    ) as mock_shutil, mock.patch(
        "circup.zipfile"
    ) as mock_zipfile:
        mock_click.progressbar = mock_progress
        mock_requests.get().status_code = mock_requests.codes.ok
        mock_requests.get.reset_mock()
        tag = "12345"
        circup.get_bundle(tag)
        assert mock_requests.get.call_count == 2
        assert mock_open.call_count == 2
        assert mock_shutil.rmtree.call_count == 2
        assert mock_zipfile.ZipFile.call_count == 2
        assert mock_zipfile.ZipFile().__enter__().extractall.call_count == 2


def test_get_bundle_network_error():
    """
    Ensure that if there is a network related error when grabbing the bundle
    then the error is logged and re-raised for the HTTP status code.
    """
    with mock.patch("circup.requests") as mock_requests, mock.patch(
        "circup.logger"
    ) as mock_logger:
        # Force failure with != requests.codes.ok
        mock_requests.get().status_code = mock_requests.codes.BANG
        # Ensure raise_for_status actually raises an exception.
        mock_requests.get().raise_for_status.return_value = Exception("Bang!")
        mock_requests.get.reset_mock()
        tag = "12345"
        with pytest.raises(Exception) as ex:
            circup.get_bundle(tag)
            assert ex.value.args[0] == "Bang!"
        url = (
            "https://github.com/adafruit/Adafruit_CircuitPython_Bundle"
            "/releases/download"
            "/{tag}/adafruit-circuitpython-bundle-py-{tag}.zip".format(tag=tag)
        )
        mock_requests.get.assert_called_once_with(url, stream=True)
        assert mock_logger.warning.call_count == 1
        mock_requests.get().raise_for_status.assert_called_once_with()


def test_show_command():
    """
    test_show_command
    """
    runner = CliRunner()
    TEST_BUNDLE_MODULES = ["one.py", "two.py", "three.py"]
    with mock.patch("circup.get_bundle_versions", return_value=TEST_BUNDLE_MODULES):
        result = runner.invoke(circup.show)
    assert result.exit_code == 0
    assert all([m.replace(".py", "") in result.output for m in TEST_BUNDLE_MODULES])


def test_show_match_command():
    """
    test_show_match_command
    """
    runner = CliRunner()
    TEST_BUNDLE_MODULES = ["one.py", "two.py", "three.py"]
    with mock.patch("circup.get_bundle_versions", return_value=TEST_BUNDLE_MODULES):
        result = runner.invoke(circup.show, ["t"])
    assert result.exit_code == 0
    assert "one" not in result.output


def test_show_match_py_command():
    """
    Check that py does not match the .py extention in the module names
    """
    runner = CliRunner()
    TEST_BUNDLE_MODULES = ["one.py", "two.py", "three.py"]
    with mock.patch("circup.get_bundle_versions", return_value=TEST_BUNDLE_MODULES):
        result = runner.invoke(circup.show, ["py"])
    assert result.exit_code == 0
    assert "0 shown" in result.output
