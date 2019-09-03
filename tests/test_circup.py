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
from unittest import mock


def test_Module_init():
    """
    Ensure the Module instance is set up as expected and logged.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    local_version = "1.2.3"
    remote_version = "3.2.1"
    with mock.patch("circup.logger.info") as mock_logger:
        m = circup.Module(path, repo, local_version, remote_version)
        mock_logger.assert_called_once_with(m)
        assert m.path == path
        assert m.file == "module.py"
        assert m.name == "module"
        assert m.repo == repo
        assert m.local_version == local_version
        assert m.remote_version == remote_version


def test_Module_outofdate():
    """
    Ensure the ``outofdate`` property on a Module instance returns the expected
    boolean value to correctly indicate if the referenced module is, in fact,
    out of date.
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    m1 = circup.Module(path, repo, "1.2.3", "3.2.1")
    m2 = circup.Module(path, repo, "1.2.3", "1.2.3")
    m3 = circup.Module(path, repo, "3.2.1", "1.2.3")  # shouldn't happen!
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
    m = circup.Module(path, repo, "1.2.3", "hello")
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
    m = circup.Module(path, repo, "1.2.3", "")
    assert m.row == ("module", "1.2.3", "unknown")


def test_Module_repr():
    """
    """
    path = os.path.join("foo", "bar", "baz", "module.py")
    repo = "https://github.com/adafruit/SomeLibrary.git"
    local_version = "1.2.3"
    remote_version = "3.2.1"
    m = circup.Module(path, repo, local_version, remote_version)
    assert repr(m) == repr(
        {
            "path": path,
            "file": "module.py",
            "name": "module",
            "repo": repo,
            "local_version": local_version,
            "remote_version": remote_version,
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


def test_get_repos_file():
    """
    Ensure the repository path and filename are handled in such a way to create
    the expected and correct calls to the GitHub API.
    """
    repository = "https://github.com/adafruit/SomeLibrary.git"
    filename = "somelibrary.py"
    mock_response = mock.MagicMock()
    mock_response.text = "# Python content of the file\n"
    url = (
        "https://raw.githubusercontent.com/"
        "adafruit/SomeLibrary/master/somelibrary.py"
    )
    with mock.patch(
        "circup.requests.get", return_value=mock_response
    ) as mock_get:
        result = circup.get_repos_file(repository, filename)
        assert result == mock_response.text
        mock_get.assert_called_once_with(url)


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
    Ensure the result of the glob.glob call is returned, and the call is made
    with the expected path.
    """
    glob_result = ["module1.py", "module2.py"]
    with mock.patch("circup.find_device", return_value="foo"), mock.patch(
        "circup.glob.glob", return_value=glob_result
    ) as mock_glob:
        circup.find_modules()
        mock_glob.assert_called_once_with(os.path.join("foo", "lib", "*.py"))


def test_find_modules_no_device_connected():
    """
    Ensure an IOError is raised if there's no connected device which can be
    checked.
    """
    with mock.patch("circup.find_device", return_value=None), pytest.raises(
        IOError
    ) as ex:
        circup.find_modules()
        assert ex.value.args[0] == "Could find a connected Adafruit device."


def test_check_file_versions():
    """
    Ensure the expected calls are made for extracting both the local and
    remote version information for the referenced single file module. This
    should be returned as an instance of circup.Module.

    The local_module.py and remote_module.py "fixture" files contain versions:
    ``"1.2.3"`` and ``"2.3.4"`` respectively. The referenced GitHub repository
    is: ``"https://github.com/adafruit/SomeLibrary.git"``
    """
    filepath = "tests/local_module.py"
    with open("tests/remote_module.py") as remote_module:
        remote_source = remote_module.read()
    with mock.patch(
        "circup.get_repos_file", return_value=remote_source
    ) as mock_grf:
        result = circup.check_file_versions(filepath)
        assert isinstance(result, circup.Module)
        assert repr(result) == repr(
            circup.Module(
                filepath,
                "https://github.com/adafruit/SomeLibrary.git",
                "1.2.3",
                "2.3.4",
            )
        )
        mock_grf.assert_called_once_with(
            "https://github.com/adafruit/SomeLibrary.git", "local_module.py"
        )


def test_check_file_versions_unknown_version():
    """
    If no version information is available from the local file, the resulting
    circup.Module class has None set against the two potentail versions (local
    and remote).
    """
    filepath = "tests/local_module.py"
    with mock.patch("circup.extract_metadata", return_value={}):
        result = circup.check_file_versions(filepath)
        assert result.local_version is None
        assert result.remote_version is None


def test_check_module():
    """
    TODO: Finish this.
    """
    with mock.patch("circup.check_file_versions") as mock_cfv:
        circup.check_module("foo")
        mock_cfv.assert_called_once_with("foo")
