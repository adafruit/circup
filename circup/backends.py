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
import tempfile
from urllib.parse import urlparse, urljoin
import click
import requests
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

    def __init__(self, logger):
        self.device_location = None
        self.LIB_DIR_PATH = None
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

    def _create_library_directory(self, device_path, library_path):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def _install_module_py(self, metadata):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    def _install_module_mpy(self, bundle, metadata):
        """
        To be overridden by subclass
        """
        raise NotImplementedError

    # pylint: disable=too-many-locals,too-many-branches,too-many-arguments
    def install_module(
        self, device_path, device_modules, name, pyext, mod_names
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
        """
        if not name:
            click.echo("No module name(s) provided.")
        elif name in mod_names:
            # Grab device modules to check if module already installed
            if name in device_modules:
                click.echo("'{}' is already installed.".format(name))
                return

            library_path = os.path.join(device_path, self.LIB_DIR_PATH) if not isinstance(self,WebBackend) else urljoin(device_path,self.LIB_DIR_PATH)

            # Create the library directory first.
            self._create_library_directory(device_path, library_path)

            metadata = mod_names[name]
            bundle = metadata["bundle"]
            if pyext:
                # Use Python source for module.
                self._install_module_py(metadata)
            else:
                # Use pre-compiled mpy modules.
                self._install_module_mpy(bundle, metadata)
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


class WebBackend(Backend):
    """
    Backend for interacting with a device via Web Workflow
    """

    def __init__(self, host, password, logger):
        super().__init__(logger)
        self.LIB_DIR_PATH = "fs/lib/"
        self.host = host
        self.password = password
        self.device_location = f"http://:{self.password}@{self.host}"

        self.library_path = self.device_location + "/" + self.LIB_DIR_PATH

    def install_file_http(self, source):
        """
        Install file to device using web workflow.
        :param source source file.
        """
        file_name = source.split(os.path.sep)
        file_name = file_name[-2] if file_name[-1] == "" else file_name[-1]
        target = (
            self.device_location
            + "/"
            + self.LIB_DIR_PATH
            + file_name
        )
        url = urlparse(target)
        auth = HTTPBasicAuth("", url.password)
        print(f"target: {target}")
        print(f"source: {source}")

        with open(source, "rb") as fp:
            r = requests.put(target, fp.read(), auth=auth)
            r.raise_for_status()

    def install_dir_http(self, source):
        """
        Install directory to device using web workflow.
        :param source source directory.
        """
        mod_name = source.split(os.path.sep)
        mod_name = mod_name[-2] if mod_name[-1] == "" else mod_name[-1]
        target = (
            self.device_location
            + "/"
            + self.LIB_DIR_PATH
            + mod_name
        )
        url = urlparse(target)
        auth = HTTPBasicAuth("", url.password)
        print(f"target: {target}")
        print(f"source: {source}")

        # Create the top level directory.
        r = requests.put((target + "/" if target[:-1]!="/" else target), auth=auth)
        print(f"resp {r.content}")
        r.raise_for_status()

        # Traverse the directory structure and create the directories/files.
        for root, dirs, files in os.walk(source):
            rel_path = os.path.relpath(root, source)
            if rel_path == ".":
                rel_path = ""
            for name in files:
                with open(os.path.join(root, name), "rb") as fp:
                    path_to_create = urljoin( urljoin(target , rel_path + "/", allow_fragments=False) , name, allow_fragments=False) if rel_path != "" else urljoin(target , name, allow_fragments=False)
                    # print(f"file_path_to_create: {path_to_create}")
                    r = requests.put(
                        path_to_create, fp.read(), auth=auth
                    )
                    r.raise_for_status()
            for name in dirs:
                path_to_create = urljoin( urljoin(target , rel_path + "/", allow_fragments=False) , name, allow_fragments=False) if rel_path != "" else urljoin(target , name, allow_fragments=False)
                # print(f"dir_path_to_create: {path_to_create}")
                r = requests.put(path_to_create, auth=auth)
                r.raise_for_status()

    def get_circuitpython_version(self):
        """
        Returns the version number of CircuitPython running on the board connected
        via ``device_path``, along with the board ID. This is obtained using
        RESTful API from the /cp/version.json URL.

        :return: A tuple with the version string for CircuitPython and the board ID string.
        """
        # pylint: disable=arguments-renamed
        r = requests.get(self.device_location + "/cp/version.json")
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
        r = requests.get(url, auth=auth, headers={"Accept": "application/json"})
        r.raise_for_status()

        directory_mods = []
        single_file_mods = []
        for entry in r.json():
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
        """
        #TODO describe what this does

        :param auth HTTP authentication.
        :param directory_mods list of modules.
        :param result dictionary for the result.
        :param url: URL of the device.
        """
        for dm in directory_mods:
            if not str(urlparse(dm).scheme).lower() in ("http", "https"):
                dm_url = url + dm + "/"
            else:
                dm_url = dm
            r = requests.get(dm_url, auth=auth, headers={"Accept": "application/json"})
            r.raise_for_status()
            mpy = False
            for entry in r.json():
                entry_name = entry.get("name")
                if not entry.get("directory") and (
                    entry_name.endswith(".py") or entry_name.endswith(".mpy")
                ):
                    if entry_name.endswith(".mpy"):
                        mpy = True
                    r = requests.get(dm_url + entry_name, auth=auth)
                    r.raise_for_status()
                    idx = entry_name.rfind(".")
                    with tempfile.NamedTemporaryFile(
                        prefix=entry_name[:idx] + "-",
                        suffix=entry_name[idx:],
                        delete=False,
                    ) as fp:
                        fp.write(r.content)
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
            if not str(urlparse(sfm).scheme).lower() in ("http", "https"):
                sfm_url = url + sfm
            else:
                sfm_url = sfm
            r = requests.get(sfm_url, auth=auth)
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

    def _create_library_directory(self, device_path, library_path):
        url = urlparse(device_path)
        auth = HTTPBasicAuth("", url.password)
        r = requests.put(library_path, auth=auth)
        r.raise_for_status()

    def _install_module_mpy(self, bundle, metadata):
        """
        :param bundle library bundle.
        :param library_path library path
        :param metadata dictionary.
        """
        library_path = self.library_path
        print(f"metadata: {metadata}")
        module_name = os.path.basename(metadata["path"]).replace(".py", ".mpy")
        if not module_name:
            # Must be a directory based module.
            module_name = os.path.basename(os.path.dirname(metadata["path"]))
        major_version = self.get_circuitpython_version()[0].split(".")[0]
        bundle_platform = "{}mpy".format(major_version)
        bundle_path = os.path.join(bundle.lib_dir(bundle_platform), module_name)
        if os.path.isdir(bundle_path):

            print(f"456 library_path: {library_path}")
            print(f"456 module_name: {module_name}")

            self.install_dir_http(bundle_path)

        elif os.path.isfile(bundle_path):
            target = os.path.basename(bundle_path)
            print(f"123 library_path: {library_path}")
            print(f"123 target: {target}")
            self.install_file_http(bundle_path)

        else:
            raise IOError("Cannot find compiled version of module.")

    # pylint: enable=too-many-locals,too-many-branches
    def _install_module_py(self, metadata):
        """
        :param library_path library path
        :param metadata dictionary.
        """

        source_path = metadata["path"]  # Path to Python source version.
        if os.path.isdir(source_path):
            self.install_dir_http(source_path)

        else:
            self.install_file_http(source_path)

    def get_auto_file_path(self, auto_file_path):
        """
        Make a local temp copy of the --auto file from the device.
        Returns the path to the local copy.
        """
        url = auto_file_path
        auth = HTTPBasicAuth("", self.password)
        r = requests.get(url, auth=auth)
        r.raise_for_status()
        with open(LOCAL_CODE_PY_COPY, "w", encoding="utf-8") as f:
            f.write(r.text)
        return LOCAL_CODE_PY_COPY

    def uninstall(self, device_path, module_path):
        """
        Uninstall given module on device using REST API.
        """
        url = urlparse(device_path)
        auth = HTTPBasicAuth("", url.password)
        r = requests.delete(module_path, auth=auth)
        r.raise_for_status()

    def update(self, module):
        """
        Delete the module on the device, then copy the module from the bundle
        back onto the device.

        The caller is expected to handle any exceptions raised.
        """
        self._update_http(module)

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
            r = requests.delete(module.path, auth=auth)
            r.raise_for_status()
            self.install_dir_http(module.bundle_path)

    def get_file_path(self, filename):
        """
        retuns the full path on the device to a given file name.
        """
        return urljoin( urljoin(self.device_location, "fs/", allow_fragments=False), filename, allow_fragments=False)

    def is_device_present(self):
        """
        returns True if the device is currently connected
        """
        try:
            _ = self.get_device_versions()
            return True
        except requests.exceptions.ConnectionError:
            return False

    def get_device_versions(self):
        """
        Returns a dictionary of metadata from modules on the connected device.

        :param str device_url: URL for the device.
        :return: A dictionary of metadata about the modules available on the
                 connected device.
        """
        return self.get_modules(urljoin(self.device_location, self.LIB_DIR_PATH))

class DiskBackend(Backend):
    """
    Backend for interacting with a device via USB Workflow

    :param String device_location: Path to the device
    :param logger: logger to use for outputting messages
    :param String boot_out: Optional mock contents of a boot_out.txt file
        to use for version information.
    """

    def __init__(self, device_location, logger, boot_out=None):
        if device_location is None:
            raise ValueError(
                "Auto locating USB Disk based device failed. "
                "Please specify --path argument or ensure your device "
                "is connected and mounted under the name CIRCUITPY."
            )
        super().__init__(logger)
        self.LIB_DIR_PATH = "lib"
        self.device_location = device_location
        self.library_path = self.device_location + "/" + self.LIB_DIR_PATH
        self.version_info = None
        if boot_out is not None:
            self.version_info = self.parse_boot_out_file(boot_out)

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
            print((circuit_python, board_id))
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

    def _create_library_directory(self, device_path, library_path):
        if not os.path.exists(library_path):  # pragma: no cover
            os.makedirs(library_path)

    def _install_module_mpy(self, bundle, metadata):
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
    def _install_module_py(self, metadata):
        """
        :param library_path library path
        :param metadata dictionary.
        """

        source_path = metadata["path"]  # Path to Python source version.
        if os.path.isdir(source_path):
            target = os.path.basename(os.path.dirname(source_path))
            target_path = os.path.join(self.library_path, target)
            # Copy the directory.
            shutil.copytree(source_path, target_path)
        else:
            target = os.path.basename(source_path)
            target_path = os.path.join(self.library_path, target)
            # Copy file.
            shutil.copyfile(source_path, target_path)

    def get_auto_file_path(self, auto_file_path):
        """
        Returns the path on the device to the file to be read for --auto.
        """
        return auto_file_path

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

    def get_file_path(self, filename):
        """
        returns the full path on the device to a given file name.
        """
        return os.path.join(self.device_location, filename)

    def is_device_present(self):
        """
        returns True if the device is currently connected
        """
        return os.path.exists(self.device_location)
