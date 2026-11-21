# SPDX-FileCopyrightText: Copyright (c) 2020 Bryan Siepert for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2022 Ruth Ivimey-Cook
#
# SPDX-License-Identifier: MIT
# pylint: disable=protected-access
"""
`adafruit_emc2101.emc2101_fanspeed`
================================================================================

Brushless fan controller: extended functionality


* Author(s): Bryan Siepert, Rylie Pavlik

Implementation Notes
--------------------

**Hardware:**

* `Adafruit EMC2101 Breakout <https://adafruit.com/product/4808>`_ (Product ID: 4808)

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

* Adafruit's Bus Device library:
  https://github.com/adafruit/Adafruit_CircuitPython_BusDevice

* Adafruit's Register library:
  https://github.com/adafruit/Adafruit_CircuitPython_Register
"""

from adafruit_register.i2c_struct_array import StructArray

from adafruit_emc2101 import emc2101_regs

try:
    from types import TracebackType
    from typing import Optional, Type
except ImportError:
    pass

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_EMC2101.git"


class FanSpeedLUT:
    """A class used to provide a dict-like interface to the EMC2101's
    Temperature to Fan speed Look Up Table (LUT).

    Keys are integer temperatures, values are fan duty cycles between 0 and
    100. A max of 8 values may be stored.

    To remove a single stored point in the LUT, assign it as `None`.

    Usage:
    At 50 C the speed should be 62% of max duty cycle. (Updates the chip
    immediately).

    .. code-block:: python

        emc2101.lut[50] = 62

    Set two values up and write to the chip on exit from 'with' block.

    .. code-block:: python

        with emc2101.lut as lut:
            lut[20] = 0
            lut[40] = 10

    Delete an unneeded temperature point: (Updates the chip immediately).

    .. code-block:: python

        emc2101.lut[20] = None

    Read a dict of the currently set values:

    .. code-block:: python

        values = emc2101.lut.lookup_table
        # returns:
        # { 40: 10, 50: 62 }

    Delete some LUT values, assign None:

    .. code-block:: python

        for temp in emc2101.lut.lookup_table:
            emc2101.lut[temp] = None

    Delete all LUT values at once:

    .. code-block:: python

        emc2101.lut.clear()
    """

    # 8 (Temperature, Speed) pairs in increasing order
    _fan_lut = StructArray(emc2101_regs.LUT_BASE, "<B", 16)
    _defer_update = False

    def __init__(self, fan_obj):
        self._defer_update = False
        self.emc_fan = fan_obj
        self.lut_values = {}
        self.i2c_device = fan_obj.i2c_device

    def __enter__(self):
        """'with' wrapper: defer lut update until end of 'with' so
        update_lut work can be done just once at the end of setting the LUT.

        """
        # Use increment/decrement so nested with's are dealt with properly.
        self._defer_update = True
        return self

    # 'with' wrapper
    def __exit__(
        self,
        typ: Optional[Type[BaseException]],
        val: Optional[BaseException],
        tbk: Optional[TracebackType],
    ):
        """'with' wrapper: defer lut update until end of 'with' so
        update_lut work can be done just once at the end of setting the LUT.
        """
        self._defer_update = False
        self._update_lut()

    def __getitem__(self, index: int) -> int:
        if not isinstance(index, int):
            raise IndexError
        if not index in self.lut_values:
            raise IndexError
        return self.lut_values[index]

    def __setitem__(self, index: int, value: int) -> None:
        if not isinstance(index, int):
            raise IndexError
        if value is None:
            # Assign None to remove this entry
            del self.lut_values[index]
        elif value > 100.0 or value < 0:
            # Range check
            raise ValueError("LUT values must be a fan speed from 0-100%")
        else:
            self.lut_values[index] = value

        if not self._defer_update:
            self._update_lut()

    def __repr__(self) -> str:
        """return the official string representation of the LUT"""
        return f"FanSpeedLUT {id(self):x}"

    def __str__(self) -> str:
        """return the official string representation of the LUT"""
        value_strs = []
        lut_keys = tuple(sorted(self.lut_values.keys()))
        for temp in lut_keys:
            fan_drive = self.lut_values[temp]
            value_strs.append(f"{temp:d} deg C => {fan_drive:.1f}% duty cycle")

        return "\n".join(value_strs)

    @property
    def lookup_table(self) -> dict:
        """Return a dictionary of LUT values."""
        lut_keys = tuple(sorted(self.lut_values.keys()))
        values = {}
        for temp in lut_keys:
            fan_drive = self.lut_values[temp]
            values[temp] = fan_drive
        return values

    def __len__(self) -> int:
        return len(self.lut_values)

    # this function does a whole lot of work to organized the user-supplied lut dict into
    # their correct spot within the lut table as pairs of set registers, sorted with the lowest
    # temperature first

    def _update_lut(self) -> None:
        # Make sure we're not going to try to set more entries than we have slots
        if len(self.lut_values) > 8:
            raise ValueError("LUT can only contain a maximum of 8 items")

        # Backup state
        current_mode = self.emc_fan.lut_enabled

        # Disable the lut to allow it to be updated
        self.emc_fan.lut_enabled = False

        # we want to assign the lowest temperature to the lowest LUT slot, so we sort the keys/temps
        # get and sort the new lut keys so that we can assign them in order
        for idx, current_temp in enumerate(sorted(self.lut_values.keys())):
            # We don't want to make `_speed_to_lsb()` public, it is only needed here.
            current_speed = self.emc_fan._speed_to_lsb(self.lut_values[current_temp])
            self._set_lut_entry(idx, current_temp, current_speed)

        # Set the remaining LUT entries to the default (Temp/Speed = max value)
        for idx in range(len(self.lut_values), 8):
            self._set_lut_entry(
                idx, emc2101_regs.MAX_LUT_TEMP, emc2101_regs.MAX_LUT_SPEED
            )
        self.emc_fan.lut_enabled = current_mode

    def _set_lut_entry(self, idx: int, temp: int, speed: int) -> None:
        """Internal function: add a value to the local LUT as a byte array,
        suitable for block transfer to the EMC I2C interface.
        """
        self._fan_lut[idx * 2] = bytearray((temp,))
        self._fan_lut[idx * 2 + 1] = bytearray((speed,))

    def clear(self) -> None:
        """Clear all LUT entries."""
        self.lut_values = {}
        self._update_lut()
