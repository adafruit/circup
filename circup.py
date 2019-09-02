"""
CircUp -- a utility to manage and update libraries on a CircuitPython device.

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
import glob
import re
import github
from subprocess import check_output


# IMPORTANT
# ---------
# Keep these metadata assignments simple and single-line. They are parsed
# somewhat naively by setup.py.
__title__ = "circup"
__description__ = "A tool to manage/update libraries on CircuitPython devices."
__version__ = "0.0.1"
__license__ = "MIT"
__url__ = "https://github.com/adafruit/circup"
__author__ = "Adafruit Industries"
__email__ = "ntoll@ntoll.org"


#: The unique USB vendor ID for Adafruit boards.
VENDOR_ID = 9114
#: The regex used to extract __version__ and __repo__ assignments within code.
DUNDER_ASSIGN_RE = re.compile(r"""^__\w+__\s*=\s*['"].+['"]$""")


def find_device():
    """
    Return the location on the filesystem for the connected Adafruit device.
    This is based upon how Mu discovers this information.

    :return: The path to the device on the local filesystem.
    """
    device_dir = None
    # Attempt to find the path on the filesystem that represents the plugged in
    # CIRCUITPY board.
    if os.name == "posix":
        # Linux / OSX
        for mount_command in ["mount", "/sbin/mount"]:
            try:
                mount_output = check_output(mount_command).splitlines()
                mounted_volumes = [x.split()[2] for x in mount_output]
                for volume in mounted_volumes:
                    if volume.endswith(b"CIRCUITPY"):
                        device_dir = volume.decode("utf-8")
            except FileNotFoundError:
                next
    elif os.name == "nt":
        # Windows

        def get_volume_name(disk_name):
            """
            Each disk or external device connected to windows has an attribute
            called "volume name". This function returns the volume name for the
            given disk/device.

            Based upon answer given here: http://stackoverflow.com/a/12056414
            """
            vol_name_buf = ctypes.create_unicode_buffer(1024)
            ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(disk_name),
                vol_name_buf,
                ctypes.sizeof(vol_name_buf),
                None,
                None,
                None,
                None,
                0,
            )
            return vol_name_buf.value

        #
        # In certain circumstances, volumes are allocated to USB
        # storage devices which cause a Windows popup to raise if their
        # volume contains no media. Wrapping the check in SetErrorMode
        # with SEM_FAILCRITICALERRORS (1) prevents this popup.
        #
        old_mode = ctypes.windll.kernel32.SetErrorMode(1)
        try:
            for disk in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                path = "{}:\\".format(disk)
                if (
                    os.path.exists(path)
                    and get_volume_name(path) == "CIRCUITPY"
                ):
                    device_dir = path
                    # Report only the FIRST device found.
                    break
        finally:
            ctypes.windll.kernel32.SetErrorMode(old_mode)
    else:
        # No support for unknown operating systems.
        raise NotImplementedError('OS "{}" not supported.'.format(os.name))
    return device_dir


def get_repos_file(repository, filename):
    """
    Given a GitHub repository and a file contained therein, either returns the
    content of that file, or raises an exception.

    :param str repository: The full path to the GitHub repository.
    :param str filename: The name of the file within the GitHub repository.
    :return: The content of the file.
    :raises ValueError: if the repository or filename is unknown.
    """
    # Extract the repository's path for the GitHub API.
    owner, repos_name = repository.split("/")[-2:]
    repos_path = "{}/{}".format(owner, repos_name.replace(".git", ""))
    # Reference the remote repository.
    gh = github.Github()
    repos = gh.get_repo(repos_path)
    # Return the content of filename.
    source = repos.get_contents(filename)
    return source.decoded_content.decode("utf-8")


def extract_metadata(code):
    """
    Given some Adafruit library code, return a dictionary containing metadata
    extracted from dunder attributes found therein.

    Such metadata assignments should be simple and single-line. For example::

        __version__ = "1.1.4"
        __repo__ = "https://github.com/adafruit/SomeLibrary.git"

    :param str code: The source code containing the version details.
    :return: The dunder based metadata found in the code as a dictionary.
    """
    result = {}
    lines = code.split("\n")
    for line in lines:
        if DUNDER_ASSIGN_RE.search(line):
            exec(line, result)
    del result["__builtins__"]  # Side effect of using exec, but not needed.
    return result


def find_modules():
    """
    Returns a list of paths to ``.py`` modules in the ``lib`` directory on a
    connected Adafruit device.
    """
    device_path = find_device()
    if device_path is None:
        raise IOError("Could not find a connected Adafruit device.")
    return glob.glob(os.path.join(device_path, "lib", "*.py"))


def main():  # pragma: no cover
    """
    TODO: Finish this. Just checking things work.
    """
    print(find_device())
