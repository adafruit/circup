import os
from urllib.parse import urljoin, urlparse

import click
import requests
from semver import VersionInfo

from circup.shared import DATA_DIR, PLATFORMS, REQUESTS_TIMEOUT, BAD_FILE_FORMAT, tags_data_load, \
    get_latest_release_from_url
from circup.backends import WebBackend
from circup.logging import logger

#: Flag to indicate if the command is being run in verbose mode.
VERBOSE = False

#: The version of CircuitPython found on the connected device.
CPY_VERSION = ""


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
            self._current = tags_data_load(logger).get(self.key, "0")
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
            self._latest = get_latest_release_from_url(self.url + "/releases/latest", logger)
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
