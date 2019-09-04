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
import circup
import ctypes
import pytest
import json
from unittest import mock


def test_Module_init():
    """
    Ensure the Module instance is set up as expected and logged.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    device_version = "1.2.3"
    bundle_version = "3.2.1"
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    with mock.patch("circup.logger.info") as mock_logger:
        m = circup.Module(
            path, repo, device_version, bundle_version, bundle_path
        )
        mock_logger.assert_called_once_with(m)
        assert m.path == path
        assert m.file == "module.py"
        assert m.name == "module"
        assert m.repo == repo
        assert m.device_version == device_version
        assert m.bundle_version == bundle_version
        assert m.bundle_path == bundle_path


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
    m = circup.Module(path, repo, device_version, bundle_version, bundle_path)
    assert m.row == ("module", "1.2.3", "unknown")


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
        mock_shutil.rmtree.assert_called_once_with(m.path)
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
    bundle_path = os.path.join("baz", "bar", "foo", "module.py")
    m = circup.Module(path, repo, device_version, bundle_version, bundle_path)
    assert repr(m) == repr(
        {
            "path": path,
            "file": "module.py",
            "name": "module",
            "repo": repo,
            "device_version": device_version,
            "bundle_version": bundle_version,
            "bundle_path": bundle_path,
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
    with mock.patch("os.name", "posix"), mock.patch(
        "circup.check_output", mock_check
    ):
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
        "https://github.com/adafruit/Adafruit_CircuitPython_Bundle"
        "/releases/latest"
    )
    with mock.patch("circup.requests.get", return_value=response) as mock_get:
        result = circup.get_latest_tag()
        assert result == "20190903"
        mock_get.assert_called_once_with(expected_url)


def test_extract_metadata():
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
    result = circup.extract_metadata(code)
    assert len(result) == 2
    assert result["__version__"] == "1.1.4"
    assert result["__repo__"] == "https://github.com/adafruit/SomeLibrary.git"


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
    ), mock.patch("circup.get_bundle_versions", return_value=bundle_modules):
        result = circup.find_modules()
    assert len(result) == 1
    assert result[0].name == "adafruit_74hc595"


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
        circup.find_modules()
        assert mock_click.echo.call_count == 1
        mock_exit.assert_called_once_with(1)


def test_get_bundle_versions():
    """
    Ensure get_modules is called with the path for the library bundle.
    """
    dirs = (("foo/bar/lib", "", ""),)
    with mock.patch("circup.ensure_latest_bundle"), mock.patch(
        "circup.os.walk", return_value=dirs
    ) as mock_walk, mock.patch(
        "circup.get_modules", return_value="ok"
    ) as mock_gm:
        assert circup.get_bundle_versions() == "ok"
        mock_walk.assert_called_once_with(circup.BUNDLE_DIR)
        mock_gm.assert_called_once_with("foo/bar/lib")


def test_get_device_versions():
    """
    Ensure get_modules is called with the path for the attached device.
    """
    with mock.patch(
        "circup.find_device", return_value="CIRCUITPYTHON"
    ), mock.patch("circup.get_modules", return_value="ok") as mock_gm:
        assert circup.get_device_versions() == "ok"
        mock_gm.assert_called_once_with(os.path.join("CIRCUITPYTHON", "lib"))


def test_get_device_versions_go_bang():
    """
    If it's not possible to find a connected device, ensure an IOError is
    raised.
    """
    with mock.patch("circup.find_device", return_value=None):
        with pytest.raises(IOError):
            circup.get_device_versions()


def test_get_modules():
    """
    Check the expected dictionary containing metadata is returned given the
    (mocked) results of glob and open.
    """
    path = "foo"
    mods = ["tests/local_module.py"]
    with mock.patch("circup.glob.glob", return_value=mods):
        result = circup.get_modules(path)
        assert len(result) == 1  # dict key is reused.


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


def test_ensure_latest_bundle_to_update():
    """
    If the version found in the BUNDLE_DATA is out of date, the cause an update
    to the bundle.
    """
    with mock.patch("circup.get_latest_tag", return_value="54321"), mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch("circup.get_bundle") as mock_gb, mock.patch(
        "circup.json"
    ) as mock_json:
        mock_json.load.return_value = {"tag": "12345"}
        circup.ensure_latest_bundle()
        mock_gb.assert_called_once_with("54321")
        assert mock_json.dump.call_count == 1  # Current version saved to file.


def test_ensure_latest_bundle_no_update():
    """
    If the version found in the BUNDLE_DATA is NOT out of date, just log the
    fact and don't update.
    """
    with mock.patch("circup.get_latest_tag", return_value="12345"), mock.patch(
        "circup.os.path.isfile", return_value=True
    ), mock.patch("circup.get_bundle") as mock_gb, mock.patch(
        "circup.json"
    ) as mock_json, mock.patch(
        "circup.logger"
    ) as mock_logger:
        mock_json.load.return_value = {"tag": "12345"}
        circup.ensure_latest_bundle()
        assert mock_gb.call_count == 0
        assert mock_logger.info.call_count == 2
