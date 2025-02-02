# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, written for Adafruit Industries
# SPDX-FileCopyrightText: 2023 Tim Cocks, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
Backend classes that represent interfaces to physical devices.
"""
import os
import shutil
import sys
import socket
import tempfile
from urllib.parse import urlparse, urljoin
import click
import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

from circup.shared import DATA_DIR, BAD_FILE_FORMAT, extract_metadata, _get_modules_file

#: The location to store a local copy of code.py for use with --auto and
#  web workflow
LOCAL_CODE_PY_COPY = os.path.join(DATA_DIR, "code.tmp.py")


class Backend:
    """
    Backend parent class to be extended for workflow specific
    implementations
    """

    def __init__(self, logger, version_override=None):
        self.device_location = None
        self.LIB_DIR_PATH = None
        self.version_override = version_override
        self.logger = logger

    def get_circuitpython_version(self):
        """
        Must be overridden by subclass for implementation!

        Returns the version number of CircuitPython running on the board connected
        via ``device_url``, along with the board ID.

        :param str device_location: http based device URL or local file path.
        :return: A tuple with the version string for CircuitPython and the board ID string.
        """
        raise NotImplementedError

    def _get_modules(self, device_lib_path):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def get_modules(self, device_url):
        """
        Get a dictionary containing metadata about all the Python modules found in
        the referenced path.

        :param str device_url: URL to be used to find modules.
        :return: A dictionary containing metadata about the found modules.
        """
        return self._get_modules(device_url)

    def get_device_versions(self):
        """
        Returns a dictionary of metadata from modules on the connected device.

        :param str device_url: URL for the device.
        :return: A dictionary of metadata about the modules available on the
                 connected device.
        """
        return self.get_modules(os.path.join(self.device_location, self.LIB_DIR_PATH))

    def create_directory(self, device_path, directory):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def install_module_py(self, metadata, location=None):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def install_module_mpy(self, bundle, metadata):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def copy_file(self, target_file, location_to_paste):
        """Paste a copy of the specified file at the location given
        To be overridden by subclass
        """
        raise NotImplementedError

    def upload_file(self, target_file, location_to_paste):
        """Paste a copy of the specified file at the location given
        To be overridden by subclass
        """
        raise NotImplementedError

    # pylint: disable=too-many-locals,too-many-branches,too-many-arguments,too-many-nested-blocks,too-many-statements
    def install_module(
        self, device_path, device_modules, name, pyext, mod_names, upgrade=False
    ):  # pragma: no cover
        """
        Finds a connected device and installs a given module name if it
        is available in the current module bundle and is not already
        installed on the device.
        TODO: There is currently no check for the version.

        :param str device_path: The path to the connected board.
        :param list(dict) device_modules: List of module metadata from the device.
        :param str name: Name of module to install
        :param bool pyext: Boolean to specify if the module should be installed from
                        source or from a pre-compiled module
        :param mod_names: Dictionary of metadata from modules that can be generated
                           with get_bundle_versions()
        :param bool upgrade: Upgrade the specified modules if they're already installed.
        """
        local_path = None
        if os.path.exists(name):
            # local file exists use that.
            local_path = name
            name = local_path.split(os.path.sep)[-1]
            name = name.replace(".py", "").replace(".mpy", "")
            click.echo(f"Installing from local path: {local_path}")

        if not name:
            click.echo("No module name(s) provided.")
            return
        if name in mod_names or local_path is not None:

            # Grab device modules to check if module already installed
            if name in device_modules:
                if not upgrade:
                    # skip already installed modules if no -upgrade flag
                    click.echo("'{}' is already installed.".format(name))
                    return

                # uninstall the module before installing
                name = name.lower()
                _mod_names = {}
                for module_item, _metadata in device_modules.items():
                    _mod_names[module_item.replace(".py", "").lower()] = _metadata
                if name in _mod_names:
                    _metadata = _mod_names[name]
                    module_path = _metadata["path"]
                    self.uninstall(device_path, module_path)

            new_module_size = 0
            library_path = (
                os.path.join(device_path, self.LIB_DIR_PATH)
                if not isinstance(self, WebBackend)
                else urljoin(device_path, self.LIB_DIR_PATH)
            )
            if local_path is None:
                metadata = mod_names[name]
                bundle = metadata["bundle"]
            else:
                metadata = {"path": local_path}

            new_module_size = os.path.getsize(metadata["path"])
            if os.path.isdir(metadata["path"]):
                # pylint: disable=unused-variable
                for dirpath, dirnames, filenames in os.walk(metadata["path"]):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            if not os.path.islink(fp):  # Ignore symbolic links
                                new_module_size += os.path.getsize(fp)
                            else:
                                self.logger.warning(
                                    f"Skipping symbolic link in space calculation: {fp}"
                                )
                        except OSError as e:
                            self.logger.error(
                                f"Error: {e} - Skipping file in space calculation: {fp}"
                            )

            if self.get_free_space() < new_module_size:
                self.logger.error(
                    f"Aborted installing module {name} - "
                    f"not enough free space ({new_module_size} < {self.get_free_space()})"
                )
                click.secho(
                    f"Aborted installing module {name} - "
                    f"not enough free space ({new_module_size} < {self.get_free_space()})",
                    fg="red",
                )
                return

            # Create the library directory first.
            self.create_directory(device_path, library_path)
            if local_path is None:
                if pyext:
                    # Use Python source for module.
                    self.install_module_py(metadata)
                else:
                    # Use pre-compiled mpy modules.
                    self.install_module_mpy(bundle, metadata)
            else:
                self.copy_file(metadata["path"], "lib")
            click.echo("Installed '{}'.".format(name))
        else:
            click.echo("Unknown module named, '{}'.".format(name))

    # def libraries_from_imports(self, code_py, mod_names):
    #     """
    #     To be overridden by subclass
    #     """
    #     raise NotImplementedError

    def uninstall(self, device_path, module_path):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def update(self, module):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def get_file_path(self, filename):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def get_file_content(self, target_file):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def get_free_space(self):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def is_device_present(self):
        """
        To be overriden by subclass
        """
        raise NotImplementedError

    @staticmethod
    def parse_boot_out_file(boot_out_contents):
        """
        Parse the contents of boot_out.txt
        Returns: circuitpython version and board id
        """
        lines = boot_out_contents.split("\n")
        version_line = lines[0]
        circuit_python = version_line.split(";")[0].split(" ")[-3]
        board_line = lines[1]
        if board_line.startswith("Board ID:"):
            board_id = board_line[9:].strip()
        else:
            board_id = ""
        return circuit_python, board_id

    def file_exists(self, filepath):
        """
        To be overriden by subclass
        """
        raise NotImplementedError


def _writeable_error():
    click.secho(
        "CircuitPython Web Workflow Device not writable\n - "
        "Remount storage as writable to device (not PC)",
        fg="red",
    )
    sys.exit(1)


class WebBackend(Backend):
    """
    Backend for interacting with a device via Web Workflow
    """

    def __init__(  # pylint: disable=too-many-arguments
        self, host, port, password, logger, timeout=10, version_override=None
    ):
        super().__init__(logger)
        if password is None:
            raise ValueError(
                "Must pass --password or set CIRCUP_WEBWORKFLOW_PASSWORD environment variable"
            )

        # pylint: disable=no-member
        # verify hostname/address
        try:
            socket.getaddrinfo(host, 80, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise RuntimeError(
                "Invalid host: {}.".format(host) + " You should remove the 'http://'"
                if "http://" in host or "https://" in host
                else "Could not find or connect to specified device"
            ) from exc

        self.FS_PATH = "fs/"
        self.LIB_DIR_PATH = f"{self.FS_PATH}lib/"
        self.host = host
        self.port = port
        self.password = password
        self.device_location = f"http://:{self.password}@{self.host}:{self.port}"

        self.session = requests.Session()
        self.session.mount(self.device_location, HTTPAdapter(max_retries=5))
        self.library_path = self.device_location + "/" + self.LIB_DIR_PATH
        self.timeout = timeout
        self.version_override = version_override
        self.FS_URL = urljoin(self.device_location, self.FS_PATH)

    def __repr__(self):
        return f"<WebBackend @{self.device_location}>"

    def install_file_http(self, source, location=None):
        """
        Install file to device using web workflow.
        :param source source file.
        :param location the location on the device to copy the source
          directory in to. If omitted is CIRCUITPY/lib/ used.
        """
        file_name = source.split(os.path.sep)
        file_name = file_name[-2] if file_name[-1] == "" else file_name[-1]

        if location is None:
            target = self.device_location + "/" + self.LIB_DIR_PATH + file_name
        else:
            target = self.device_location + "/" + self.FS_PATH + location + file_name

        auth = HTTPBasicAuth("", self.password)

        with open(source, "rb") as fp:
            r = self.session.put(target, fp.read(), auth=auth, timeout=self.timeout)
            if r.status_code == 409:
                _writeable_error()
            r.raise_for_status()

    def install_dir_http(self, source, location=None):
        """
        Install directory to device using web workflow.
        :param source source directory.
        :param location the location on the device to copy the source
          directory in to. If omitted is CIRCUITPY/lib/ used.
        """
        mod_name = source.split(os.path.sep)
        mod_name = mod_name[-2] if mod_name[-1] == "" else mod_name[-1]
        if location is None:
            target = self.device_location + "/" + self.LIB_DIR_PATH + mod_name
        else:
            target = self.device_location + "/" + self.FS_PATH + location + mod_name
        target = target + "/" if target[:-1] != "/" else target
        url = urlparse(target)
        auth = HTTPBasicAuth("", url.password)

        # Create the top level directory.
        with self.session.put(target, auth=auth, timeout=self.timeout) as r:
            if r.status_code == 409:
                _writeable_error()
            r.raise_for_status()

        # Traverse the directory structure and create the directories/files.
        for root, dirs, files in os.walk(source):
            rel_path = os.path.relpath(root, source)
            if rel_path == ".":
                rel_path = ""
            for name in dirs:
                path_to_create = (
                    urljoin(
                        urljoin(target, rel_path + "/", allow_fragments=False),
                        name,
                        allow_fragments=False,
                    )
                    if rel_path != ""
                    else urljoin(target, name, allow_fragments=False)
                )
                path_to_create = (
                    path_to_create + "/"
                    if path_to_create[:-1] != "/"
                    else path_to_create
                )

                with self.session.put(
                    path_to_create, auth=auth, timeout=self.timeout
                ) as r:
                    if r.status_code == 409:
                        _writeable_error()
                    r.raise_for_status()
            for name in files:
                with open(os.path.join(root, name), "rb") as fp:
                    path_to_create = (
                        urljoin(
                            urljoin(target, rel_path + "/", allow_fragments=False),
                            name,
                            allow_fragments=False,
                        )
                        if rel_path != ""
                        else urljoin(target, name, allow_fragments=False)
                    )
                    with self.session.put(
                        path_to_create, fp.read(), auth=auth, timeout=self.timeout
                    ) as r:
                        if r.status_code == 409:
                            _writeable_error()
                        r.raise_for_status()

    def get_circuitpython_version(self):
        """
        Returns the version number of CircuitPython running on the board connected
        via ``device_path``, along with the board ID. This is obtained using
        RESTful API from the /cp/version.json URL.

        :return: A tuple with the version string for CircuitPython and the board ID string.
        """
        if self.version_override is not None:
            return self.version_override

        # pylint: disable=arguments-renamed
        with self.session.get(
            self.device_location + "/cp/version.json", timeout=self.timeout
        ) as r:
            # pylint: disable=no-member
            if r.status_code != requests.codes.ok:
                click.secho(
                    f"  Unable to get version from {self.device_location}: {r.status_code}",
                    fg="red",
                )
                sys.exit(1)
            # pylint: enable=no-member
            ver_json = r.json()
        return ver_json.get("version"), ver_json.get("board_id")

    def _get_modules(self, device_lib_path):
        return self._get_modules_http(device_lib_path)

    def _get_modules_http(self, url):
        """
        Get a dictionary containing metadata about all the Python modules found using
        the referenced URL.

        :param str url: URL for the modules.
        :return: A dictionary containing metadata about the found modules.
        """
        result = {}
        u = urlparse(url)
        auth = HTTPBasicAuth("", u.password)
        with self.session.get(
            url, auth=auth, headers={"Accept": "application/json"}, timeout=self.timeout
        ) as r:
            r.raise_for_status()

            directory_mods = []
            single_file_mods = []

            for entry in r.json()["files"]:

                entry_name = entry.get("name")
                if entry.get("directory"):
                    directory_mods.append(entry_name)
                else:
                    if entry_name.endswith(".py") or entry_name.endswith(".mpy"):
                        single_file_mods.append(entry_name)

        self._get_modules_http_single_mods(auth, result, single_file_mods, url)
        self._get_modules_http_dir_mods(auth, directory_mods, result, url)

        return result

    def _get_modules_http_dir_mods(self, auth, directory_mods, result, url):
        # pylint: disable=too-many-locals
        """
        Builds result dictionary with keys containing module names and values containing a
        dictionary with metadata bout the module like version, compatibility, mpy or not etc.

        :param auth HTTP authentication.
        :param directory_mods list of modules.
        :param result dictionary for the result.
        :param url: URL of the device.
        """
        for dm in directory_mods:
            if str(urlparse(dm).scheme).lower() not in ("http", "https"):
                dm_url = url + dm + "/"
            else:
                dm_url = dm

            with self.session.get(
                dm_url,
                auth=auth,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            ) as r:
                r.raise_for_status()
                mpy = False

                for entry in r.json()["files"]:
                    entry_name = entry.get("name")
                    if not entry.get("directory") and (
                        entry_name.endswith(".py") or entry_name.endswith(".mpy")
                    ):
                        if entry_name.endswith(".mpy"):
                            mpy = True

                        with self.session.get(
                            dm_url + entry_name, auth=auth, timeout=self.timeout
                        ) as rr:
                            rr.raise_for_status()
                            idx = entry_name.rfind(".")
                            with tempfile.NamedTemporaryFile(
                                prefix=entry_name[:idx] + "-",
                                suffix=entry_name[idx:],
                                delete=False,
                            ) as fp:
                                fp.write(rr.content)
                                tmp_name = fp.name
                        metadata = extract_metadata(tmp_name, self.logger)
                        os.remove(tmp_name)
                        if "__version__" in metadata:
                            metadata["path"] = dm_url
                            result[dm] = metadata
                            # break now if any of the submodules has a bad format
                            if metadata["__version__"] == BAD_FILE_FORMAT:
                                break

            if result.get(dm) is None:
                result[dm] = {"path": dm_url, "mpy": mpy}

    def _get_modules_http_single_mods(self, auth, result, single_file_mods, url):
        """
        :param auth HTTP authentication.
        :param single_file_mods list of modules.
        :param result dictionary for the result.
        :param url: URL of the device.
        """
        for sfm in single_file_mods:
            if str(urlparse(sfm).scheme).lower() not in ("http", "https"):
                sfm_url = url + sfm
            else:
                sfm_url = sfm
            with self.session.get(sfm_url, auth=auth, timeout=self.timeout) as r:
                r.raise_for_status()
                idx = sfm.rfind(".")
                with tempfile.NamedTemporaryFile(
                    prefix=sfm[:idx] + "-", suffix=sfm[idx:], delete=False
                ) as fp:
                    fp.write(r.content)
                    tmp_name = fp.name
            metadata = extract_metadata(tmp_name, self.logger)
            os.remove(tmp_name)
            metadata["path"] = sfm_url
            result[sfm[:idx]] = metadata

    def create_directory(self, device_path, directory):
        auth = HTTPBasicAuth("", self.password)
        with self.session.put(directory, auth=auth, timeout=self.timeout) as r:
            if r.status_code == 409:
                _writeable_error()
            r.raise_for_status()

    def copy_file(self, target_file, location_to_paste):
        if os.path.isdir(target_file):
            create_directory_url = urljoin(
                self.device_location,
                "/".join(("fs", location_to_paste, target_file, "")),
            )
            self.create_directory(self.device_location, create_directory_url)
            self.install_dir_http(target_file)
        else:
            self.install_file_http(target_file)

    def upload_file(self, target_file, location_to_paste):
        """
        copy a file from the host PC to the microcontroller
        :param target_file: file on the host PC to copy
        :param location_to_paste: Location on the microcontroller to paste it.
        :return:
        """
        if os.path.isdir(target_file):
            create_directory_url = urljoin(
                self.device_location,
                "/".join(("fs", location_to_paste, target_file, "")),
            )
            self.create_directory(self.device_location, create_directory_url)
            self.install_dir_http(target_file, location_to_paste)
        else:
            self.install_file_http(target_file, location_to_paste)

    def download_file(self, target_file, location_to_paste):
        """
        Download a file from the MCU device to the local host PC
        :param target_file: The file on the MCU to download
        :param location_to_paste: The location on the host PC to put the downloaded copy.
        :return:
        """
        auth = HTTPBasicAuth("", self.password)
        with self.session.get(
            self.FS_URL + target_file, timeout=self.timeout, auth=auth
        ) as r:
            if r.status_code == 404:
                click.secho(f"{target_file} was not found on the device", "red")

            file_name = target_file.split("/")[-1]
            if location_to_paste is None:
                with open(file_name, "wb") as f:
                    f.write(r.content)

                click.echo(f"Downloaded File: {file_name}")
            else:
                with open(os.path.join(location_to_paste, file_name), "wb") as f:
                    f.write(r.content)

                click.echo(
                    f"Downloaded File: {os.path.join(location_to_paste, file_name)}"
                )

    def get_file_content(self, target_file):
        """
        Get the content of a file from the MCU drive
        :param target_file: The file on the MCU to download
        :return:
        """
        auth = HTTPBasicAuth("", self.password)
        with self.session.get(
            self.FS_URL + target_file, timeout=self.timeout, auth=auth
        ) as r:
            if r.status_code == 404:
                return None
            return r.content  # .decode("utf8")

    def install_module_mpy(self, bundle, metadata):
        """
        :param bundle library bundle.
        :param library_path library path
        :param metadata dictionary.
        """
        module_name = os.path.basename(metadata["path"]).replace(".py", ".mpy")
        if not module_name:
            # Must be a directory based module.
            module_name = os.path.basename(os.path.dirname(metadata["path"]))
        major_version = self.get_circuitpython_version()[0].split(".")[0]
        bundle_platform = "{}mpy".format(major_version)
        bundle_path = os.path.join(bundle.lib_dir(bundle_platform), module_name)
        if os.path.isdir(bundle_path):

            self.install_dir_http(bundle_path)

        elif os.path.isfile(bundle_path):
            self.install_file_http(bundle_path)

        else:
            raise IOError("Cannot find compiled version of module.")

    # pylint: enable=too-many-locals,too-many-branches
    def install_module_py(self, metadata, location=None):
        """
        :param library_path library path
        :param metadata dictionary.
        """

        source_path = metadata["path"]  # Path to Python source version.
        if os.path.isdir(source_path):
            self.install_dir_http(source_path, location=location)

        else:
            self.install_file_http(source_path, location=location)

    def uninstall(self, device_path, module_path):
        """
        Uninstall given module on device using REST API.
        """
        url = urlparse(device_path)
        auth = HTTPBasicAuth("", url.password)
        with self.session.delete(module_path, auth=auth, timeout=self.timeout) as r:
            if r.status_code == 409:
                _writeable_error()
            r.raise_for_status()

    def update(self, module):
        """
        Delete the module on the device, then copy the module from the bundle
        back onto the device.

        The caller is expected to handle any exceptions raised.
        """
        self._update_http(module)

    def file_exists(self, filepath):
        """
        return True if the file exists, otherwise False.
        """
        auth = HTTPBasicAuth("", self.password)
        resp = requests.get(
            self.get_file_path(filepath), auth=auth, timeout=self.timeout
        )
        if resp.status_code == 200:
            return True
        return False

    def _update_http(self, module):
        """
        Update the module using web workflow.
        """
        if module.file:
            # Copy the file (will overwrite).
            self.install_file_http(module.bundle_path)
        else:
            # Delete the directory (recursive) first.
            url = urlparse(module.path)
            auth = HTTPBasicAuth("", url.password)
            with self.session.delete(module.path, auth=auth, timeout=self.timeout) as r:
                if r.status_code == 409:
                    _writeable_error()
                r.raise_for_status()
            self.install_dir_http(module.bundle_path)

    def get_file_path(self, filename):
        """
        retuns the full path on the device to a given file name.
        """
        return "/".join((self.device_location, "fs", filename))

    def is_device_present(self):
        """
        returns True if the device is currently connected and running supported version
        """
        try:
            with self.session.get(f"{self.device_location}/cp/version.json") as r:
                r.raise_for_status()
                web_api_version = r.json().get("web_api_version")
                if web_api_version is None:
                    self.logger.error("Unable to get web API version from device.")
                    click.secho("Unable to get web API version from device.", fg="red")
                    return False

                if web_api_version < 4:
                    self.logger.error(
                        f"Device running unsupported web API version {web_api_version} < 4."
                    )
                    click.secho(
                        f"Device running unsupported web API version {web_api_version} < 4.",
                        fg="red",
                    )
                    return False
        except requests.exceptions.ConnectionError:
            return False

        return True

    def get_device_versions(self):
        """
        Returns a dictionary of metadata from modules on the connected device.

        :param str device_url: URL for the device.
        :return: A dictionary of metadata about the modules available on the
                 connected device.
        """
        return self.get_modules(urljoin(self.device_location, self.LIB_DIR_PATH))

    def get_free_space(self):
        """
        Returns the free space on the device in bytes.
        """
        auth = HTTPBasicAuth("", self.password)
        with self.session.get(
            urljoin(self.device_location, "fs/"),
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            if r.json().get("free") is None:
                self.logger.error("Unable to get free block count from device.")
                click.secho("Unable to get free block count from device.", fg="red")
            elif r.json().get("block_size") is None:
                self.logger.error("Unable to get block size from device.")
                click.secho("Unable to get block size from device.", fg="red")
            elif r.json().get("writable") is None or r.json().get("writable") is False:
                self.logger.error(
                    "CircuitPython Web Workflow Device not writable\n - "
                    "Remount storage as writable to device (not PC)"
                )
                click.secho(
                    "CircuitPython Web Workflow Device not writable\n - "
                    "Remount storage as writable to device (not PC)",
                    fg="red",
                )
            else:
                return r.json()["free"] * r.json()["block_size"]  # bytes
            sys.exit(1)

    def list_dir(self, dirpath):
        """
        Returns the list of files located in the given dirpath.
        """
        auth = HTTPBasicAuth("", self.password)
        with self.session.get(
            urljoin(self.device_location, f"fs/{dirpath if dirpath else ''}"),
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        ) as r:
            return r.json()["files"]


class DiskBackend(Backend):
    """
    Backend for interacting with a device via USB Workflow

    :param String device_location: Path to the device
    :param logger: logger to use for outputting messages
    :param String boot_out: Optional mock contents of a boot_out.txt file
        to use for version information.
    :param String version_override: Optional mock version to use.
    """

    def __init__(self, device_location, logger, boot_out=None, version_override=None):
        if device_location is None:
            raise ValueError(
                "Auto locating USB Disk based device failed. "
                "Please specify --path argument or ensure your device "
                "is connected and mounted under the name CIRCUITPY."
            )
        super().__init__(logger)
        self.LIB_DIR_PATH = "lib"
        self.device_location = device_location
        self.library_path = os.path.join(self.device_location, self.LIB_DIR_PATH)
        self.version_info = None
        if boot_out is not None:
            self.version_info = self.parse_boot_out_file(boot_out)
        self.version_override = version_override

    def get_circuitpython_version(self):
        """
        Returns the version number of CircuitPython running on the board connected
        via ``device_path``, along with the board ID. This is obtained from the
        ``boot_out.txt`` file on the device, whose first line will start with
        something like this::

            Adafruit CircuitPython 4.1.0 on 2019-08-02;

        While the second line is::

            Board ID:raspberry_pi_pico

        :return: A tuple with the version string for CircuitPython and the board ID string.
        """
        if self.version_override is not None:
            return self.version_override

        if not self.version_info:
            try:
                with open(
                    os.path.join(self.device_location, "boot_out.txt"),
                    "r",
                    encoding="utf-8",
                ) as boot:
                    boot_out_contents = boot.read()
                    circuit_python, board_id = self.parse_boot_out_file(
                        boot_out_contents
                    )
            except FileNotFoundError:
                click.secho(
                    "Missing file boot_out.txt on the device: wrong path or drive corrupted.",
                    fg="red",
                )
                self.logger.error("boot_out.txt not found.")
                sys.exit(1)
            return circuit_python, board_id

        return self.version_info

    def _get_modules(self, device_lib_path):
        """
        Get a dictionary containing metadata about all the Python modules found in
        the referenced path.

        :param str device_lib_path: URL to be used to find modules.
        :return: A dictionary containing metadata about the found modules.
        """
        return _get_modules_file(device_lib_path, self.logger)

    def create_directory(self, device_path, directory):
        if not os.path.exists(directory):  # pragma: no cover
            os.makedirs(directory)

    def copy_file(self, target_file, location_to_paste):
        target_filename = target_file.split(os.path.sep)[-1]
        if os.path.isdir(target_file):
            shutil.copytree(
                target_file,
                os.path.join(self.device_location, location_to_paste, target_filename),
            )
        else:
            shutil.copyfile(
                target_file,
                os.path.join(self.device_location, location_to_paste, target_filename),
            )

    def upload_file(self, target_file, location_to_paste):
        self.copy_file(target_file, location_to_paste)

    def install_module_mpy(self, bundle, metadata):
        """
        :param bundle library bundle.
        :param metadata dictionary.
        """
        module_name = os.path.basename(metadata["path"]).replace(".py", ".mpy")
        if not module_name:
            # Must be a directory based module.
            module_name = os.path.basename(os.path.dirname(metadata["path"]))

        major_version = self.get_circuitpython_version()[0].split(".")[0]
        bundle_platform = "{}mpy".format(major_version)
        bundle_path = os.path.join(bundle.lib_dir(bundle_platform), module_name)
        if os.path.isdir(bundle_path):
            target_path = os.path.join(self.library_path, module_name)
            # Copy the directory.
            shutil.copytree(bundle_path, target_path)
        elif os.path.isfile(bundle_path):

            target = os.path.basename(bundle_path)

            target_path = os.path.join(self.library_path, target)

            # Copy file.
            shutil.copyfile(bundle_path, target_path)
        else:
            raise IOError("Cannot find compiled version of module.")

    # pylint: enable=too-many-locals,too-many-branches
    def install_module_py(self, metadata, location=None):
        """
        :param metadata dictionary.
        :param location the location on the device to copy the py module to.
          If omitted is CIRCUITPY/lib/ used.
        """
        if location is None:
            location = self.library_path
        else:
            location = os.path.join(self.device_location, location)

        source_path = metadata["path"]  # Path to Python source version.
        if os.path.isdir(source_path):
            target = os.path.basename(os.path.dirname(source_path))
            target_path = os.path.join(location, target)
            # Copy the directory.
            shutil.copytree(source_path, target_path)
        else:
            if "target_name" in metadata:
                target = metadata["target_name"]
            else:
                target = os.path.basename(source_path)
            target_path = os.path.join(location, target)
            # Copy file.
            shutil.copyfile(source_path, target_path)

    def uninstall(self, device_path, module_path):
        """
        Uninstall module using local file system.
        """
        library_path = os.path.join(device_path, "lib")
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

    def update(self, module):
        """
        Delete the module on the device, then copy the module from the bundle
        back onto the device.

        The caller is expected to handle any exceptions raised.
        """
        self._update_file(module)

    def _update_file(self, module):
        """
        Update the module using file system.
        """
        if os.path.isdir(module.path):
            # Delete and copy the directory.
            shutil.rmtree(module.path, ignore_errors=True)
            shutil.copytree(module.bundle_path, module.path)
        else:
            # Delete and copy file.
            os.remove(module.path)
            shutil.copyfile(module.bundle_path, module.path)

    def file_exists(self, filepath):
        """
        return True if the file exists, otherwise False.
        """
        return os.path.exists(os.path.join(self.device_location, filepath))

    def get_file_path(self, filename):
        """
        returns the full path on the device to a given file name.
        """
        return os.path.join(self.device_location, filename)

    def get_file_content(self, target_file):
        """
        Get the content of a file from the MCU drive
        :param target_file: The file on the MCU to download
        :return:
        """
        file_path = self.get_file_path(target_file)
        if os.path.exists(file_path):
            with open(file_path, "rb") as file:
                return file.read()
        return None

    def is_device_present(self):
        """
        returns True if the device is currently connected
        """
        return os.path.exists(self.device_location)

    def get_free_space(self):
        """
        Returns the free space on the device in bytes.
        """
        # pylint: disable=unused-variable
        _, total, free = shutil.disk_usage(self.device_location)
        return free

    def list_dir(self, dirpath):
        """
        Returns the list of files located in the given dirpath.
        """
        files_list = []
        files = os.listdir(os.path.join(self.device_location, dirpath))
        for file_name in files:
            file = os.path.join(self.device_location, dirpath, file_name)
            stat = os.stat(file)
            files_list.append(
                {
                    "name": file_name,
                    "directory": os.path.isdir(file),
                    "modified_ns": stat.st_mtime_ns,
                    "file_size": stat.st_size,
                }
            )
        return files_list
