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
import re
import shutil
from subprocess import check_output
import sys
import zipfile

import appdirs
import click
import findimports
import requests
from semver import VersionInfo


# Useful constants.
#: Flag to indicate if the command is being run in verbose mode.
VERBOSE = False
#: The location of data files used by circup (following OS conventions).
DATA_DIR = appdirs.user_data_dir(appname="circup", appauthor="adafruit")
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
    "pyserial",
]
#: The version of CircuitPython found on the connected device.
CPY_VERSION = ""
#: Adafruit bundle repository
BUNDLE_ADAFRUIT = "adafruit/Adafruit_CircuitPython_Bundle"
#: Community bundle repository
BUNDLE_COMMUNITY = "adafruit/CircuitPython_Community_Bundle"
#: CircuitPython Organization bundle repository
BUNDLE_CIRCUITPYTHON_ORG = "circuitpython/CircuitPython_Org_Bundle"
#: Default bundle repository list
BUNDLES_DEFAULT_LIST = [BUNDLE_ADAFRUIT, BUNDLE_COMMUNITY, BUNDLE_CIRCUITPYTHON_ORG]
#: Module formats list (and the other form used in github files)
PLATFORMS = {"py": "py", "6mpy": "6.x-mpy", "7mpy": "7.x-mpy"}


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
        self.url = "https://github.com/" + repo + "/releases"
        self.basename = bundle_id + "-{platform}-{tag}"
        self.urlzip = self.basename + ".zip"
        self.dir = os.path.join(DATA_DIR, vendor, bundle_id + "-{platform}")
        self.zip = os.path.join(DATA_DIR, bundle_id + "-{platform}.zip")
        self.url_format = self.url + "/download/{tag}/" + self.urlzip
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

    def requirements_for(self, library_name):
        """
        The requirements file for this library.

        :param str library_name: The name of the library.
        :return: The path to the requirements.txt file.
        """
        platform = "py"
        tag = self.current_tag
        requirements_txt = os.path.join(
            self.dir.format(platform=platform),
            self.basename.format(platform=PLATFORMS[platform], tag=tag),
            "requirements",
            library_name,
            "requirements.txt",
        )
        if os.path.isfile(requirements_txt):
            with open(requirements_txt, "r") as read_this:
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
            self._latest = get_latest_release_from_url(self.url + "/latest")
        return self._latest

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
        self, path, repo, device_version, bundle_version, mpy, bundle, compatibility
    ):
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
        :param Bundle bundle: Bundle object where the module is located.
        :param (str,str) compatibility: Min and max versions of CP compatible with the mpy.
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
                    "There was a problem downloading the bundle. "
                    "Please try again in a moment."
                ),
                fg="red",
            )
            logger.exception(ex)
            sys.exit(1)
    else:
        logger.info("Current bundle up to date %s.", tag)


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
    elif path.endswith(".mpy"):
        result["mpy"] = True
        with open(path, "rb") as mpy_file:
            content = mpy_file.read()
        # Track the MPY version number
        mpy_version = content[0:2]
        compatibility = None
        # Find the start location of the __version__
        if mpy_version == b"M\x03":
            # One byte for the length of "__version__"
            loc = content.find(b"__version__") - 1
            compatibility = (None, "7.0.0-alpha.1")
        elif mpy_version == b"C\x05":
            # Two bytes in mpy version 5
            loc = content.find(b"__version__") - 2
            compatibility = ("7.0.0-alpha.1", None)
        if loc > -1:
            # Backtrack until a byte value of the offset is reached.
            offset = 1
            while offset < loc:
                val = int(content[loc - offset])
                if mpy_version == b"C\x05":
                    val = val // 2
                if val == offset - 1:  # Off by one..!
                    # Found version, extract the number given boundaries.
                    start = loc - offset + 1  # No need for prepended length.
                    end = loc  # Up to the start of the __version__.
                    version = content[start:end]  # Slice the version number.
                    # Create a string version as metadata in the result.
                    result = {"__version__": version.decode("utf-8"), "mpy": True}
                    break  # Nothing more to do.
                offset += 1  # ...and again but backtrack by one.
        if compatibility:
            result["compatibility"] = compatibility
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


def find_modules(device_path, bundles_list):
    """
    Extracts metadata from the connected device and available bundles and
    returns this as a list of Module instances representing the modules on the
    device.

    :param str device_path: The path to the connected board.
    :param Bundle bundles_list: List of supported bundles as Bundle objects.
    :return: A list of Module instances describing the current state of the
             modules on the connected device.
    """
    # pylint: disable=broad-except,too-many-locals
    try:
        device_modules = get_device_versions(device_path)
        bundle_modules = get_bundle_versions(bundles_list)
        result = []
        for name, device_metadata in device_modules.items():
            if name in bundle_modules:
                path = device_metadata["path"]
                bundle_metadata = bundle_modules[name]
                repo = bundle_metadata.get("__repo__")
                bundle = bundle_metadata.get("bundle")
                device_version = device_metadata.get("__version__")
                bundle_version = bundle_metadata.get("__version__")
                mpy = device_metadata["mpy"]
                compatibility = device_metadata.get("compatibility", (None, None))
                result.append(
                    Module(
                        path,
                        repo,
                        device_version,
                        bundle_version,
                        mpy,
                        bundle,
                        compatibility,
                    )
                )
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
    click.echo("Downloading latest version for {}.\n".format(bundle.key))
    for platform in PLATFORMS:
        url = bundle.url_format.format(platform=PLATFORMS[platform], tag=tag)
        logger.info("Downloading bundle: %s", url)
        r = requests.get(url, stream=True)
        # pylint: disable=no-member
        if r.status_code != requests.codes.ok:
            logger.warning("Unable to connect to %s", url)
            r.raise_for_status()
        # pylint: enable=no-member
        total_size = int(r.headers.get("Content-Length"))
        temp_zip = bundle.zip.format(platform=platform)
        with click.progressbar(r.iter_content(1024), length=total_size) as pbar, open(
            temp_zip, "wb"
        ) as f:
            for chunk in pbar:
                f.write(chunk)
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

    :param Bundle bundles_list: List of supported bundles as Bundle objects.
    :param bool avoid_download: if True, download the bundle only if missing.
    :return: A dictionary of metadata about the modules available in the
             library bundle.
    """
    all_the_modules = dict()
    for bundle in bundles_list:
        if not avoid_download or not os.path.isdir(bundle.lib_dir("py")):
            ensure_latest_bundle(bundle)
        path = bundle.lib_dir("py")
        path_modules = get_modules(path)
        for name, module in path_modules.items():
            module["bundle"] = bundle
            if name not in all_the_modules:  # here we decide the order of priority
                all_the_modules[name] = module
    return all_the_modules


def get_bundles_list():
    """
    Retrieve the list of bundles. Currently uses the fixed list.
    The goal is to implement reading from a configuration file.
    https://github.com/adafruit/circup/issues/82#issuecomment-843368130

    :return: List of supported bundles as Bundle objects.
    """
    bundles_list = [Bundle(b) for b in BUNDLES_DEFAULT_LIST]
    logger.info("Using bundles: %s", ", ".join([b.key for b in bundles_list]))
    # TODO: this is were we retrieve the bundles list from json
    return bundles_list


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
            bundle = mod_names[library]["bundle"]
            requirements_txt = bundle.requirements_for(library)
            if requirements_txt:
                _requested_libraries.extend(
                    libraries_from_requirements(requirements_txt)
                )
        # we've processed this library, remove it from the list
        _requested_libraries.remove(library)

        return get_dependencies(
            tuple(_requested_libraries), mod_names=mod_names, to_install=_to_install
        )


def get_device_versions(device_path):
    """
    Returns a dictionary of metadata from modules on the connected device.

    :param str device_path: Path to the device volume.
    :return: A dictionary of metadata about the modules available on the
             connected device.
    """
    return get_modules(os.path.join(device_path, "lib"))


def get_latest_release_from_url(url):
    """
    Find the tag name of the latest release by using HTTP HEAD and decoding the redirect.

    :param str url: URL to the latest release page on a git repository.
    :return: The most recent tag value for the release.
    """

    logger.info("Requesting redirect information: %s", url)
    response = requests.head(url)
    responseurl = response.url
    if response.is_redirect:
        responseurl = response.headers["Location"]
    tag = responseurl.rsplit("/", 1)[-1]
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


# pylint: disable=too-many-locals,too-many-branches
def install_module(
    device_path, device_modules, name, py, mod_names
):  # pragma: no cover
    """
    Finds a connected device and installs a given module name if it
    is available in the current module bundle and is not already
    installed on the device.
    TODO: There is currently no check for the version.

    :param str device_path: The path to the connected board.
    :param list(dict) device_modules: List of module metadata from the device.
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
        bundle = metadata["bundle"]
        # Grab device modules to check if module already installed
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
            bundle_path = os.path.join(bundle.lib_dir(bundle_platform), module_name)
            if os.path.isdir(bundle_path):
                target_path = os.path.join(library_path, module_name)
                # Copy the directory.
                shutil.copytree(bundle_path, target_path)
            elif os.path.isfile(bundle_path):
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


def libraries_from_imports(code_py, mod_names):
    """
    Parse the given code.py file and return the imported libraries

    :param str code_py: Full path of the code.py file
    :return: sequence of library names
    """
    imports = [info.name.split(".", 1)[0] for info in findimports.find_imports(code_py)]
    return [r for r in imports if r in mod_names]


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
    latest_version = get_latest_release_from_url(
        "https://github.com/adafruit/circuitpython/releases/latest"
    )
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
    modules = find_modules(ctx.obj["DEVICE_PATH"], get_bundles_list())
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
    data = [("Module", "Version", "Latest", "Update Reason")]

    modules = [
        m.row
        for m in find_modules(ctx.obj["DEVICE_PATH"], get_bundles_list())
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
@click.option("--py", is_flag=True)
@click.option("-r", "--requirement")
@click.option("--auto/--no-auto", "-a/-A")
@click.option("--auto-file", default="code.py")
@click.pass_context
def install(ctx, modules, py, requirement, auto, auto_file):  # pragma: no cover
    """
    Install a named module(s) onto the device. Multiple modules
    can be installed at once by providing more than one module name, each
    separated by a space.

    Option --py installs .py version of module(s).

    Option -r allows specifying a text file to install all modules listed in
    the text file.

    Option -a installs based on the modules imported by code.py
    """
    # TODO: Ensure there's enough space on the device
    available_modules = get_bundle_versions(get_bundles_list())
    mod_names = {}
    for module, metadata in available_modules.items():
        mod_names[module.replace(".py", "").lower()] = metadata
    if requirement:
        cwd = os.path.abspath(os.getcwd())
        requirements_txt = open(cwd + "/" + requirement, "r").read()
        requested_installs = libraries_from_requirements(requirements_txt)
    elif auto:
        auto_file = os.path.join(ctx.obj["DEVICE_PATH"], auto_file)
        requested_installs = libraries_from_imports(auto_file, mod_names)
    else:
        requested_installs = modules
    requested_installs = sorted(set(requested_installs))
    click.echo(f"Searching for dependencies for: {requested_installs}")
    to_install = get_dependencies(requested_installs, mod_names=mod_names)
    device_modules = get_device_versions(ctx.obj["DEVICE_PATH"])
    if to_install is not None:
        to_install = sorted(to_install)
        click.echo(f"Ready to install: {to_install}\n")
        for library in to_install:
            install_module(
                ctx.obj["DEVICE_PATH"], device_modules, library, py, mod_names
            )


# pylint: enable=too-many-arguments,too-many-locals


@click.argument("match", required=False, nargs=1)
@main.command()
def show(match):  # pragma: no cover
    """
    Show a list of available modules in the bundle. These are modules which
    *could* be installed on the device.

    If MATCH is specified only matching modules will be listed.
    """
    available_modules = get_bundle_versions(get_bundles_list())
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
    modules = [
        m
        for m in find_modules(ctx.obj["DEVICE_PATH"], get_bundles_list())
        if m.outofdate
    ]
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
                if module.mpy_mismatch:
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
                    module.update()
                    click.echo("Updated {}".format(module.name))
                except Exception as ex:
                    logger.exception(ex)
                    click.echo(
                        "Something went wrong, {} (check the logs)".format(str(ex))
                    )
                # pylint: enable=broad-except
        return
    click.echo("None of the modules found on the device need an update.")


# Allows execution via `python -m circup ...`
# pylint: disable=no-value-for-parameter
if __name__ == "__main__":  # pragma: no cover
    main()
