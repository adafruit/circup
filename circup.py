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
import appdirs
import os
import sys
import ctypes
import glob
import re
import requests
import click
import shutil
import json
import zipfile
from datetime import datetime
from semver import compare
from subprocess import check_output


# Useful constants.
#: The unique USB vendor ID for Adafruit boards.
VENDOR_ID = 9114
#: The regex used to extract ``__version__`` and ``__repo__`` assignments.
DUNDER_ASSIGN_RE = re.compile(r"""^__\w+__\s*=\s*['"].+['"]$""")
#: Flag to indicate if the command is being run in verbose mode.
VERBOSE = False
#: The location of data files used by circup (following OS conventions).
DATA_DIR = appdirs.user_data_dir(appname="circup", appauthor="adafruit")
#: The path to the JSON file containing the metadata about the current bundle.
BUNDLE_DATA = os.path.join(DATA_DIR, "circup.json")
#: The path to the zip file containing the current library bundle.
BUNDLE_ZIP = os.path.join(DATA_DIR, "adafruit-circuitpython-bundle-py.zip")
#: The path to the directory into which the current bundle is unzipped.
BUNDLE_DIR = os.path.join(DATA_DIR, "adafruit_circuitpython_bundle")
#: The directory containing the utility's log file.
LOG_DIR = appdirs.user_log_dir(appname="circup", appauthor="adafruit")
#: The location of the log file for the utility.
LOGFILE = os.path.join(LOG_DIR, "circup.log")


# Ensure DATA_DIR / LOG_DIR related directories and files exist.
if not os.path.exists(DATA_DIR):  # pragma: no cover
    os.makedirs(DATA_DIR)
if not os.path.exists(LOG_DIR):  # pragma: no cover
    os.makedirs(LOG_DIR)


# Setup logging.
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logfile_handler = logging.FileHandler(LOGFILE)
log_formatter = logging.Formatter("%(levelname)s: %(message)s")
logfile_handler.setFormatter(log_formatter)
logger.addHandler(logfile_handler)


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


class Module:
    """
    Represents a CircuitPython module.
    """

    def __init__(
        self, path, repo, device_version, bundle_version, bundle_path
    ):
        """
        The ``self.file`` and ``self.name`` attributes are constructed from
        the ``path`` value. If the path is to a directory based module, the
        resulting self.file value will be None, and the name will be the
        basename of the directory path.

        :param str path: The path to the module on the connected CIRCUITPYTHON
        device.
        :param str repo: The URL of the Git repository for this module.
        :param str device_version: The semver value for the version on device.
        :param str bundle_version: The semver value for the version in bundle.
        :param str bundle_path: The path to the bundle version of the module.
        """
        self.path = path
        if os.path.isfile(self.path):
            # Single file module.
            self.file = os.path.basename(path)
            self.name = self.file[:-3]
        else:
            # Directory based module.
            self.file = None
            self.name = os.path.basename(os.path.dirname(self.path))
        self.repo = repo
        self.device_version = device_version
        self.bundle_version = bundle_version
        self.bundle_path = bundle_path
        logger.info(self)

    @property
    def outofdate(self):
        """
        Returns a boolean to indicate if this module is out of date.

        :return: Truthy indication if the module is out of date.
        """
        if self.device_version and self.bundle_version:
            try:
                return compare(self.device_version, self.bundle_version) < 0
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

        :return: A tuple containing the module's name, version on the connected
                 device and version in the latest bundle.
        """
        loc = self.device_version if self.device_version else "unknown"
        rem = self.bundle_version if self.bundle_version else "unknown"
        return (self.name, loc, rem)

    def update(self):
        """
        Delete the module on the device, then copy the module from the bundle
        back onto the device.

        The caller is expected to handle any exceptions raised.
        """
        if os.path.isdir(self.path):
            # Delete and copy the directory.
            shutil.rmtree(self.path)
            shutil.copytree(self.bundle_path, self.path)
        else:
            # Delete and copy file.
            os.remove(self.path)
            shutil.copyfile(self.bundle_path, self.path)

    def __repr__(self):
        """
        Helps with log files.

        :return: A repr of a dictionary containing the module's metadata.
        """
        return repr(
            {
                "path": self.path,
                "file": self.file,
                "name": self.name,
                "repo": self.repo,
                "device_version": self.device_version,
                "bundle_version": self.bundle_version,
                "bundle_path": self.bundle_path,
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


def get_latest_tag():
    """
    Find the value of the latest tag for the Adafruit CircuitPython library
    bundle.

    :return: The most recent tag value for the project.
    """
    url = (
        "https://github.com/adafruit/Adafruit_CircuitPython_Bundle"
        "/releases/latest"
    )
    logger.info("Requesting tag information: {}".format(url))
    response = requests.get(url)
    logger.info("Response url: {}".format(response.url))
    tag = response.url.rsplit("/", 1)[-1]
    logger.info("Tag: '{}'".format(tag))
    return tag


def extract_metadata(code):
    """
    Given some Adafruit library code, return a dictionary containing metadata
    extracted from dunder attributes found therein.

    Such metadata assignments should be simple and single-line. For example::

        __version__ = "1.1.4"
        __repo__ = "https://github.com/adafruit/SomeLibrary.git"

    :param str code: The source code containing the metadata.
    :return: The dunder based metadata found in the code as a dictionary.
    """
    result = {}
    lines = code.split("\n")
    for line in lines:
        if DUNDER_ASSIGN_RE.search(line):
            exec(line, result)
    if "__builtins__" in result:
        del result["__builtins__"]  # Side effect of using exec, not needed.
    if result:
        logger.info("Extracted metadata: {}".format(result))
    return result


def find_modules():
    """
    Extracts metadata from the connected device and available bundle and
    returns this as a list of Module instances representing the modules on the
    device.

    :return: A list of Module instances describing the current state of the
             modules on the connected device.
    """
    try:
        device_modules = get_device_versions()
        bundle_modules = get_bundle_versions()
        result = []
        for name, device_metadata in device_modules.items():
            if name in bundle_modules:
                bundle_metadata = bundle_modules[name]
                path = device_metadata["path"]
                repo = device_metadata.get("__repo__")
                device_version = device_metadata.get("__version__")
                bundle_version = bundle_metadata.get("__version__")
                bundle_path = bundle_metadata["path"]
                result.append(
                    Module(
                        path, repo, device_version, bundle_version, bundle_path
                    )
                )
        return result
    except Exception as ex:
        # If it's not possible to get the device and bundle metadata, bail out
        # with a friendly message and indication of what's gone wrong.
        logger.exception(ex)
        click.echo("There was a problem: {}".format(ex))
        sys.exit(1)


def get_bundle_versions():
    """
    Returns a dictionary of metadata from modules in the latest known release
    of the library bundle.

    :return: A dictionary of metadata about the modules available in the
             library bundle.
    """
    ensure_latest_bundle()
    for path, subdirs, files in os.walk(BUNDLE_DIR):
        if path.endswith("lib"):
            break
    return get_modules(path)


def get_device_versions():
    """
    Returns a dictionary of metadata from modules on the connected device.

    :return: A dictionary of metadata about the modules available on the
             connected device.
    """
    device_path = find_device()
    if device_path is None:
        raise IOError("Could not find a connected Adafruit device.")
    return get_modules(os.path.join(device_path, "lib"))


def get_modules(path):
    """
    Get a dictionary containing metadata about all the Python modules found in
    the referenced path.

    :param str path: The directory in which to find modules.
    :return: A dictionary containing metadata about the found modules.
    """
    single_file_mods = glob.glob(os.path.join(path, "*.py"))
    directory_mods = glob.glob(os.path.join(path, "*", ""))
    result = {}
    for sfm in single_file_mods:
        with open(sfm, encoding="utf-8") as source_file:
            source_code = source_file.read()
            metadata = extract_metadata(source_code)
            metadata["path"] = sfm
            result[os.path.basename(sfm)] = metadata
    for dm in directory_mods:
        name = os.path.basename(os.path.dirname(dm))
        metadata = {}
        for source in glob.glob(os.path.join(dm, "*.py")):
            with open(source, encoding="utf-8") as source_file:
                source_code = source_file.read()
                metadata = extract_metadata(source_code)
            if "__version__" in metadata:
                metadata["path"] = dm
                result[name] = metadata
                break
        else:
            # No version metadata found.
            result[name] = {"path": dm}
    return result


def ensure_latest_bundle():
    """
    Ensure that there's a copy of the latest library bundle available so circup
    can check the metadata contained therein.
    """
    logger.info("Checking for library updates.")
    tag = get_latest_tag()
    old_tag = "0"
    if os.path.isfile(BUNDLE_DATA):
        with open(BUNDLE_DATA, encoding="utf-8") as data:
            try:
                old_tag = json.load(data)["tag"]
            except json.decoder.JSONDecodeError as ex:
                # Sometimes (why?) the JSON file becomes corrupt. In which case
                # log it and carry on as if setting up for first time.
                logger.error("Could not parse {}".format(BUNDLE_DATA))
                logger.exception(ex)
    if tag > old_tag:
        logger.info("New version available ({}).".format(tag))
        get_bundle(tag)
        with open(BUNDLE_DATA, "w", encoding="utf-8") as data:
            json.dump({"tag": tag}, data)
    else:
        logger.info("Current library bundle up to date ({}).".format(tag))


def get_bundle(tag):
    """
    Downloads and extracts the version of the bundle with the referenced tag.

    :param str tag: The GIT tag to use to download the bundle.
    :return: The location of the resulting zip file in a temporary location on
             the local filesystem.
    """
    url = (
        "https://github.com/adafruit/Adafruit_CircuitPython_Bundle"
        "/releases/download"
        "/{tag}/adafruit-circuitpython-bundle-py-{tag}.zip".format(tag=tag)
    )
    logger.info("Downloading bundle: {}".format(url))
    r = requests.get(url, stream=True)
    if r.status_code != requests.codes.ok:
        logger.warning("Unable to connect to {}".format(url))
        r.raise_for_status()
    total_size = int(r.headers.get("Content-Length"))
    click.echo("Downloading latest version information.\n")
    with click.progressbar(
        r.iter_content(1024), length=total_size
    ) as bar, open(BUNDLE_ZIP, "wb") as f:
        for chunk in bar:
            f.write(chunk)
            bar.update(len(chunk))
    logger.info("Saved to {}".format(BUNDLE_ZIP))
    if os.path.isdir(BUNDLE_DIR):
        shutil.rmtree(BUNDLE_DIR)
    with zipfile.ZipFile(BUNDLE_ZIP, "r") as zfile:
        zfile.extractall(BUNDLE_DIR)
    click.echo("\nOK\n")


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
        click.echo("Logging to {}\n".format(LOGFILE))
    logger.info("### Started {}".format(datetime.now()))


@main.command()
def freeze():  # pragma: no cover
    """
    Output details of all the modules found on the connected CIRCUITPYTHON
    device.
    """
    logger.info("Freeze")
    modules = find_modules()
    if modules:
        for module in modules:
            output = "{}=={}".format(module.name, module.device_version)
            click.echo(output)
            logger.info(output)
    else:
        click.echo("No modules found on the device.")


@main.command()
def list():  # pragma: no cover
    """
    Lists all out of date modules found on the connected CIRCUITPYTHON device.
    """
    logger.info("List")
    # Grab out of date modules.
    data = [("Module", "Version", "Latest")]
    modules = [m.row for m in find_modules() if m.outofdate]
    if modules:
        data += modules
        # Nice tabular display.
        col_width = [0, 0, 0]
        for row in data:
            for i, word in enumerate(row):
                col_width[i] = max(len(word) + 2, col_width[i])
        dashes = tuple(("-" * (width - 1) for width in col_width))
        data.insert(1, dashes)
        click.echo(
            "The following modules are out of date or probably need "
            "an update.\n"
        )
        for row in data:
            output = ""
            for i in range(3):
                output += row[i].ljust(col_width[i])
            if not VERBOSE:
                click.echo(output)
            logger.info(output)
    else:
        click.echo("All modules found on the device are up to date.")


@main.command()
def update():  # pragma: no cover
    """
    Checks for out-of-date modules on the connected CIRCUITPYTHON device, and
    prompts the user to confirm updating such modules.
    """
    logger.info("Update")
    # Grab out of date modules.
    modules = [m for m in find_modules() if m.outofdate]
    if modules:
        click.echo("Found {} module[s] needing update.".format(len(modules)))
        click.echo("Please indicate which modules you wish to update:\n")
        for module in modules:
            if click.confirm("Update '{}'?".format(module.name)):
                try:
                    module.update()
                    click.echo("OK")
                except Exception as ex:
                    logger.exception(ex)
                    click.echo(
                        "Something went wrong, {} (check the logs)".format(
                            str(ex)
                        )
                    )
    else:
        click.echo("None of the modules found on the device need an update.")


@main.command()
def show():  # pragma: no cover
    """
    Show a list of available modules in the bundle. These are modules which
    *could* be installed on the device.
    """
    available_modules = get_bundle_versions()
    module_names = sorted([m.replace(".py", "") for m in available_modules])
    click.echo(", ".join(module_names))
    click.echo("{} packages.".format(len(module_names)))


@main.command()
@click.argument("name")
def install(name):  # pragma: no cover
    """
    Install a named module onto the device. This is a very naive / simple
    hacky proof of concept.

    TODO: Work out how to specify / handle dependencies (if at all), ensure
    there's enough space on the device, work out the version of CircuitPython
    on the device in order to copy the appropriate .mpy versions too. ;-)
    """
    available_modules = get_bundle_versions()
    # Normalize user input.
    name = name.lower()
    mod_names = {}
    for module, metadata in available_modules.items():
        mod_names[module.replace(".py", "").lower()] = metadata
    if name in mod_names:
        device_path = find_device()
        if device_path is None:
            raise IOError("Could not find a connected Adafruit device.")
        library_path = os.path.join(device_path, "lib")
        metadata = mod_names[name]
        source_path = metadata["path"]
        if os.path.isdir(source_path):
            target = os.path.basename(os.path.dirname(source_path))
            target_path = os.path.join(library_path, target)
            # Copy the directory.
            shutil.copytree(source_path, target_path)
        else:
            target = os.path.basename(source_path)
            target_path = os.path.join(library_path, target)
            # Copy file.
            shutil.copyfile(source_path, target_path)
        print("OK")
    else:
        click.echo("Unknown module named, '{}'.".format(name))
