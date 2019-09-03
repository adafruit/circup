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
import logging
import tempfile
import os
import sys
import ctypes
import glob
import re
import requests
import click
from datetime import datetime
from semver import compare, parse
from subprocess import check_output


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logfile = os.path.join(tempfile.gettempdir(), "circup.log")
logfile_handler = logging.FileHandler(logfile)
log_formatter = logging.Formatter("%(levelname)s: %(message)s")
logfile_handler.setFormatter(log_formatter)
logger.addHandler(logfile_handler)
click.echo("Logging to {}\n".format(logfile))


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
#: Flag to indicate if the command is being run in verbose mode.
VERBOSE = False


class Module:
    """
    Represents a CircuitPython module
    """

    def __init__(self, path, repo, local_version, remote_version):
        """
        :param str path: The path to the module on the connected CIRCUITPYTHON
        device.
        :param str repo: The URL of the Git repository for this module.
        :param str local_version: The semver value for the local copy.
        :param str remote_version: The semver value for the remote copy.
        """
        self.path = path
        self.file = os.path.basename(path)
        self.name = self.file[:-3]
        self.repo = repo
        self.local_version = local_version
        self.remote_version = remote_version
        logger.info(self)

    @property
    def outofdate(self):
        """
        Returns a boolean to indicate if this module is out of date.
        """
        if self.local_version and self.remote_version:
            try:
                return compare(self.local_version, self.remote_version) < 0
            except ValueError as ex:
                logger.warning(
                    "Module '{}' has incorrect semver value.".format(self.name)
                )
                logger.warning(ex)
        return True  # Assume out of date to try to update.

    @property
    def row(self):
        """
        Returns a tuple of items to display in a table row to show the module's
        name, local version and remote version.
        """
        loc = self.local_version if self.local_version else "unknown"
        rem = self.remote_version if self.remote_version else "unknown"
        return (self.name, loc, rem)

    def __repr__(self):
        """
        Helps with log files.
        """
        return repr(
            {
                "path": self.path,
                "file": self.file,
                "name": self.name,
                "repo": self.repo,
                "local_version": self.local_version,
                "remote_version": self.remote_version,
            }
        )


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
    logger.info("Found device: {}".format(device_dir))
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
    logger.info("Requesting remote file: {}".format(url))
    response = requests.get(url)
    logger.info(response)
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
    logger.info("Extracted metadata: {}".format(result))
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


def check_file_versions(filepath):
    """
    Given a path to an Adafruit module file, extract the metadata and check
    the latest version via GitHub. Return an instance of the Module class.

    :param str filepath: A path to an Adafruit module file.
    :return: An instance of the Module class containing metadata.
    """
    with open(filepath) as source_file:
        source_code = source_file.read()
    metadata = extract_metadata(source_code)
    module_file = os.path.basename(filepath)
    module_name = module_file[:-3]
    logger.info("Checking versions for module '{}'.".format(module_name))
    local_version = metadata.get("__version__", "")
    try:
        parse(local_version)
    except ValueError:
        local_version = None
    repo = metadata.get("__repo__", "unknown")
    remote_version = None
    if local_version and repo:
        remote_source = get_repos_file(repo, module_file)
        remote_metadata = extract_metadata(remote_source)
        remote_version = remote_metadata.get("__version__", "")
    return Module(filepath, repo, local_version, remote_version)


def check_module(module):
    """
    Shim. TODO: finish this.
    """
    return check_file_versions(module)


# ----------- CLI command definitions  ----------- #

# The following functions have IO side effects (for instance they emit to
# stdout). Ergo, these are not checked with unit tests. Most of the
# functionality they provide is provided by the functions above, which *are*
# tested. Most of the logic of the following functions is to prepare things for
# presentation to / interaction with the user.


@click.group()
@click.option(
    "--verbose", is_flag=True, help="Comprehensive logging is sent to stdout."
)
@click.version_option(
    version=__version__,
    prog_name="CircUp",
    message="%(prog)s, A CircuitPython module updater. Version %(version)s",
)
def main(verbose):  # pragma: no cover
    """
    A tool to manage and update libraries on a CircuitPython device.
    """
    if verbose:
        # Configure additional logging to stdout.
        global VERBOSE
        VERBOSE = True
        verbose_handler = logging.StreamHandler(sys.stdout)
        verbose_handler.setLevel(logging.INFO)
        verbose_handler.setFormatter(log_formatter)
        logger.addHandler(verbose_handler)
    logger.info("\n\n\nStarted {}".format(datetime.now()))


@main.command()
def freeze():  # pragma: no cover
    """
    Output details of all the modules found on the connected CIRCUITPYTHON
    device.
    """
    logger.info("Freeze")
    local_modules = find_modules()
    for module in local_modules:
        with open(module) as source_file:
            source_code = source_file.read()
            metadata = extract_metadata(source_code)
            module_file = os.path.basename(module)
            module_name = module_file[:-3]
            output = "{}=={}".format(
                module_name, metadata.get("__version__", "unknown")
            )
            click.echo(output)
            logger.info(output)


@main.command()
def list():  # pragma: no cover
    """
    Lists all out of date modules found on the connected CIRCUITPYTHON device.
    """
    logger.info("List")
    local_modules = find_modules()
    results = []
    click.echo("Found {} modules to check...\n".format(len(local_modules)))
    if VERBOSE:
        # No CLI effects, just allow logs to be emitted.
        for item in local_modules:
            module = check_module(item)
            if module.outofdate:
                results.append(module)
    else:
        # Use a progress bar instead.
        with click.progressbar(local_modules) as bar:
            for item in bar:
                module = check_module(item)
                if module.outofdate:
                    results.append(module)
    # Nice tabular display.
    data = [("Package", "Version", "Latest")]
    for item in results:
        data.append(item.row)
    col_width = [0, 0, 0]
    for row in data:
        for i, word in enumerate(row):
            col_width[i] = max(len(word) + 2, col_width[i])
    dashes = tuple(("-" * (width - 1) for width in col_width))
    data.insert(1, dashes)
    click.echo(
        "\nThe following packages are out of date or probably need "
        "an update.\n"
    )
    for row in data:
        output = ""
        for i in range(3):
            output += row[i].ljust(col_width[i])
        if not VERBOSE:
            click.echo(output)
        logger.info(output)
    click.echo("\n✨ 🍰 ✨")


@main.command()
def update():  # pragma: no cover
    """
    Checks for out-of-date modules on the connected CIRCUITPYTHON device, and
    prompts the user to confirm updating such modules.
    """
    logger.info("Update")
