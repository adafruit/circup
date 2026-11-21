# SPDX-FileCopyrightText: Copyright (c) 2020 Bryan Siepert for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2022 Ruth Ivimey-Cook
#
# SPDX-License-Identifier: MIT
# pylint: disable=unused-import
"""
`adafruit_emc2101.emc2101_lut`
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


The class defined here may be used instead of :class:`adafruit_emc2101.EMC2101`,
if your device has enough RAM to support it. This class adds LUT control
and PWM frequency control to the base feature set.
"""

from adafruit_register.i2c_struct import UnaryStruct

from adafruit_emc2101 import emc2101_regs
from adafruit_emc2101.emc2101_ext import EMC2101_EXT
from adafruit_emc2101.emc2101_fanspeed import FanSpeedLUT

try:
    import typing

    from busio import I2C
except ImportError:
    pass

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_EMC2101.git"


class EMC2101_LUT(EMC2101_EXT):
    """Driver for the EMC2101 Fan Controller, with PWM frequency and temperature
    look-up-table (LUT) control.

    See :class:`adafruit_emc2101.EMC2101` for the base/common functionality.
    See :class:`adafruit_emc2101.EMC2101_EXT` for (almost) complete device register
    set but no temperature look-up-table LUT support.

    :param ~busio.I2C i2c_bus: The I2C bus the EMC is connected to.
    """

    lut_temperature_hysteresis = UnaryStruct(emc2101_regs.LUT_HYSTERESIS, "<B")
    """The amount of hysteresis, in degrees centigrade, of hysteresis applied to
    temperature readings used for the LUT. As the temperature drops, the
    controller will switch to a lower LUT entry when the measured value is below
    the lower entry's threshold, minus the hysteresis value.
    """

    def __init__(self, i2c_bus: I2C) -> None:
        super().__init__(i2c_bus)

        self.initialize()
        self._lut = FanSpeedLUT(self)

    def initialize(self) -> None:
        """Reset the controller to an initial default configuration.

        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        self.lut_enabled = True
        self._fan_clk_ovr = True
        super().initialize()
        self._check_status()

    def set_pwm_clock(self, use_preset: bool = False, use_slow: bool = False) -> None:
        """
        Select the PWM clock source, choosing between two preset clocks or by
        configuring the clock with `pwm_frequency` and `pwm_frequency_divisor`.

        :param bool use_preset:
         True: Select between two preset clock sources
         False: The PWM clock is set by `pwm_frequency` and `pwm_frequency_divisor`
        :param bool use_slow:
             True: Use the 1.4kHz clock
             False: Use the 360kHz clock.
        :type priority: integer or None
        :return: None
        :raises TypeError: if use_preset is not a `bool`
        :raises TypeError: if use_slow is not a `bool`
        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """

        if not isinstance(use_preset, bool):
            raise TypeError("use_preset must be given a bool")
        if not isinstance(use_slow, bool):
            raise TypeError("use_slow_pwm must be given a bool")

        self._fan_clk_ovr = not use_preset
        self._fan_clk_sel = use_slow
        self._check_status()

    @property
    def pwm_frequency(self) -> int:
        """Selects the base clock frequency used for the fan PWM output"""
        self._check_status()
        return self._pwm_freq

    @pwm_frequency.setter
    def pwm_frequency(self, value: int) -> None:
        """Set the PWM (fan) output frequency, which is a value from the
        datasheet.

        :param int: value the frequency value tag.
        :raises ValueError: if the assigned frequency is not valid.
        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        if not 0 <= value < 32:
            raise ValueError("pwm_frequency must be from 0-31")
        self._pwm_freq = value
        self._calculate_full_speed(pwm_f=value)
        self._check_status()

    @property
    def pwm_frequency_divisor(self) -> int:
        """The Divisor applied to the PWM frequency to set the final frequency.

        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        self._check_status()
        return self._pwm_freq_div

    @pwm_frequency_divisor.setter
    def pwm_frequency_divisor(self, divisor: int) -> None:
        """Set the PWM (fan) output frequency divisor, which is a value from
        the datasheet.

        :param int: value the frequency divisor tag.
        :raises ValueError: if the assigned divisor is not valid.
        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        if not 0 <= divisor <= 255:
            raise ValueError("pwm_frequency_divisor must be from 0-255")
        self._pwm_freq_div = divisor
        self._check_status()

    @property
    def lut_enabled(self) -> bool:
        """Enable or disable the internal look up table used to map a given
        temperature to a fan speed. When the LUT is disabled fan speed can be
        changed with `manual_fan_speed`.
        :return enable_lut
        """
        self._check_status()
        return not self._fan_lut_prog

    @lut_enabled.setter
    def lut_enabled(self, enable_lut: bool) -> None:
        """Enable or disable the internal look up table used to map a given
        temperature to a fan speed. When the LUT is disabled fan speed can be
        changed with `manual_fan_speed`.

        :param bool: enable_lut
        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        self._fan_lut_prog = not enable_lut
        self._check_status()

    @property
    def lut(self):
        """The dict-like representation of the LUT, an instance of
        :class:`FanSpeedLUT`. Use this to update or read the current LUT.

        You can use python 'with' on this class to perform a multiple
        update of the LUT.  Usage:

        .. code-block:: python

            with emc2101.lut as lut:
                lut[20] = 0
                lut[40] = 10

        The device only supports 8 entries in the LUT. If you try to add
        more than this the update will fail with a ValueError. If the add
        is part of a 'with' block, this happens when the block ends.

        To delete an entry from the current table, assign None to the
        current temperature slot(s).

        .. code-block:: python

            with emc2101.lut as lut:
                lut[20] = 0
                lut[40] = 10

            emc2101.lut[20] = None
            print(emc2101.lut.lookup_table)

        will print one item, for temp 40, speed 10%.
        """
        return self._lut
