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
import time
from logging.handlers import RotatingFileHandler
import os
import re
import shutil
import socket
import sys
import tempfile
import zipfile
from subprocess import check_output
from urllib.parse import urlparse, urljoin

import appdirs
import click
import findimports
import pkg_resources
import requests
import toml
import update_checker
from requests.auth import HTTPBasicAuth
from semver import VersionInfo

from circup.shared import DATA_DIR, BAD_FILE_FORMAT, extract_metadata, _get_modules_file
from circup.backends import WebBackend, DiskBackend

#: The version of CircuitPython found on the connected device.
CPY_VERSION = ""

# Useful constants.
#: Flag to indicate if the command is being run in verbose mode.
VERBOSE = False

#: The path to the JSON file containing the metadata about the bundles.
BUNDLE_CONFIG_FILE = pkg_resources.resource_filename(
    "circup", "config/bundle_config.json"
)
#: Overwrite the bundles list with this file (only done manually)
BUNDLE_CONFIG_OVERWRITE = os.path.join(DATA_DIR, "bundle_config.json")
#: The path to the JSON file containing the local list of bundles.
BUNDLE_CONFIG_LOCAL = os.path.join(DATA_DIR, "bundle_config_local.json")
#: The path to the JSON file containing the metadata about the bundles.
BUNDLE_DATA = os.path.join(DATA_DIR, "circup.json")
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
    "adafruit-circuitpython-typing",
    "circuitpython_typing",
    "pyserial",
]

#: Module formats list (and the other form used in github files)
PLATFORMS = {"py": "py", "8mpy": "8.x-mpy", "9mpy": "9.x-mpy"}
#: Commands that do not require an attached board
BOARDLESS_COMMANDS = ["show", "bundle-add", "bundle-remove", "bundle-show"]

#: Timeout for requests calls like get()
REQUESTS_TIMEOUT = 30

# Ensure DATA_DIR / LOG_DIR related directories and files exist.
if not os.path.exists(DATA_DIR):  # pragma: no cover
    os.makedirs(DATA_DIR)
if not os.path.exists(LOG_DIR):  # pragma: no cover
    os.makedirs(LOG_DIR)


# Setup logging.
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logfile_handler = RotatingFileHandler(LOGFILE, maxBytes=10_000_000, backupCount=0)
log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)s: %(message)s", datefmt="%m/%d/%Y %H:%M:%S"
)
logfile_handler.setFormatter(log_formatter)
logger.addHandler(logfile_handler)


__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/circup.git"


class Bundle:
    """
    All the links and file names for a bundle
    """

    def __init__(self, repo):
        """
        Initialise a Bundle created from its github info.
        Construct all the strings in one place.

        :param str repo: Repository string for github: "user/repository"
        """
        vendor, bundle_id = repo.split("/")
        bundle_id = bundle_id.lower().replace("_", "-")
        self.key = repo
        #
        self.url = "https://github.com/" + repo
        self.basename = bundle_id + "-{platform}-{tag}"
        self.urlzip = self.basename + ".zip"
        self.dir = os.path.join(DATA_DIR, vendor, bundle_id + "-{platform}")
        self.zip = os.path.join(DATA_DIR, bundle_id + "-{platform}.zip")
        self.url_format = self.url + "/releases/download/{tag}/" + self.urlzip
        # tag
        self._current = None
        self._latest = None

    def lib_dir(self, platform):
        """
        This bundle's lib directory for the platform.

        :param str platform: The platform identifier (py/6mpy/...).
        :return: The path to the lib directory for the platform.
        """
        tag = self.current_tag
        return os.path.join(
            self.dir.format(platform=platform),
            self.basename.format(platform=PLATFORMS[platform], tag=tag),
            "lib",
        )

    def requirements_for(self, library_name, toml_file=False):
        """
        The requirements file for this library.

        :param str library_name: The name of the library.
        :return: The path to the requirements.txt file.
        """
        platform = "py"
        tag = self.current_tag
        found_file = os.path.join(
            self.dir.format(platform=platform),
            self.basename.format(platform=PLATFORMS[platform], tag=tag),
            "requirements",
            library_name,
            "requirements.txt" if not toml_file else "pyproject.toml",
        )
        if os.path.isfile(found_file):
            with open(found_file, "r", encoding="utf-8") as read_this:
                return read_this.read()
        return None

    @property
    def current_tag(self):
        """
        Lazy load current cached tag from the BUNDLE_DATA json file.

        :return: The current cached tag value for the project.
        """
        if self._current is None:
            self._current = tags_data_load().get(self.key, "0")
        return self._current

    @current_tag.setter
    def current_tag(self, tag):
        """
        Set the current cached tag (after updating).

        :param str tag: The new value for the current tag.
        :return: The current cached tag value for the project.
        """
        self._current = tag

    @property
    def latest_tag(self):
        """
        Lazy find the value of the latest tag for the bundle.

        :return: The most recent tag value for the project.
        """
        if self._latest is None:
            self._latest = get_latest_release_from_url(self.url + "/releases/latest")
        return self._latest

    def validate(self):
        """
        Test the existence of the expected URLs (not their content)
        """
        tag = self.latest_tag
        if not tag or tag == "releases":
            if VERBOSE:
                click.secho(f'  Invalid tag "{tag}"', fg="red")
            return False
        for platform in PLATFORMS.values():
            url = self.url_format.format(platform=platform, tag=tag)
            r = requests.get(url, stream=True, timeout=REQUESTS_TIMEOUT)
            # pylint: disable=no-member
            if r.status_code != requests.codes.ok:
                if VERBOSE:
                    click.secho(f"  Unable to find {os.path.split(url)[1]}", fg="red")
                return False
            # pylint: enable=no-member
        return True

    def __repr__(self):
        """
        Helps with log files.

        :return: A repr of a dictionary containing the Bundles's metadata.
        """
        return repr(
            {
                "key": self.key,
                "url": self.url,
                "urlzip": self.urlzip,
                "dir": self.dir,
                "zip": self.zip,
                "url_format": self.url_format,
                "current": self._current,
                "latest": self._latest,
            }
        )


class Module:
    """
    Represents a CircuitPython module.
    """

    # pylint: disable=too-many-arguments

    def __init__(
        self,
        name,
        backend,
        repo,
        device_version,
        bundle_version,
        mpy,
        bundle,
        compatibility,
    ):
        """
        The ``self.file`` and ``self.name`` attributes are constructed from
        the ``path`` value. If the path is to a directory based module, the
        resulting self.file value will be None, and the name will be the
        basename of the directory path.

        :param str name: The file name of the module.
        :param Backend backend: The backend that the module is on.
        :param str repo: The URL of the Git repository for this module.
        :param str device_version: The semver value for the version on device.
        :param str bundle_version: The semver value for the version in bundle.
        :param bool mpy: Flag to indicate if the module is byte-code compiled.
        :param Bundle bundle: Bundle object where the module is located.
        :param (str,str) compatibility: Min and max versions of CP compatible with the mpy.
        """
        self.name = name
        self.backend = backend
        self.path = (
            urljoin(backend.library_path, name, allow_fragments=False)
            if isinstance(backend, WebBackend)
            else os.path.join(backend.library_path, name)
        )

        url = urlparse(self.path, allow_fragments=False)

        if (
            url.path.endswith("/")
            if isinstance(backend, WebBackend)
            else self.path.endswith(os.sep)
        ):
            self.file = None
            self.name = self.path.split(
                "/" if isinstance(backend, WebBackend) else os.sep
            )[-2]
        else:
            self.file = os.path.basename(url.path)
            self.name = (
                os.path.basename(url.path).replace(".py", "").replace(".mpy", "")
            )

        self.repo = repo
        self.device_version = device_version
        self.bundle_version = bundle_version
        self.mpy = mpy
        self.min_version = compatibility[0]
        self.max_version = compatibility[1]
        # Figure out the bundle path.
        self.bundle_path = None
        if self.mpy:
            # Byte compiled, now check CircuitPython version.
            major_version = CPY_VERSION.split(".")[0]
            bundle_platform = "{}mpy".format(major_version)
        else:
            # Regular Python
            bundle_platform = "py"
        # module path in the bundle
        search_path = bundle.lib_dir(bundle_platform)
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
        Treat mismatched MPY versions as out of date.

        :return: Truthy indication if the module is out of date.
        """
        if self.mpy_mismatch:
            return True
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
    def bad_format(self):
        """A boolean indicating that the mpy file format could not be identified"""
        return self.mpy and self.device_version == BAD_FILE_FORMAT

    @property
    def mpy_mismatch(self):
        """
        Returns a boolean to indicate if this module's MPY version is compatible
        with the board's current version of Circuitpython. A min or max version
        that evals to False means no limit.

        :return: Boolean indicating if the MPY versions don't match.
        """
        if not self.mpy:
            return False
        try:
            cpv = VersionInfo.parse(CPY_VERSION)
        except ValueError as ex:
            logger.warning("CircuitPython has incorrect semver value.")
            logger.warning(ex)
        try:
            if self.min_version and cpv < VersionInfo.parse(self.min_version):
                return True  # CP version too old
            if self.max_version and cpv >= VersionInfo.parse(self.max_version):
                return True  # MPY version too old
        except (TypeError, ValueError) as ex:
            logger.warning(
                "Module '%s' has incorrect MPY compatibility information.", self.name
            )
            logger.warning(ex)
        return False

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
        name, local version and remote version, and reason to update.

        :return: A tuple containing the module's name, version on the connected
                 device, version in the latest bundle and reason to update.
        """
        loc = self.device_version if self.device_version else "unknown"
        rem = self.bundle_version if self.bundle_version else "unknown"
        if self.mpy_mismatch:
            update_reason = "MPY Format"
        elif self.major_update:
            update_reason = "Major Version"
        else:
            update_reason = "Minor Version"
        return (self.name, loc, rem, update_reason)

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
                "min_version": self.min_version,
                "max_version": self.max_version,
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
        "adafruit_asyncio": "asyncio",
        "adafruit_busdevice": "adafruit_bus_device",
        "adafruit_connectionmanager": "adafruit_connection_manager",
        "adafruit_display_button": "adafruit_button",
        "adafruit_neopixel": "neopixel",
        "adafruit_sd": "adafruit_sdcard",
        "adafruit_simpleio": "simpleio",
        "pimoroni_ltr559": "pimoroni_circuitpython_ltr559",
    }
    if "circuitpython" in assumed_library_name:
        # convert repo or pypi name to common library name
        assumed_library_name = (
            assumed_library_name.replace("-circuitpython-", "_")
            .replace("_circuitpython_", "_")
            .replace("-", "_")
        )
    if assumed_library_name in not_standard_names:
        return not_standard_names[assumed_library_name]
    return assumed_library_name


def completion_for_install(ctx, param, incomplete):
    """
    Returns the list of available modules for the command line tab-completion
    with the ``circup install`` command.
    """
    # pylint: disable=unused-argument
    available_modules = get_bundle_versions(get_bundles_list(), avoid_download=True)
    module_names = {m.replace(".py", "") for m in available_modules}
    if incomplete:
        module_names = [name for name in module_names if name.startswith(incomplete)]
    return sorted(module_names)


def ensure_latest_bundle(bundle):
    """
    Ensure that there's a copy of the latest library bundle available so circup
    can check the metadata contained therein.

    :param Bundle bundle: the target Bundle object.
    """
    logger.info("Checking library updates for %s.", bundle.key)
    tag = bundle.latest_tag
    do_update = False
    if tag == bundle.current_tag:
        for platform in PLATFORMS:
            # missing directories (new platform added on an existing install
            # or side effect of pytest or network errors)
            do_update = do_update or not os.path.isdir(bundle.lib_dir(platform))
    else:
        do_update = True

    if do_update:
        logger.info("New version available (%s).", tag)
        try:
            get_bundle(bundle, tag)
            tags_data_save_tag(bundle.key, tag)
        except requests.exceptions.HTTPError as ex:
            # See #20 for reason for this
            click.secho(
                (
                    "There was a problem downloading that platform bundle. "
                    "Skipping and using existing download if available."
                ),
                fg="red",
            )
            logger.exception(ex)
    else:
        logger.info("Current bundle up to date %s.", tag)


def find_device():
    """
    Return the location on the filesystem for the connected CircuitPython device.
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


def find_modules(backend, bundles_list):
    """
    Extracts metadata from the connected device and available bundles and
    returns this as a list of Module instances representing the modules on the
    device.

    :param Backend backend: Backend with the device connection.
    :param List[Bundle] bundles_list: List of supported bundles as Bundle objects.
    :return: A list of Module instances describing the current state of the
             modules on the connected device.
    """
    # pylint: disable=broad-except,too-many-locals
    try:
        device_modules = backend.get_device_versions()
        bundle_modules = get_bundle_versions(bundles_list)
        result = []
        for key, device_metadata in device_modules.items():

            if key in bundle_modules:
                path = device_metadata["path"]
                bundle_metadata = bundle_modules[key]
                repo = bundle_metadata.get("__repo__")
                bundle = bundle_metadata.get("bundle")
                device_version = device_metadata.get("__version__")
                bundle_version = bundle_metadata.get("__version__")
                mpy = device_metadata["mpy"]
                compatibility = device_metadata.get("compatibility", (None, None))
                module_name = (
                    path.split(os.sep)[-1]
                    if not path.endswith(os.sep)
                    else path[:-1].split(os.sep)[-1] + os.sep
                )

                m = Module(
                    module_name,
                    backend,
                    repo,
                    device_version,
                    bundle_version,
                    mpy,
                    bundle,
                    compatibility,
                )
                result.append(m)
        return result
    except Exception as ex:
        # If it's not possible to get the device and bundle metadata, bail out
        # with a friendly message and indication of what's gone wrong.
        logger.exception(ex)
        click.echo("There was a problem: {}".format(ex))
        sys.exit(1)
    # pylint: enable=broad-except,too-many-locals


def get_bundle(bundle, tag):
    """
    Downloads and extracts the version of the bundle with the referenced tag.
    The resulting zip file is saved on the local filesystem.

    :param Bundle bundle: the target Bundle object.
    :param str tag: The GIT tag to use to download the bundle.
    """
    click.echo(f"Downloading latest bundles for {bundle.key} ({tag}).")
    for platform, github_string in PLATFORMS.items():
        # Report the platform: "8.x-mpy", etc.
        click.echo(f"{github_string}:")
        url = bundle.url_format.format(platform=github_string, tag=tag)
        logger.info("Downloading bundle: %s", url)
        r = requests.get(url, stream=True, timeout=REQUESTS_TIMEOUT)
        # pylint: disable=no-member
        if r.status_code != requests.codes.ok:
            logger.warning("Unable to connect to %s", url)
            r.raise_for_status()
        # pylint: enable=no-member
        total_size = int(r.headers.get("Content-Length"))
        temp_zip = bundle.zip.format(platform=platform)
        with click.progressbar(
            r.iter_content(1024), label="Extracting:", length=total_size
        ) as pbar, open(temp_zip, "wb") as zip_fp:
            for chunk in pbar:
                zip_fp.write(chunk)
                pbar.update(len(chunk))
        logger.info("Saved to %s", temp_zip)
        temp_dir = bundle.dir.format(platform=platform)
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)
        with zipfile.ZipFile(temp_zip, "r") as zfile:
            zfile.extractall(temp_dir)
    bundle.current_tag = tag
    click.echo("\nOK\n")


def get_bundle_versions(bundles_list, avoid_download=False):
    """
    Returns a dictionary of metadata from modules in the latest known release
    of the library bundle. Uses the Python version (rather than the compiled
    version) of the library modules.

    :param List[Bundle] bundles_list: List of supported bundles as Bundle objects.
    :param bool avoid_download: if True, download the bundle only if missing.
    :return: A dictionary of metadata about the modules available in the
             library bundle.
    """
    all_the_modules = dict()
    for bundle in bundles_list:
        if not avoid_download or not os.path.isdir(bundle.lib_dir("py")):
            ensure_latest_bundle(bundle)
        path = bundle.lib_dir("py")
        path_modules = _get_modules_file(path, logger)
        for name, module in path_modules.items():
            module["bundle"] = bundle
            if name not in all_the_modules:  # here we decide the order of priority
                all_the_modules[name] = module
    return all_the_modules


def get_bundles_dict():
    """
    Retrieve the dictionary from BUNDLE_CONFIG_FILE (JSON).
    Put the local dictionary in front, so it gets priority.
    It's a dictionary of bundle string identifiers.

    :return: Combined dictionaries from the config files.
    """
    bundle_dict = get_bundles_local_dict()
    try:
        with open(BUNDLE_CONFIG_OVERWRITE, "rb") as bundle_config_json:
            bundle_config = json.load(bundle_config_json)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        with open(BUNDLE_CONFIG_FILE, "rb") as bundle_config_json:
            bundle_config = json.load(bundle_config_json)
    for name, bundle in bundle_config.items():
        if bundle not in bundle_dict.values():
            bundle_dict[name] = bundle
    return bundle_dict


def get_bundles_local_dict():
    """
    Retrieve the local bundles from BUNDLE_CONFIG_LOCAL (JSON).

    :return: Raw dictionary from the config file(s).
    """
    try:
        with open(BUNDLE_CONFIG_LOCAL, "rb") as bundle_config_json:
            bundle_config = json.load(bundle_config_json)
        if not isinstance(bundle_config, dict) or not bundle_config:
            logger.error("Local bundle list invalid. Skipped.")
            raise FileNotFoundError("Bad local bundle list")
        return bundle_config
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        return dict()


def get_bundles_list():
    """
    Retrieve the list of bundles from the config dictionary.

    :return: List of supported bundles as Bundle objects.
    """
    bundle_config = get_bundles_dict()
    bundles_list = [Bundle(bundle_config[b]) for b in bundle_config]
    logger.info("Using bundles: %s", ", ".join(b.key for b in bundles_list))
    return bundles_list


def get_circup_version():
    """Return the version of circup that is running. If not available, return None.

    :return: Current version of circup, or None.
    """
    try:
        from importlib import metadata  # pylint: disable=import-outside-toplevel
    except ImportError:
        try:
            import importlib_metadata as metadata  # pylint: disable=import-outside-toplevel
        except ImportError:
            return None
    try:
        return metadata.version("circup")
    except metadata.PackageNotFoundError:
        return None


def get_dependencies(*requested_libraries, mod_names, to_install=()):
    """
    Return a list of other CircuitPython libraries required by the given list
    of libraries

    :param tuple requested_libraries: The libraries to search for dependencies
    :param object mod_names:  All the modules metadata from bundle
    :param list(str) to_install: Modules already selected for installation.
    :return: tuple of module names to install which we build
    """
    # Internal variables
    _to_install = to_install
    _requested_libraries = []
    _rl = requested_libraries[0]

    if not requested_libraries[0]:
        # If nothing is requested, we're done
        return _to_install

    for lib_name in _rl:
        lower_lib_name = lib_name.lower()
        if lower_lib_name in NOT_MCU_LIBRARIES:
            logger.info(
                "Skipping %s. It is not for microcontroller installs.", lib_name
            )
        else:
            # Canonicalize, with some exceptions:
            # adafruit-circuitpython-something => adafruit_something
            canonical_lib_name = clean_library_name(lower_lib_name)
            try:
                # Don't process any names we can't find in mod_names
                mod_names[canonical_lib_name]  # pylint: disable=pointless-statement
                _requested_libraries.append(canonical_lib_name)
            except KeyError:
                click.secho(
                    f"WARNING:\n\t{canonical_lib_name} is not a known CircuitPython library.",
                    fg="yellow",
                )

    if not _requested_libraries:
        # If nothing is requested, we're done
        return _to_install

    for library in list(_requested_libraries):
        if library not in _to_install:
            _to_install = _to_install + (library,)
            # get the requirements.txt from bundle
            bundle = mod_names[library]["bundle"]
            requirements_txt = bundle.requirements_for(library)
            if requirements_txt:
                _requested_libraries.extend(
                    libraries_from_requirements(requirements_txt)
                )

            circup_dependencies = get_circup_dependencies(bundle, library)
            for circup_dependency in circup_dependencies:
                _requested_libraries.append(circup_dependency)

        # we've processed this library, remove it from the list
        _requested_libraries.remove(library)

        return get_dependencies(
            tuple(_requested_libraries), mod_names=mod_names, to_install=_to_install
        )


def get_circup_dependencies(bundle, library):
    """
    Get the list of circup dependencies from pyproject.toml
    e.g.
    [circup]
    circup_dependencies = ["dependency_name_here"]

    :param bundle: The Bundle to look within
    :param library: The Library to find pyproject.toml for and get dependencies from

    :return: The list of dependency libraries that were found
    """
    try:
        pyproj_toml = bundle.requirements_for(library, toml_file=True)
        if pyproj_toml:
            pyproj_toml_data = toml.loads(pyproj_toml)
            dependencies = pyproj_toml_data["circup"]["circup_dependencies"]
            if isinstance(dependencies, list):
                return dependencies

            if isinstance(dependencies, str):
                return (dependencies,)

        return tuple()

    except KeyError:
        # no circup_dependencies in pyproject.toml
        return tuple()


def get_latest_release_from_url(url):
    """
    Find the tag name of the latest release by using HTTP HEAD and decoding the redirect.

    :param str url: URL to the latest release page on a git repository.
    :return: The most recent tag value for the release.
    """

    logger.info("Requesting redirect information: %s", url)
    response = requests.head(url, timeout=REQUESTS_TIMEOUT)
    responseurl = response.url
    if response.is_redirect:
        responseurl = response.headers["Location"]
    tag = responseurl.rsplit("/", 1)[-1]
    logger.info("Tag: '%s'", tag)
    return tag


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
            # Remove everything after any pip style version specifiers
            line = re.split("[<>=~[;]", line)[0].strip()
            libraries = libraries + (line,)
    return libraries


def save_local_bundles(bundles_data):
    """
    Save the list of local bundles to the settings.

    :param str key: The bundle's identifier/key.
    """
    if len(bundles_data) > 0:
        with open(BUNDLE_CONFIG_LOCAL, "w", encoding="utf-8") as data:
            json.dump(bundles_data, data)
    else:
        if os.path.isfile(BUNDLE_CONFIG_LOCAL):
            os.unlink(BUNDLE_CONFIG_LOCAL)


def tags_data_load():
    """
    Load the list of the version tags of the bundles on disk.

    :return: a dict() of tags indexed by Bundle identifiers/keys.
    """
    tags_data = None
    try:
        with open(BUNDLE_DATA, encoding="utf-8") as data:
            try:
                tags_data = json.load(data)
            except json.decoder.JSONDecodeError as ex:
                # Sometimes (why?) the JSON file becomes corrupt. In which case
                # log it and carry on as if setting up for first time.
                logger.error("Could not parse %s", BUNDLE_DATA)
                logger.exception(ex)
    except FileNotFoundError:
        pass
    if not isinstance(tags_data, dict):
        tags_data = {}
    return tags_data


def tags_data_save_tag(key, tag):
    """
    Add or change the saved tag value for a bundle.

    :param str key: The bundle's identifier/key.
    :param str tag: The new tag for the bundle.
    """
    tags_data = tags_data_load()
    tags_data[key] = tag
    with open(BUNDLE_DATA, "w", encoding="utf-8") as data:
        json.dump(tags_data, data)


def libraries_from_code_py(code_py, mod_names):
    """
    Parse the given code.py file and return the imported libraries

    :param str code_py: Full path of the code.py file
    :return: sequence of library names
    """
    # pylint: disable=broad-except
    try:
        found_imports = findimports.find_imports(code_py)
    except Exception as ex:  # broad exception because anything could go wrong
        logger.exception(ex)
        click.secho('Unable to read the auto file: "{}"'.format(str(ex)), fg="red")
        sys.exit(2)
    # pylint: enable=broad-except
    imports = [info.name.split(".", 1)[0] for info in found_imports]
    return [r for r in imports if r in mod_names]


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
@click.option(
    "--host",
    help="Hostname or IP address of a device. Overrides automatic path detection.",
)
@click.option(
    "--password", help="Password to use for authentication when --host is used."
)
@click.option(
    "--timeout",
    default=30,
    help="Specify the timeout in seconds for any network operations.",
)
@click.option(
    "--board-id",
    default=None,
    help="Manual Board ID of the CircuitPython device. If provided in combination "
    "with --cpy-version, it overrides the detected board ID.",
)
@click.option(
    "--cpy-version",
    default=None,
    help="Manual CircuitPython version. If provided in combination "
    "with --board-id, it overrides the detected CPy version.",
)
@click.version_option(
    prog_name="CircUp",
    message="%(prog)s, A CircuitPython module updater. Version %(version)s",
)
@click.pass_context
def main(  # pylint: disable=too-many-locals
    ctx, verbose, path, host, password, timeout, board_id, cpy_version
):  # pragma: no cover
    """
    A tool to manage and update libraries on a CircuitPython device.
    """
    # pylint: disable=too-many-arguments,too-many-branches,too-many-statements,too-many-locals
    ctx.ensure_object(dict)
    global REQUESTS_TIMEOUT
    ctx.obj["TIMEOUT"] = REQUESTS_TIMEOUT = timeout
    device_path = get_device_path(host, password, path)

    using_webworkflow = "host" in ctx.params.keys() and ctx.params["host"] is not None

    if using_webworkflow:
        if host == "circuitpython.local":
            click.echo("Checking versions.json on circuitpython.local to find hostname")
            versions_resp = requests.get(
                "http://circuitpython.local/cp/version.json", timeout=timeout
            )
            host = f'{versions_resp.json()["hostname"]}.local'
            click.echo(f"Using hostname: {host}")
            device_path = device_path.replace("circuitpython.local", host)
        try:
            ctx.obj["backend"] = WebBackend(
                host=host, password=password, logger=logger, timeout=timeout
            )
        except ValueError as e:
            click.secho(e, fg="red")
            time.sleep(0.3)
            sys.exit(1)
        except RuntimeError as e:
            click.secho(e, fg="red")
            sys.exit(1)
    else:
        try:
            ctx.obj["backend"] = DiskBackend(device_path, logger)
        except ValueError as e:
            print(e)

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

    # If a newer version of circup is available, print a message.
    logger.info("Checking for a newer version of circup")
    version = get_circup_version()
    if version:
        update_checker.update_check("circup", version)

    # stop early if the command is boardless
    if ctx.invoked_subcommand in BOARDLESS_COMMANDS:
        return

    ctx.obj["DEVICE_PATH"] = device_path
    latest_version = get_latest_release_from_url(
        "https://github.com/adafruit/circuitpython/releases/latest"
    )
    global CPY_VERSION
    if device_path is None or not ctx.obj["backend"].is_device_present():
        click.secho("Could not find a connected CircuitPython device.", fg="red")
        sys.exit(1)
    else:
        CPY_VERSION, board_id = (
            ctx.obj["backend"].get_circuitpython_version()
            if board_id is None or cpy_version is None
            else (cpy_version, board_id)
        )
        click.echo(
            "Found device at {}, running CircuitPython {}.".format(
                device_path, CPY_VERSION
            )
        )
    try:
        if VersionInfo.parse(CPY_VERSION) < VersionInfo.parse(latest_version):
            click.secho(
                "A newer version of CircuitPython ({}) is available.".format(
                    latest_version
                ),
                fg="green",
            )
            if board_id:
                url_download = f"https://circuitpython.org/board/{board_id}"
            else:
                url_download = "https://circuitpython.org/downloads"
            click.secho("Get it here: {}".format(url_download), fg="green")
    except ValueError as ex:
        logger.warning("CircuitPython has incorrect semver value.")
        logger.warning(ex)


def get_device_path(host, password, path):
    """
    :param host Hostname or IP address.
    :param password REST API password.
    :param path File system path.
    :return device URL or None if the device cannot be found.
    """
    if path:
        device_path = path
    elif host:
        # pylint: enable=no-member
        device_path = f"http://:{password}@" + host
    else:
        device_path = find_device()
    return device_path


@main.command()
@click.option("-r", "--requirement", is_flag=True)
@click.pass_context
def freeze(ctx, requirement):  # pragma: no cover
    """
    Output details of all the modules found on the connected CIRCUITPYTHON
    device. Option -r saves output to requirements.txt file
    """
    logger.info("Freeze")
    modules = find_modules(ctx.obj["backend"], get_bundles_list())
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
            with open(
                cwd + "/" + "requirements.txt", "w", newline="\n", encoding="utf-8"
            ) as file:
                file.truncate(0)
                file.writelines(output)
    else:
        click.echo("No modules found on the device.")


@main.command("list")
@click.pass_context
def list_cli(ctx):  # pragma: no cover
    """
    Lists all out of date modules found on the connected CIRCUITPYTHON device.
    """
    logger.info("List")
    # Grab out of date modules.
    data = [("Module", "Version", "Latest", "Update Reason")]

    modules = [
        m.row
        for m in find_modules(ctx.obj["backend"], get_bundles_list())
        if m.outofdate
    ]
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
            "MPY Format changes from Circuitpython 6 to 7 require an update.\n"
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


# pylint: disable=too-many-arguments,too-many-locals
@main.command()
@click.argument(
    "modules", required=False, nargs=-1, shell_complete=completion_for_install
)
@click.option(
    "pyext",
    "--py",
    is_flag=True,
    help="Install the .py version of the module(s) instead of the mpy version.",
)
@click.option(
    "-r",
    "--requirement",
    type=click.Path(exists=True, dir_okay=False),
    help="specify a text file to install all modules listed in the text file."
    " Typically requirements.txt.",
)
@click.option(
    "--auto", "-a", is_flag=True, help="Install the modules imported in code.py."
)
@click.option(
    "--auto-file",
    default=None,
    help="Specify the name of a file on the board to read for auto install."
    " Also accepts an absolute path or a local ./ path.",
)
@click.pass_context
def install(ctx, modules, pyext, requirement, auto, auto_file):  # pragma: no cover
    """
    Install a named module(s) onto the device. Multiple modules
    can be installed at once by providing more than one module name, each
    separated by a space.
    """

    # TODO: Ensure there's enough space on the device
    available_modules = get_bundle_versions(get_bundles_list())
    mod_names = {}
    for module, metadata in available_modules.items():
        mod_names[module.replace(".py", "").lower()] = metadata
    if requirement:
        with open(requirement, "r", encoding="utf-8") as rfile:
            requirements_txt = rfile.read()
        requested_installs = libraries_from_requirements(requirements_txt)
    elif auto or auto_file:
        if auto_file is None:
            auto_file = "code.py"
            print(f"Auto file: {auto_file}")
        # pass a local file with "./" or "../"
        is_relative = not isinstance(ctx.obj["backend"], WebBackend) or auto_file.split(
            os.sep
        )[0] in [os.path.curdir, os.path.pardir]
        if not os.path.isabs(auto_file) and not is_relative:
            auto_file = ctx.obj["backend"].get_file_path(auto_file or "code.py")

        auto_file_path = ctx.obj["backend"].get_auto_file_path(auto_file)
        print(f"Auto file path: {auto_file_path}")
        if not os.path.isfile(auto_file_path):
            # fell through to here when run from random folder on windows - ask backend.
            new_auto_file = ctx.obj["backend"].get_file_path(auto_file)
            if os.path.isfile(new_auto_file):
                auto_file = new_auto_file
                auto_file_path = ctx.obj["backend"].get_auto_file_path(auto_file)
                print(f"Auto file path: {auto_file_path}")
            else:
                click.secho(f"Auto file not found: {auto_file}", fg="red")
                sys.exit(1)

        requested_installs = libraries_from_code_py(auto_file_path, mod_names)
    else:
        requested_installs = modules
    requested_installs = sorted(set(requested_installs))
    click.echo(f"Searching for dependencies for: {requested_installs}")
    to_install = get_dependencies(requested_installs, mod_names=mod_names)
    device_modules = ctx.obj["backend"].get_device_versions()
    if to_install is not None:
        to_install = sorted(to_install)
        click.echo(f"Ready to install: {to_install}\n")
        for library in to_install:
            ctx.obj["backend"].install_module(
                ctx.obj["DEVICE_PATH"], device_modules, library, pyext, mod_names
            )


# pylint: enable=too-many-arguments,too-many-locals


@main.command()
@click.argument("match", required=False, nargs=1)
def show(match):  # pragma: no cover
    """
    Show a list of available modules in the bundle. These are modules which
    *could* be installed on the device.

    If MATCH is specified only matching modules will be listed.
    """
    available_modules = get_bundle_versions(get_bundles_list())
    module_names = sorted([m.replace(".py", "") for m in available_modules])
    if match is not None:
        match = match.lower()
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
    device_path = ctx.obj["DEVICE_PATH"]
    print(f"Uninstalling {module} from {device_path}")
    for name in module:
        device_modules = ctx.obj["backend"].get_device_versions()
        name = name.lower()
        mod_names = {}
        for module_item, metadata in device_modules.items():
            mod_names[module_item.replace(".py", "").lower()] = metadata
        if name in mod_names:
            metadata = mod_names[name]
            module_path = metadata["path"]
            ctx.obj["backend"].uninstall(device_path, module_path)
            click.echo("Uninstalled '{}'.".format(name))
        else:
            click.echo("Module '{}' not found on device.".format(name))
        continue


# pylint: disable=too-many-branches


@main.command(
    short_help=(
        "Update modules on the device. "
        "Use --all to automatically update all modules without Major Version warnings."
    )
)
@click.option(
    "update_all",
    "--all",
    is_flag=True,
    help="Update all modules without Major Version warnings.",
)
@click.pass_context
# pylint: disable=too-many-locals
def update(ctx, update_all):  # pragma: no cover
    """
    Checks for out-of-date modules on the connected CIRCUITPYTHON device, and
    prompts the user to confirm updating such modules.
    """
    logger.info("Update")
    # Grab current modules.
    bundles_list = get_bundles_list()
    installed_modules = find_modules(ctx.obj["backend"], bundles_list)
    modules_to_update = [m for m in installed_modules if m.outofdate]

    if not modules_to_update:
        click.echo("None of the module[s] found on the device need an update.")
        return

    # Process out of date modules
    updated_modules = []
    click.echo("Found {} module[s] needing update.".format(len(modules_to_update)))
    if not update_all:
        click.echo("Please indicate which module[s] you wish to update:\n")
    for module in modules_to_update:
        update_flag = update_all
        if VERBOSE:
            click.echo(
                "Device version: {}, Bundle version: {}".format(
                    module.device_version, module.bundle_version
                )
            )
        if isinstance(module.bundle_version, str) and not VersionInfo.is_valid(
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
            if module.bad_format:
                click.secho(
                    f"WARNING: '{module.name}': module corrupted or in an"
                    " unknown mpy format. Updating is required.",
                    fg="yellow",
                )
                update_flag = click.confirm("Do you want to update?")
            elif module.mpy_mismatch:
                click.secho(
                    f"WARNING: '{module.name}': mpy format doesn't match the"
                    " device's Circuitpython version. Updating is required.",
                    fg="yellow",
                )
                update_flag = click.confirm("Do you want to update?")
            elif module.major_update:
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
                ctx.obj["backend"].update(module)
                updated_modules.append(module.name)
                click.echo("Updated {}".format(module.name))
            except Exception as ex:
                logger.exception(ex)
                click.echo("Something went wrong, {} (check the logs)".format(str(ex)))
            # pylint: enable=broad-except

    if not updated_modules:
        return

    # We updated modules, look to see if any requirements are missing
    click.echo(
        "Checking {} updated module[s] for missing requirements.".format(
            len(updated_modules)
        )
    )
    available_modules = get_bundle_versions(bundles_list)
    mod_names = {}
    for module, metadata in available_modules.items():
        mod_names[module.replace(".py", "").lower()] = metadata
    missing_modules = get_dependencies(updated_modules, mod_names=mod_names)
    device_modules = ctx.obj["backend"].get_device_versions()
    # Process newly needed modules
    if missing_modules is not None:
        installed_module_names = [m.name for m in installed_modules]
        missing_modules = set(missing_modules) - set(installed_module_names)
        missing_modules = sorted(list(missing_modules))
        click.echo(f"Ready to install: {missing_modules}\n")
        for library in missing_modules:
            ctx.obj["backend"].install_module(
                ctx.obj["DEVICE_PATH"], device_modules, library, False, mod_names
            )


# pylint: enable=too-many-branches


@main.command("bundle-show")
@click.option("--modules", is_flag=True, help="List all the modules per bundle.")
def bundle_show(modules):
    """
    Show the list of bundles, default and local, with URL, current version
    and latest version retrieved from the web.
    """
    local_bundles = get_bundles_local_dict().values()
    bundles = get_bundles_list()
    available_modules = get_bundle_versions(bundles)

    for bundle in bundles:
        if bundle.key in local_bundles:
            click.secho(bundle.key, fg="yellow")
        else:
            click.secho(bundle.key, fg="green")
        click.echo("    " + bundle.url)
        click.echo("    version = " + bundle.current_tag)
        if modules:
            click.echo("Modules:")
            for name, mod in sorted(available_modules.items()):
                if mod["bundle"] == bundle:
                    click.echo(f"   {name} ({mod.get('__version__', '-')})")


@main.command("bundle-add")
@click.argument("bundle", nargs=-1)
def bundle_add(bundle):
    """
    Add bundles to the local bundles list, by "user/repo" github string.
    A series of tests to validate that the bundle exists and at least looks
    like a bundle are done before validating it. There might still be errors
    when the bundle is downloaded for the first time.
    """
    bundles_dict = get_bundles_local_dict()
    modified = False
    for bundle_repo in bundle:
        # cleanup in case seombody pastes the URL to the repo/releases
        bundle_repo = re.sub(
            r"https?://github.com/([^/]+/[^/]+)(/.*)?", r"\1", bundle_repo
        )
        if bundle_repo in bundles_dict.values():
            click.secho("Bundle already in list.", fg="yellow")
            click.secho("    " + bundle_repo, fg="yellow")
            continue
        try:
            bundle_added = Bundle(bundle_repo)
        except ValueError:
            click.secho(
                "Bundle string invalid, expecting github URL or `user/repository` string.",
                fg="red",
            )
            click.secho("    " + bundle_repo, fg="red")
            continue
        result = requests.get(
            "https://github.com/" + bundle_repo, timeout=REQUESTS_TIMEOUT
        )
        # pylint: disable=no-member
        if result.status_code == requests.codes.NOT_FOUND:
            click.secho("Bundle invalid, the repository doesn't exist (404).", fg="red")
            click.secho("    " + bundle_repo, fg="red")
            continue
        # pylint: enable=no-member
        if not bundle_added.validate():
            click.secho(
                "Bundle invalid, is the repository a valid circup bundle ?", fg="red"
            )
            click.secho("    " + bundle_repo, fg="red")
            continue
        # note: use bun as the dictionary key for uniqueness
        bundles_dict[bundle_repo] = bundle_repo
        modified = True
        click.echo("Added " + bundle_repo)
        click.echo("    " + bundle_added.url)
    if modified:
        # save the bundles list
        save_local_bundles(bundles_dict)
        # update and get the new bundles for the first time
        get_bundle_versions(get_bundles_list())


@main.command("bundle-remove")
@click.argument("bundle", nargs=-1)
@click.option("--reset", is_flag=True, help="Remove all local bundles.")
def bundle_remove(bundle, reset):
    """
    Remove one or more bundles from the local bundles list.
    """
    if reset:
        save_local_bundles({})
        return
    bundle_config = list(get_bundles_dict().values())
    bundles_local_dict = get_bundles_local_dict()
    modified = False
    for bun in bundle:
        # cleanup in case seombody pastes the URL to the repo/releases
        bun = re.sub(r"https?://github.com/([^/]+/[^/]+)(/.*)?", r"\1", bun)
        found = False
        for name, repo in list(bundles_local_dict.items()):
            if bun in (name, repo):
                found = True
                click.secho(f"Bundle {repo}")
                do_it = click.confirm("Do you want to remove that bundle ?")
                if do_it:
                    click.secho("Removing the bundle from the local list", fg="yellow")
                    click.secho(f"    {bun}", fg="yellow")
                    modified = True
                    del bundles_local_dict[name]
        if not found:
            if bun in bundle_config:
                click.secho("Cannot remove built-in module:" "\n    " + bun, fg="red")
            else:
                click.secho(
                    "Bundle not found in the local list, nothing removed:"
                    "\n    " + bun,
                    fg="red",
                )
    if modified:
        save_local_bundles(bundles_local_dict)


# Allows execution via `python -m circup ...`
# pylint: disable=no-value-for-parameter
if __name__ == "__main__":  # pragma: no cover
    main()
