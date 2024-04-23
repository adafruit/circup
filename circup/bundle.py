# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, 2024 Tim Cocks, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
Class that represents a specific release of a Bundle.
"""
import os
import sys

import click
import requests

from circup.shared import (
    DATA_DIR,
    PLATFORMS,
    REQUESTS_TIMEOUT,
    tags_data_load,
    get_latest_release_from_url,
)

from circup.logging import logger


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

    def examples_dir(self, platform):
        """
        This bundle's examples directory for the platform.

        :param str platform: The platform identifier (py/6mpy/...).
        :return: The path to the examples directory for the platform.
        """
        tag = self.current_tag
        return os.path.join(
            self.dir.format(platform=platform),
            self.basename.format(platform=PLATFORMS[platform], tag=tag),
            "examples",
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
            self._latest = get_latest_release_from_url(
                self.url + "/releases/latest", logger
            )
        return self._latest

    def validate(self):
        """
        Test the existence of the expected URLs (not their content)
        """
        tag = self.latest_tag
        if not tag or tag == "releases":
            if "--verbose" in sys.argv:
                click.secho(f'  Invalid tag "{tag}"', fg="red")
            return False
        for platform in PLATFORMS.values():
            url = self.url_format.format(platform=platform, tag=tag)
            r = requests.get(url, stream=True, timeout=REQUESTS_TIMEOUT)
            # pylint: disable=no-member
            if r.status_code != requests.codes.ok:
                if "--verbose" in sys.argv:
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
