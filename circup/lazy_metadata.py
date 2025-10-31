# SPDX-FileCopyrightText: 2025 George Waters
#
# SPDX-License-Identifier: MIT
"""
Class that acts similar to a dictionary, but defers the loading of expensive
data until that data is accessed.
"""
from typing import Any, Callable


class LazyMetadata:
    """
    Dictionary like class that stores module metadata. Expensive to load
    metadata won't be loaded until it is accessed.
    """

    def __init__(
        self,
        deferred_load: Callable[[], dict[str, Any]],
        initial_data: dict[str, Any] | None = None,
    ):
        """
        Initialize a LazyMetadata object by providing a callable and initial
        data.

        :param deferred_load: A callable that returns a dictionary of metadata.
        This is not invoked until a key is accessed that is not available in
        :py:attr:`initial_data`.
        :param initial_data: A dictionary containing the initial metadata.
        """
        self._deferred_load = deferred_load
        self.initial_data = initial_data.copy() if initial_data is not None else {}
        self._deferred_data: dict[str, Any] | None = None

    @property
    def deferred_data(self) -> dict[str, Any]:
        """
        Lazy load the metadata from :py:attr:`_deferred_load`.

        :return: The "expensive" metadata that was loaded from
        :py:attr:`_deferred_load`.
        """
        if self._deferred_data is None:
            self._deferred_data = self._deferred_load()
        return self._deferred_data

    def __getitem__(self, key: str) -> Any:
        """
        Get items via keyed index lookup, like a dictionary.

        Keys are first looked for in :py:attr:`initial_data`, if the key isn't
        found it is then looked for in :py:attr:`deferred_data`.

        :param key: Key to a metadata value.
        :return: Metadata value for the given key.
        :raises KeyError: If the key cannot be found.
        """
        if key in self.initial_data:  # pylint: disable=no-else-return
            return self.initial_data[key]
        elif key in self.deferred_data:
            return self.deferred_data[key]
        raise KeyError(key)

    def __setitem__(self, key: str, item: Any) -> None:
        """
        Sets the item under the given key.

        The item is set in the :py:attr:`initial_data` dictionary.

        :param key: Key to a metadata value.
        :param item: Metadata value
        """
        self.initial_data[key] = item

    def __contains__(self, key: str):
        """
        Whether or not a key is present.

        This checks both :py:attr:`initial_data` and :py:attr:`deferred_data`
        for the key. *Note* this will cause :py:attr:`deferred_data` to load
        the deferred data if it is not already.
        """
        return key in self.initial_data or key in self.deferred_data

    def get(self, key: str, default: Any = None):
        """
        Get items via keyed index lookup, like a dictionary.

        Also like a dictionary, this method doesn't error if the key is not
        found. :param default: is returned if the key is not found.

        :param key: Key to a metadata value.
        :param default: Default value to return when the key doesn't exist.
        :return: Metadata value for the given key.
        """
        if key in self:
            return self[key]
        return default

    def __repr__(self) -> str:
        """
        Helps with log files.

        :return: A repr of a dictionary containing the metadata's values.
        """
        return repr(
            {
                "initial_data": self.initial_data,
                "deferred_data": self._deferred_data
                if self._deferred_data is not None
                else "<Not Loaded>",
            }
        )
