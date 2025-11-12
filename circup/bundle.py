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
    get_latest_release_from_url,
)

from circup.logging import logger


class Bundle:
    """
    All the links and file names for a bundle
    """

    #: Avoid requests to the internet
    offline = False

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
        self.pinned_tag = None
        self._available = []

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
        The current tag for the project. If the tag hasn't been explicitly set
        this will be the pinned tag, if one is set. If there is no pinned tag,
        this will be the latest available tag that is locally available.

        :return: The current tag value for the project.
        """
        if self._current is None:
            self._current = self.pinned_tag or (
                # This represents the latest version locally available
                self._available[-1]
                if len(self._available) > 0
                else None
            )
        return self._current

    @current_tag.setter
    def current_tag(self, tag):
        """
        Set the current tag (after updating).

        :param str tag: The new value for the current tag.
        """
        self._current = tag

    @property
    def latest_tag(self):
        """
        Lazy find the value of the latest tag for the bundle.

        :return: The most recent tag value for the project.
        """
        if self._latest is None:
            if self.offline:
                self._latest = self._available[-1] if len(self._available) > 0 else None
            else:
                self._latest = get_latest_release_from_url(
                    self.url + "/releases/latest", logger
                )
        return self._latest

    @property
    def available_tags(self):
        """
        The locally available tags to use for the project.

        :return: All tags available for the project.
        """
        return tuple(self._available)

    @available_tags.setter
    def available_tags(self, tags):
        """
        Set the available tags.

        :param str|list tags: The new value for the locally available tags.
        """
        if isinstance(tags, str):
            tags = [tags]
        self._available = sorted(tags)

    def add_tag(self, tag: str) -> None:
        """
        Add a tag to the list of available tags.

        This will add the tag if it isn't already present in the list of
        available tags. The tag will be added so that the list is sorted in an
        increasing order. This ensures that that last tag is always the latest.

        :param str tag: The tag to add to the list of available tags.
        """
        if tag in self._available:
            # The tag is already stored for some reason, lets not add it again
            return

        for rev_i, available_tag in enumerate(reversed(self._available)):
            if int(tag) > int(available_tag):
                i = len(self._available) - rev_i
                self._available.insert(i, tag)
                break
        else:
            self._available.insert(0, tag)

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
                "pinned": self.pinned_tag,
                "available": self._available,
            }
        )
