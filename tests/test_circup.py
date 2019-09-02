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
    mock_github = mock.MagicMock()  # Mock away the API shim.
    mock_repos = mock.MagicMock()  # Mock repository object.
    mock_source = mock.MagicMock()  # Mock source file.
    mock_github.get_repo.return_value = mock_repos
    mock_repos.get_contents.return_value = mock_source
    mock_source.decoded_content = b"# Python content of the file\n"
    with mock.patch("circup.github.Github", return_value=mock_github):
        result = circup.get_repos_file(repository, filename)
        assert result == mock_source.decoded_content.decode("utf-8")
        mock_github.get_repo.assert_called_once_with("adafruit/SomeLibrary")
        mock_repos.get_contents.assert_called_once_with(filename)


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
