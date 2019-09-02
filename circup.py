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
import requests
from semver import compare
from tqdm import tqdm
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
#: The regex used to extract ``__version__`` and ``__repo__`` assignments.
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
    """
    # Extract the repository's path for the GitHub API.
    owner, repos_name = repository.split("/")[-2:]
    repos_path = "{}/{}".format(owner, repos_name.replace(".git", ""))
    url = "https://raw.githubusercontent.com/{}/master/{}".format(
        repos_path, filename
    )
    response = requests.get(url)
    return response.text


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
    if "__builtins__" in result:
        del result["__builtins__"]  # Side effect of using exec, not needed.
    return result


def find_modules():
    """
    Returns a list of paths to ``.py`` modules in the ``lib`` directory on a
    connected Adafruit device.

    :return: A list of filpaths to modules in the lib directory on the device.
    """
    device_path = find_device()
    if device_path is None:
        raise IOError("Could not find a connected Adafruit device.")
    return glob.glob(os.path.join(device_path, "lib", "*.py"))


def check_version(filepath):
    """
    Given a path to an Adafruit module file, extract the metadata and check
    the latest version via GitHub. Return a tuple contining the current local
    version and the remote version::

        ("1.0.1", "1.2.0")

    If a version cannot be determined then ``None`` will be used instead.

    :param str filepath: A path to an Adafruit module file.
    :return: A tuple containing the current local and remote versions.
    """
    with open(filepath) as source_file:
        source_code = source_file.read()
    metadata = extract_metadata(source_code)
    module_file = os.path.basename(filepath)
    current_version = metadata.get("__version__")
    repo = metadata.get("__repo__")
    if current_version and repo:
        remote_source = get_repos_file(repo, module_file)
        remote_metadata = extract_metadata(remote_source)
        return (current_version, remote_metadata.get("__version__"))
    return (None, None)


def check_modules():  # pragma: no cover
    """
    Gathers modules from a connected Adafruit device. Checks each module for
    an update. Displays progress bar and tabular output of all modules that
    require updating.
    """
    local_modules = find_modules()
    results = {}
    problems = {}
    print("Found {} modules to check...\n".format(len(local_modules)))
    for module in tqdm(local_modules):
        module_name = os.path.basename(module)[:-3]
        version_state = check_version(module)
        if None in version_state:
            version_state = [
                "unknown" if x is None else x for x in version_state
            ]
            results[module_name] = version_state
        else:
            try:
                if compare(*version_state) < 0:
                    results[module_name] = version_state
            except ValueError:
                # Incorrect semver so log this.
                problems[module_name] = version_state
    # Nice tabular display.
    data = [("Package", "Version", "Latest")]
    for k, v in results.items():
        data.append((k, v[0], v[1]))
    col_width = [0, 0, 0]
    for row in data:
        for i, word in enumerate(row):
            col_width[i] = max(len(word) + 2, col_width[i])
    dashes = tuple(("-" * (width - 1) for width in col_width))
    data.insert(1, dashes)
    for row in data:
        output = ""
        for i in range(3):
            output += row[i].ljust(col_width[i])
        print(output)
    print("✨ 🍰 ✨")
    # TODO: Do something better than this...
    if problems:
        print("\n\n💥 💔 💥 Problem modules with incorrect semver...\n")
        print(problems.keys())


def main():  # pragma: no cover
    """
    TODO: Finish this properly. Just checking things work.
    """
    check_modules()
