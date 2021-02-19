# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
CircUp -- a utility to manage and update libraries on a CircuitPython device.
"""


import ctypes
import glob
import json
import logging
import os
from pathlib import Path
import re
import shutil
from subprocess import check_output
import sys
import zipfile

import appdirs
import click
import requests
from semver import VersionInfo


# Useful constants.
#: The unique USB vendor ID for Adafruit boards.
VENDOR_ID = 9114
#: Flag to indicate if the command is being run in verbose mode.
VERBOSE = False
#: The location of data files used by circup (following OS conventions).
DATA_DIR = appdirs.user_data_dir(appname="circup", appauthor="adafruit")
#: The path to the JSON file containing the metadata about the current bundle.
BUNDLE_DATA = os.path.join(DATA_DIR, "circup.json")
#: The path to the zip file containing the current library bundle.
BUNDLE_ZIP = os.path.join(DATA_DIR, "adafruit-circuitpython-bundle-{}.zip")
#: The path to the directory into which the current bundle is unzipped.
BUNDLE_DIR = os.path.join(DATA_DIR, "adafruit_circuitpython_bundle_{}")
#: The directory containing the utility's log file.
LOG_DIR = appdirs.user_log_dir(appname="circup", appauthor="adafruit")
#: The location of the log file for the utility.
LOGFILE = os.path.join(LOG_DIR, "circup.log")
#:  The libraries (and blank lines) which don't go on devices
NOT_MCU_LIBRARIES = [
    "",
    "adafruit-blinka",
    "adafruit-blinka-bleio",
    "adafruit-blinka-displayio",
    "pyserial",
]
#: The version of CircuitPython found on the connected device.
CPY_VERSION = ""


# Ensure DATA_DIR / LOG_DIR related directories and files exist.
if not os.path.exists(DATA_DIR):  # pragma: no cover
    os.makedirs(DATA_DIR)
if not os.path.exists(LOG_DIR):  # pragma: no cover
    os.makedirs(LOG_DIR)


# Setup logging.
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logfile_handler = logging.FileHandler(LOGFILE)
log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)s: %(message)s", datefmt="%m/%d/%Y %H:%M:%S"
)
logfile_handler.setFormatter(log_formatter)
logger.addHandler(logfile_handler)


__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/circup.git"


class Module:
    """
    Represents a CircuitPython module.
    """

    # pylint: disable=too-many-arguments

    def __init__(self, path, repo, device_version, bundle_version, mpy):
        """
        The ``self.file`` and ``self.name`` attributes are constructed from
        the ``path`` value. If the path is to a directory based module, the
        resulting self.file value will be None, and the name will be the
        basename of the directory path.

        :param str path: The path to the module on the connected
            CIRCUITPYTHON device.
        :param str repo: The URL of the Git repository for this module.
        :param str device_version: The semver value for the version on device.
        :param str bundle_version: The semver value for the version in bundle.
        :param bool mpy: Flag to indicate if the module is byte-code compiled.
        """
        self.path = path
        if os.path.isfile(self.path):
            # Single file module.
            self.file = os.path.basename(path)
            self.name = self.file.replace(".py", "").replace(".mpy", "")
        else:
            # Directory based module.
            self.file = None
            self.name = os.path.basename(os.path.dirname(self.path))
        self.repo = repo
        self.device_version = device_version
        self.bundle_version = bundle_version
        self.mpy = mpy
        # Figure out the bundle path.
        self.bundle_path = None
        if self.mpy:
            # Byte compiled, now check CircuitPython version.
            major_version = CPY_VERSION.split(".")[0]
            bundle_platform = "{}mpy".format(major_version)
        else:
            # Regular Python
            bundle_platform = "py"
        for search_path, _, _ in os.walk(BUNDLE_DIR.format(bundle_platform)):
            if os.path.basename(search_path) == "lib":
                if self.file:
                    self.bundle_path = os.path.join(search_path, self.file)
                else:
                    self.bundle_path = os.path.join(search_path, self.name)
        logger.info(self)

    # pylint: enable=too-many-arguments

    @property
    def outofdate(self):
        """
        Returns a boolean to indicate if this module is out of date.

        :return: Truthy indication if the module is out of date.
        """
        if self.device_version and self.bundle_version:
            try:
                return VersionInfo.parse(self.device_version) < VersionInfo.parse(
                    self.bundle_version
                )
            except ValueError as ex:
                logger.warning("Module '%s' has incorrect semver value.", self.name)
                logger.warning(ex)
        return True  # Assume out of date to try to update.

    @property
    def major_update(self):
        """
        Returns a boolean to indicate if this is a major version update.

        :return: Boolean indicating if this is a major version upgrade
        """
        try:
            if (
                VersionInfo.parse(self.device_version).major
                == VersionInfo.parse(self.bundle_version).major
            ):
                return False
        except (TypeError, ValueError) as ex:
            logger.warning("Module '%s' has incorrect semver value.", self.name)
            logger.warning(ex)
        return True  # Assume Major Version udpate.

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
        major_update = str(self.major_update)
        return (self.name, loc, rem, major_update)

    def update(self):
        """
        Delete the module on the device, then copy the module from the bundle
        back onto the device.

        The caller is expected to handle any exceptions raised.
        """
        if os.path.isdir(self.path):
            # Delete and copy the directory.
            shutil.rmtree(self.path, ignore_errors=True)
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
                "mpy": self.mpy,
            }
        )


def clean_library_name(assumed_library_name):
    """
    Most CP repos and library names are look like this:

        repo: Adafruit_CircuitPython_LC709203F
        library: adafruit_lc709203f

    But some do not and this handles cleaning that up.
    Also cleans up if the pypi or reponame is passed in instead of the
    CP library name.

    :param str assumed_library_name: An assumed name of a library from user
        or requirements.txt entry
    :return: str proper library name
    """
    not_standard_names = {
        # Assumed Name : Actual Name
        "adafruit_adafruitio": "adafruit_io",
        "adafruit_busdevice": "adafruit_bus_device",
        "adafruit_neopixel": "neopixel",
        "adafruit_sd": "adafruit_sdcard",
        "adafruit_simpleio": "simpleio",
    }
    if "circuitpython" in assumed_library_name:
        # convert repo or pypi name to common library name
        assumed_library_name = (
            assumed_library_name.replace("-circuitpython-", "_")
            .replace("_circuitpython_", "_")
            .replace("-", "_")
        )
    if assumed_library_name in not_standard_names.keys():
        return not_standard_names[assumed_library_name]
    return assumed_library_name


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
                logger.error("Could not parse %s", BUNDLE_DATA)
                logger.exception(ex)
    if tag > old_tag:
        logger.info("New version available (%s).", tag)
        try:
            get_bundle(tag)
            with open(BUNDLE_DATA, "w", encoding="utf-8") as data:
                json.dump({"tag": tag}, data)
        except requests.exceptions.HTTPError as ex:
            # See #20 for reason this this
            click.secho(
                (
                    "There was a problem downloading the bundle. "
                    "Please try again in a moment."
                ),
                fg="red",
            )
            logger.exception(ex)
            sys.exit(1)
    else:
        logger.info("Current library bundle up to date %s.", tag)


def extract_metadata(path):
    """
    Given an file path, return a dictionary containing metadata extracted from
    dunder attributes found therein. Works with both .py and .mpy files.

    For Python source files, such metadata assignments should be simple and
    single-line. For example::

        __version__ = "1.1.4"
        __repo__ = "https://github.com/adafruit/SomeLibrary.git"

    For byte compiled .mpy files, a brute force / backtrack approach is used
    to find the __version__ number in the file -- see comments in the
    code for the implementation details.

    :param str path: The path to the file containing the metadata.
    :return: The dunder based metadata found in the file, as a dictionary.
    """
    result = {}
    logger.info("%s", path)
    if path.endswith(".py"):
        result["mpy"] = False
        with open(path, encoding="utf-8") as source_file:
            content = source_file.read()
        #: The regex used to extract ``__version__`` and ``__repo__`` assignments.
        dunder_key_val = r"""(__\w+__)\s*=\s*(?:['"]|\(\s)(.+)['"]"""
        for match in re.findall(dunder_key_val, content):
            result[match[0]] = str(match[1])
        if result:
            logger.info("Extracted metadata: %s", result)
        return result
    if path.endswith(".mpy"):
        result["mpy"] = True
        with open(path, "rb") as mpy_file:
            content = mpy_file.read()
        # Find the start location of the "__version__" (prepended with byte
        # value of 11 to indicate length of "__version__").
        loc = content.find(b"\x0b__version__")
        if loc > -1:
            # Backtrack until a byte value of the offset is reached.
            offset = 1
            while offset < loc:
                val = int(content[loc - offset])
                if val == offset - 1:  # Off by one..!
                    # Found version, extract the number given boundaries.
                    start = loc - offset + 1  # No need for prepended length.
                    end = loc  # Up to the start of the __version__.
                    version = content[start:end]  # Slice the version number.
                    # Create a string version as metadata in the result.
                    result = {"__version__": version.decode("utf-8"), "mpy": True}
                    break  # Nothing more to do.
                offset += 1  # ...and again but backtrack by one.
    return result


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
                continue
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
                if os.path.exists(path) and get_volume_name(path) == "CIRCUITPY":
                    device_dir = path
                    # Report only the FIRST device found.
                    break
        finally:
            ctypes.windll.kernel32.SetErrorMode(old_mode)
    else:
        # No support for unknown operating systems.
        raise NotImplementedError('OS "{}" not supported.'.format(os.name))
    logger.info("Found device: %s", device_dir)
    return device_dir


def find_modules(device_path):
    """
    Extracts metadata from the connected device and available bundle and
    returns this as a list of Module instances representing the modules on the
    device.

    :return: A list of Module instances describing the current state of the
             modules on the connected device.
    """
    # pylint: disable=broad-except
    try:
        device_modules = get_device_versions(device_path)
        bundle_modules = get_bundle_versions()
        result = []
        for name, device_metadata in device_modules.items():
            if name in bundle_modules:
                bundle_metadata = bundle_modules[name]
                path = device_metadata["path"]
                repo = bundle_metadata.get("__repo__")
                device_version = device_metadata.get("__version__")
                bundle_version = bundle_metadata.get("__version__")
                mpy = device_metadata["mpy"]
                result.append(Module(path, repo, device_version, bundle_version, mpy))
        return result
    except Exception as ex:
        # If it's not possible to get the device and bundle metadata, bail out
        # with a friendly message and indication of what's gone wrong.
        logger.exception(ex)
        click.echo("There was a problem: {}".format(ex))
        sys.exit(1)
    # pylint: enable=broad-except


def get_bundle(tag):
    """
    Downloads and extracts the version of the bundle with the referenced tag.

    :param str tag: The GIT tag to use to download the bundle.
    :return: The location of the resulting zip file in a temporary location on
             the local filesystem.
    """
    urls = {
        "py": (
            "https://github.com/adafruit/Adafruit_CircuitPython_Bundle"
            "/releases/download"
            "/{tag}/adafruit-circuitpython-bundle-py-{tag}.zip".format(tag=tag)
        ),
        "6mpy": (
            "https://github.com/adafruit/Adafruit_CircuitPython_Bundle/"
            "releases/download"
            "/{tag}/adafruit-circuitpython-bundle-6.x-mpy-{tag}.zip".format(tag=tag)
        ),
    }
    click.echo("Downloading latest version information.\n")
    for platform, url in urls.items():
        logger.info("Downloading bundle: %s", url)
        r = requests.get(url, stream=True)
        # pylint: disable=no-member
        if r.status_code != requests.codes.ok:
            logger.warning("Unable to connect to %s", url)
            r.raise_for_status()
        # pylint: enable=no-member
        total_size = int(r.headers.get("Content-Length"))
        temp_zip = BUNDLE_ZIP.format(platform)
        with click.progressbar(r.iter_content(1024), length=total_size) as pbar, open(
            temp_zip, "wb"
        ) as f:
            for chunk in pbar:
                f.write(chunk)
                pbar.update(len(chunk))
        logger.info("Saved to %s", temp_zip)
        temp_dir = BUNDLE_DIR.format(platform)
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)
        with zipfile.ZipFile(temp_zip, "r") as zfile:
            zfile.extractall(temp_dir)
    click.echo("\nOK\n")


def get_bundle_versions():
    """
    Returns a dictionary of metadata from modules in the latest known release
    of the library bundle. Uses the Python version (rather than the compiled
    version) of the library modules.

    :return: A dictionary of metadata about the modules available in the
             library bundle.
    """
    ensure_latest_bundle()
    path = None
    for path, _, _ in os.walk(BUNDLE_DIR.format("py")):
        if os.path.basename(path) == "lib":
            break
    return get_modules(path)


def get_circuitpython_version(device_path):
    """
    Returns the version number of CircuitPython running on the board connected
    via ``device_path``. This is obtained from the ``boot_out.txt`` file on the
    device, whose content will start with something like this::

        Adafruit CircuitPython 4.1.0 on 2019-08-02;

    :param str device_path: The path to the connected board.
    :return: The version string for CircuitPython running on the connected
             board.
    """
    with open(os.path.join(device_path, "boot_out.txt")) as boot:
        circuit_python, _ = boot.read().split(";")
    return circuit_python.split(" ")[-3]


def get_dependencies(*requested_libraries, mod_names, to_install=()):
    """
    Return a list of other CircuitPython libraries

    :param tuple requested_libraries: The libraries to search for dependencies
    :param object mod_names:  All the modules metadata from bundle
    :return: tuple of module names to install which we build
    """
    # Internal variables
    _to_install = to_install
    _requested_libraries = []
    _rl = requested_libraries[0]

    if not requested_libraries[0]:
        # If nothing is requested, we're done
        return _to_install

    for l in _rl:
        # Convert tuple to list and force all to lowercase, Clean the names
        l = clean_library_name(l.lower())
        if l in NOT_MCU_LIBRARIES:
            logger.info("Skipping %s. It is not for microcontroller installs.", l)
        else:
            try:
                # Don't process any names we can't find in mod_names
                mod_names[l]  # pylint: disable=pointless-statement
                _requested_libraries.append(l)
            except KeyError:
                click.secho(
                    f"WARNING:\n\t{l} is not a known CircuitPython library.",
                    fg="yellow",
                )

    if not _requested_libraries:
        # If nothing is requested, we're done
        return _to_install

    for library in _requested_libraries:
        if library not in _to_install:
            _to_install = _to_install + (library,)
            # get the requirements.txt from bundle
            requirements_txt = get_requirements(library)
            if requirements_txt:
                _requested_libraries.extend(
                    libraries_from_requirements(requirements_txt)
                )
        # we've processed this library, remove it from the list
        _requested_libraries.remove(library)

        return get_dependencies(
            tuple(_requested_libraries),
            mod_names=mod_names,
            to_install=_to_install,
        )


def get_device_versions(device_path):
    """
    Returns a dictionary of metadata from modules on the connected device.

    :return: A dictionary of metadata about the modules available on the
             connected device.
    """
    return get_modules(os.path.join(device_path, "lib"))


def get_latest_tag():
    """
    Find the value of the latest tag for the Adafruit CircuitPython library
    bundle.

    :return: The most recent tag value for the project.
    """
    url = "https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/latest"
    logger.info("Requesting tag information: %s", url)
    response = requests.get(url)
    logger.info("Response url: %s", response.url)
    tag = response.url.rsplit("/", 1)[-1]
    logger.info("Tag: '%s'", tag)
    return tag


def get_modules(path):
    """
    Get a dictionary containing metadata about all the Python modules found in
    the referenced path.

    :param str path: The directory in which to find modules.
    :return: A dictionary containing metadata about the found modules.
    """
    result = {}
    if not path:
        return result
    single_file_py_mods = glob.glob(os.path.join(path, "*.py"))
    single_file_mpy_mods = glob.glob(os.path.join(path, "*.mpy"))
    directory_mods = [
        d
        for d in glob.glob(os.path.join(path, "*", ""))
        if not os.path.basename(os.path.normpath(d)).startswith(".")
    ]
    single_file_mods = single_file_py_mods + single_file_mpy_mods
    for sfm in [f for f in single_file_mods if not os.path.basename(f).startswith(".")]:
        metadata = extract_metadata(sfm)
        metadata["path"] = sfm
        result[os.path.basename(sfm).replace(".py", "").replace(".mpy", "")] = metadata
    for dm in directory_mods:
        name = os.path.basename(os.path.dirname(dm))
        metadata = {}
        py_files = glob.glob(os.path.join(dm, "*.py"))
        mpy_files = glob.glob(os.path.join(dm, "*.mpy"))
        all_files = py_files + mpy_files
        for source in [f for f in all_files if not os.path.basename(f).startswith(".")]:
            metadata = extract_metadata(source)
            if "__version__" in metadata:
                metadata["path"] = dm
                result[name] = metadata
                break
        else:
            # No version metadata found.
            result[name] = {"path": dm, "mpy": bool(mpy_files)}
    return result


def get_requirements(library_name):
    """
    Return a string of the requirements.txt for a GitHub Repo
    NOTE: This is only looks at the py bundle. No known differences in the mpy
    bundle for requirements.txt

    :param str library_name: CircuitPython library name
    :return: str the content of requirements.txt or None if not found
    """
    tag = get_latest_tag()
    bundle_path = BUNDLE_DIR.format("py")
    requirements_txt = (
        "{}/adafruit-circuitpython-bundle-py-{}/requirements/{}/"
        "requirements.txt".format(bundle_path, tag, library_name)
    )
    if Path(requirements_txt).is_file():
        return open(requirements_txt).read()
    return None


# pylint: disable=too-many-locals,too-many-branches
def install_module(device_path, name, py, mod_names):  # pragma: no cover
    """
    Finds a connected device and installs a given module name if it
    is available in the current module bundle and is not already
    installed on the device.
    TODO: There is currently no check for the version.

    :param str device_path: The path to the connected board.
    :param str name: Name of module to install
    :param bool py: Boolean to specify if the module should be installed from
                    source or from a pre-compiled module
    :param mod_names: Dictionary of metadata from modules that can be generated
                       with get_bundle_versions()
    """
    if not name:
        click.echo("No module name(s) provided.")
    elif name in mod_names:
        library_path = os.path.join(device_path, "lib")
        if not os.path.exists(library_path):  # pragma: no cover
            os.makedirs(library_path)
        metadata = mod_names[name]
        # Grab device modules to check if module already installed
        device_modules = []
        for module in find_modules(device_path):
            device_modules.append(module.name)
        if name in device_modules:
            click.echo("'{}' is already installed.".format(name))
            return
        if py:
            # Use Python source for module.
            source_path = metadata["path"]  # Path to Python source version.
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
        else:
            # Use pre-compiled mpy modules.
            module_name = os.path.basename(metadata["path"]).replace(".py", ".mpy")
            if not module_name:
                # Must be a directory based module.
                module_name = os.path.basename(os.path.dirname(metadata["path"]))
            major_version = CPY_VERSION.split(".")[0]
            bundle_platform = "{}mpy".format(major_version)
            bundle_path = ""
            for path, _, _ in os.walk(BUNDLE_DIR.format(bundle_platform)):
                if os.path.basename(path) == "lib":
                    bundle_path = os.path.join(path, module_name)
            if bundle_path:
                if os.path.isdir(bundle_path):
                    target_path = os.path.join(library_path, module_name)
                    # Copy the directory.
                    shutil.copytree(bundle_path, target_path)
                else:
                    target = os.path.basename(bundle_path)
                    target_path = os.path.join(library_path, target)
                    # Copy file.
                    shutil.copyfile(bundle_path, target_path)
            else:
                raise IOError("Cannot find compiled version of module.")
        click.echo("Installed '{}'.".format(name))
    else:
        click.echo("Unknown module named, '{}'.".format(name))


# pylint: enable=too-many-locals,too-many-branches


def libraries_from_requirements(requirements):
    """
    Clean up supplied requirements.txt and turn into tuple of CP libraries

    :param str requirements: A string version of a requirements.txt
    :return: tuple of library names
    """
    libraries = ()
    for line in requirements.split("\n"):
        line = line.lower().strip()
        if line.startswith("#") or line == "":
            # skip comments
            pass
        else:
            if any(operators in line for operators in [">", "<", "="]):
                # Remove everything after any pip style version specifiers
                line = re.split("[<|>|=|]", line)[0]
            libraries = libraries + (line,)
    return libraries


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
@click.option(
    "--path",
    type=click.Path(exists=True, file_okay=False),
    help="Path to CircuitPython directory. Overrides automatic path detection.",
)
@click.version_option(
    prog_name="CircUp",
    message="%(prog)s, A CircuitPython module updater. Version %(version)s",
)
@click.pass_context
def main(ctx, verbose, path):  # pragma: no cover
    """
    A tool to manage and update libraries on a CircuitPython device.
    """
    ctx.ensure_object(dict)
    if verbose:
        # Configure additional logging to stdout.
        global VERBOSE
        VERBOSE = True
        verbose_handler = logging.StreamHandler(sys.stdout)
        verbose_handler.setLevel(logging.INFO)
        verbose_handler.setFormatter(log_formatter)
        logger.addHandler(verbose_handler)
        click.echo("Logging to {}\n".format(LOGFILE))
    logger.info("### Started Circup ###")
    if path:
        device_path = path
    else:
        device_path = find_device()
    ctx.obj["DEVICE_PATH"] = device_path
    if device_path is None:
        click.secho("Could not find a connected Adafruit device.", fg="red")
        sys.exit(1)
    global CPY_VERSION
    CPY_VERSION = get_circuitpython_version(device_path)
    click.echo(
        "Found device at {}, running CircuitPython {}.".format(device_path, CPY_VERSION)
    )
    cp_release = requests.get(
        "https://github.com/adafruit/circuitpython/releases/latest", timeout=2
    )
    latest_version = cp_release.url.split("/")[-1]
    try:
        if VersionInfo.parse(CPY_VERSION) < VersionInfo.parse(latest_version):
            click.secho(
                "A newer version of CircuitPython ({}) is available.".format(
                    latest_version
                ),
                fg="green",
            )
    except ValueError as ex:
        logger.warning("CircuitPython has incorrect semver value.")
        logger.warning(ex)


@main.command()
@click.option("-r", "--requirement", is_flag=True)
@click.pass_context
def freeze(ctx, requirement):  # pragma: no cover
    """
    Output details of all the modules found on the connected CIRCUITPYTHON
    device. Option -r saves output to requirements.txt file
    """
    logger.info("Freeze")
    modules = find_modules(ctx.obj["DEVICE_PATH"])
    if modules:
        output = []
        for module in modules:
            output.append("{}=={}".format(module.name, module.device_version))
        for module in output:
            click.echo(module)
            logger.info(module)
        if requirement:
            cwd = os.path.abspath(os.getcwd())
            for i, module in enumerate(output):
                output[i] += "\n"
            with open(cwd + "/" + "requirements.txt", "w", newline="\n") as file:
                file.truncate(0)
                file.writelines(output)
    else:
        click.echo("No modules found on the device.")


@main.command()
@click.pass_context
def list(ctx):  # pragma: no cover
    """
    Lists all out of date modules found on the connected CIRCUITPYTHON device.
    """
    logger.info("List")
    # Grab out of date modules.
    data = [("Module", "Version", "Latest", "Major Update")]

    modules = [m.row for m in find_modules(ctx.obj["DEVICE_PATH"]) if m.outofdate]
    if modules:
        data += modules
        # Nice tabular display.
        col_width = [0, 0, 0, 0]
        for row in data:
            for i, word in enumerate(row):
                col_width[i] = max(len(word) + 2, col_width[i])
        dashes = tuple(("-" * (width - 1) for width in col_width))
        data.insert(1, dashes)
        click.echo(
            "The following modules are out of date or probably need an update.\n"
            "Major Updates may include breaking changes. Review before updating.\n"
        )
        for row in data:
            output = ""
            for index, cell in enumerate(row):
                output += cell.ljust(col_width[index])
            if not VERBOSE:
                click.echo(output)
            logger.info(output)
    else:
        click.echo("All modules found on the device are up to date.")


@main.command()
@click.argument("modules", required=False, nargs=-1)
@click.option("--py", is_flag=True)
@click.option("-r", "--requirement")
@click.pass_context
def install(ctx, modules, py, requirement):  # pragma: no cover
    """
    Install a named module(s) onto the device. Multiple modules
    can be installed at once by providing more than one module name, each
    separated by a space.
    Option -r allows specifying a text file to install all modules listed in
    the text file.

    TODO: Ensure there's enough space on the device, work out the version of
    CircuitPytho on the device in order to copy the appropriate .mpy versions
    too. ;-)
    """
    available_modules = get_bundle_versions()
    mod_names = {}
    for module, metadata in available_modules.items():
        mod_names[module.replace(".py", "").lower()] = metadata
    if requirement:
        cwd = os.path.abspath(os.getcwd())
        requirements_txt = open(cwd + "/" + requirement, "r").read()
        requested_installs = sorted(libraries_from_requirements(requirements_txt))
    else:
        requested_installs = sorted(modules)
    click.echo(f"Searching for dependencies for: {requested_installs}")
    to_install = get_dependencies(requested_installs, mod_names=mod_names)
    if to_install is not None:
        to_install = sorted(to_install)
        click.echo(f"Ready to install: {to_install}\n")
        for library in to_install:
            install_module(ctx.obj["DEVICE_PATH"], library, py, mod_names)


@click.argument("match", required=False, nargs=1)
@main.command()
def show(match):  # pragma: no cover
    """
    Show a list of available modules in the bundle. These are modules which
    *could* be installed on the device.

    If MATCH is specified only matching modules will be listed.
    """
    available_modules = get_bundle_versions()
    module_names = sorted([m.replace(".py", "") for m in available_modules])
    if match is not None:
        module_names = [m for m in module_names if match in m]
    click.echo("\n".join(module_names))

    click.echo(
        "{} shown of {} packages.".format(len(module_names), len(available_modules))
    )


@main.command()
@click.argument("module", nargs=-1)
@click.pass_context
def uninstall(ctx, module):  # pragma: no cover
    """
    Uninstall a named module(s) from the connected device. Multiple modules
    can be uninstalled at once by providing more than one module name, each
    separated by a space.
    """
    for name in module:
        device_modules = get_device_versions(ctx.obj["DEVICE_PATH"])
        name = name.lower()
        mod_names = {}
        for module_item, metadata in device_modules.items():
            mod_names[module_item.replace(".py", "").lower()] = metadata
        if name in mod_names:
            library_path = os.path.join(ctx.obj["DEVICE_PATH"], "lib")
            metadata = mod_names[name]
            module_path = metadata["path"]
            if os.path.isdir(module_path):
                target = os.path.basename(os.path.dirname(module_path))
                target_path = os.path.join(library_path, target)
                # Remove the directory.
                shutil.rmtree(target_path)
            else:
                target = os.path.basename(module_path)
                target_path = os.path.join(library_path, target)
                # Remove file
                os.remove(target_path)
            click.echo("Uninstalled '{}'.".format(name))
        else:
            click.echo("Module '{}' not found on device.".format(name))


@main.command(
    short_help=(
        "Update modules on the device. "
        "Use --all to automatically update all modules without Major Version warnings."
    )
)
@click.option(
    "--all", is_flag=True, help="Update all modules without Major Version warnings."
)
@click.pass_context
def update(ctx, all):  # pragma: no cover
    """
    Checks for out-of-date modules on the connected CIRCUITPYTHON device, and
    prompts the user to confirm updating such modules.
    """
    logger.info("Update")
    # Grab out of date modules.
    modules = [m for m in find_modules(ctx.obj["DEVICE_PATH"]) if m.outofdate]
    if modules:
        click.echo("Found {} module[s] needing update.".format(len(modules)))
        if not all:
            click.echo("Please indicate which modules you wish to update:\n")
        for module in modules:
            update_flag = all
            if VERBOSE:
                click.echo(
                    "Device version: {}, Bundle version: {}".format(
                        module.device_version, module.bundle_version
                    )
                )
            if isinstance(module.bundle_version, str) and not VersionInfo.isvalid(
                module.bundle_version
            ):
                click.secho(
                    f"WARNING: Library {module.name} repo has incorrect __version__"
                    "\n\tmetadata. Circup will assume it needs updating."
                    "\n\tPlease file an issue in the library repo.",
                    fg="yellow",
                )
                if module.repo:
                    click.secho(f"\t{module.repo}", fg="yellow")
            if not update_flag:
                if module.major_update:
                    update_flag = click.confirm(
                        (
                            "'{}' is a Major Version update and may contain breaking "
                            "changes. Do you want to update?".format(module.name)
                        )
                    )
                else:
                    update_flag = click.confirm("Update '{}'?".format(module.name))
            if update_flag:
                # pylint: disable=broad-except
                try:
                    module.update()
                    click.echo("Updated {}".format(module.name))
                except Exception as ex:
                    logger.exception(ex)
                    click.echo(
                        "Something went wrong, {} (check the logs)".format(str(ex))
                    )
                # pylint: enable=broad-except
    else:
        click.echo("None of the modules found on the device need an update.")


# Allows execution via `python -m circup ...`
# pylint: disable=no-value-for-parameter
if __name__ == "__main__":  # pragma: no cover
    main()
