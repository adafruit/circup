# SPDX-FileCopyrightText: Copyright (c) 2022 Ruth Ivimey-Cook
# Derived from work by Bryan Siepert for Adafruit Industries
#
# SPDX-License-Identifier: MIT
# pylint: disable=unused-import
"""
`adafruit_emc2101.emc2101_ext`
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

from adafruit_register.i2c_bit import RWBit
from adafruit_register.i2c_bits import RWBits
from adafruit_register.i2c_struct import UnaryStruct

from adafruit_emc2101 import EMC2101, emc2101_regs

try:
    import typing

    from busio import I2C
except ImportError:
    pass

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_EMC2101.git"


class EMC2101_EXT(EMC2101):
    """Driver for EMC2101 Fan, adding definitions for all (but LUT) device registers.

    See :class:`adafruit_emc2101.EMC2101` for the base/common functionality.
    See :class:`adafruit_emc2101.EMC2101_LUT` for the temperature look up table functionality.

    :param ~busio.I2C i2c_bus: The I2C bus the EMC is connected to.
    """

    _queue = RWBit(emc2101_regs.REG_CONFIG, 0)
    """If set, select whether one (0) or three (0) consecutive over-temp
    readings are required for the Alert & Status bits to signal an error."""
    _tcrit_override = RWBit(emc2101_regs.REG_CONFIG, 1)
    """If set, permits the tcrit limit to be changed. The limit can only be
    changed once per power-cycle."""

    # In base class:
    # _tach_mode_enable = RWBit(REG_CONFIG, 2)
    # _dac_output_enabled = RWBit(REG_CONFIG, 4)
    # not exposed:
    # _disable_i2c_to = RWBit(REG_CONFIG, 3)

    _fan_standby = RWBit(emc2101_regs.REG_CONFIG, 5)
    """Select whether the fan output is driven when the device is put into
    standby mode."""
    _standby = RWBit(emc2101_regs.REG_CONFIG, 6)
    """Selects the operational mode; if 0 (default) temperatures are monitored
    and the fan output driven. If 1, temperatures are not monitored and the
    fan may be disabled (depends on _fan_standby)."""

    _int_temp_limit = UnaryStruct(emc2101_regs.INT_TEMP_HI_LIM, "<B")
    """Device internal temperature limit. If temperature is higher than this
    the ALERT actions are taken."""
    _tcrit_limit = UnaryStruct(emc2101_regs.TCRIT_TEMP, "<B")
    """Device internal critical temperature. Device part spec is 0C to 85C."""
    _tcrit_hyst = UnaryStruct(emc2101_regs.TCRIT_HYST, "<B")
    """Device internal critical temperature hysteresis, default 1C"""

    # Limits, Integer Temperature in degrees centigrade:
    _ext_temp_lo_limit_msb = RWBits(6, emc2101_regs.EXT_TEMP_LO_LIM_MSB, 0)
    """External temperature low-limit (integer part). If read temperature is
    lower than this, the ALERT actions are taken."""
    _ext_temp_hi_limit_msb = RWBits(6, emc2101_regs.EXT_TEMP_HI_LIM_MSB, 0)
    """External temperature high-limit (integer part). If read temperature is
    higher than this, the ALERT actions are taken."""

    # Limits, Fractions of degree centigrade (b7:0.5, b6:0.25, b5:0.125)
    _ext_temp_lo_limit_lsb = RWBits(3, emc2101_regs.EXT_TEMP_LO_LIM_LSB, 5)
    """External temperature low-limit (3-bit fractional part). If read
    temperature is lower than this, the ALERT actions are taken."""
    _ext_temp_hi_limit_lsb = RWBits(3, emc2101_regs.EXT_TEMP_HI_LIM_LSB, 5)
    """External temperature high-limit (3-bit fractional part). If read
    temperature is higher than this, the ALERT actions are taken."""

    _ext_ideality = RWBits(5, emc2101_regs.EXT_IDEALITY, 0)
    """Factor setting the ideality factor applied to the external diode,
    based around a standard factor of 1.008. See table in datasheet for
    details"""
    _ext_betacomp = RWBits(5, emc2101_regs.EXT_BETACOMP, 0)
    """Beta compensation setting. When using diode-connected transistor,
    disable with value of 0x7. Otherwise, bit 3 enables autodetection."""

    # not exposed: tach = RWBits(2, FAN_CONFIG, 0)
    _fan_clk_ovr = RWBit(emc2101_regs.FAN_CONFIG, 2)
    """Enable override of clk_sel to use pwm_freq_div register to determine
    the pwm frequency."""
    _fan_clk_sel = RWBit(emc2101_regs.FAN_CONFIG, 3)
    """Select base clock used to determine pwm frequency, default 0 is 360KHz,
    and 1 is 1.4KHz."""
    # In base class:
    # invert_fan_output = RWBit(FAN_CONFIG, 4)
    _fan_lut_prog = RWBit(emc2101_regs.FAN_CONFIG, 5)
    # In base class:
    # forced_temp_enabled = RWBit(FAN_CONFIG, 6)

    _avg_filter = RWBits(2, emc2101_regs.AVG_FILTER, 1)
    """Set the level of digital averaging used for temp measurements.
    0: none, 1: 1 sample, 2: 3 samples."""
    _alert_comp = RWBit(emc2101_regs.AVG_FILTER, 0)
    """Set use of Alert/Tach pin, either as interrupt, or as a temperature
    comparator. See Datasheet section 5.4 for details."""

    _last_status = 0
    """A record of the last value read from the status register, because
    the device zeroes its status register on read. Default 0."""

    auto_check_status = False
    """Enable checking status register before many operations. Slows other
    uses down but useful to catch limit or overtemp alerts. checks can also
    be made by calling check_status(). Default: ON"""

    def __init__(self, i2c_bus: I2C) -> None:
        super().__init__(i2c_bus)
        self.initialize()

    def initialize(self) -> None:
        """Reset the controller to an initial default configuration."""
        self.auto_check_status = False
        self._last_status = 0
        super().initialize()

    def _check_status(self) -> None:
        if self.auto_check_status:
            self.check_status()

    @property
    def last_status(self) -> int:
        """Read the saved copy of the device status register. This is kept
        because the action of reading the status register also clears any
        outstanding alert reports, so a second read will return 0 unless
        the condition causing the alert persists.

        This method is mainly of use after a check_status call.

        :return: int the 8-bit device status register as last read, or 0
        """
        return self._last_status

    # Overrides plain version, class EMC2101 doesn't store last status.
    @property
    def devstatus(self) -> int:
        """Read device status (alerts) register. See the STATUS_* bit
        definitions in the emc2101_regs module, or refer to the datasheet for
        more detail.

        Note: The action of reading the status register also clears any
        outstanding alert reports, so a second read will return 0 unless
        the condition causing the alert persists.
        """
        self._last_status = self._status
        return self._last_status

    def check_status(self) -> None:
        """Read the status register and check for a fault indicated.
        If one of the bits in STATUS_ALERT indicates an alert, raise
        an exception.

        Note: The action of reading the status register also clears any
        outstanding alert reports, so a second read will return 0 unless
        the condition causing the alert persists.

        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        self._last_status = self._status
        if self.last_status & emc2101_regs.STATUS_ALERT:
            raise RuntimeError("Status alert")

    @property
    def internal_temperature(self) -> int:
        """The temperature as measured by the EMC2101's internal 8-bit
        temperature sensor.

        :return: int temperature in degrees centigrade.
        """
        self._check_status()
        return super().internal_temperature

    @property
    def external_temperature(self) -> float:
        """The temperature measured using the external diode. The value is
        read as a fixed-point 11-bit value ranging from -64 C to just over
        approx 126 C, with fractional part of 1/8 degree centigrade.

        :return: Float temperature in degrees centigrade.
        :raises RuntimeError: if auto_check_status and an alert status bit
            is set.
        :raises RuntimeError: if the sensor pind (DP,DN) are open circuit
            (the sensor is disconnected).
        :raises RuntimeError: if the external temp sensor is a short circuit
            (not behaving like a diode).
        """
        self._check_status()
        return super().external_temperature

    @property
    def fan_speed(self) -> float:
        """The current speed in Revolutions per Minute (RPM).

        :return: float speed in RPM.
        """
        self._check_status()
        return super().fan_speed

    @property
    def dev_temp_critical_limit(self) -> int:
        """The critical temperature limit for the device (measured by internal
        sensor), in degrees centigrade.

        Note: this value can only be written one time during any power-up
        sequence. To re-write it you must power cycle the chip. In order
        to write the limit, the tcrit override bit must first be set in the
        config register.

        :return: int the device internal critical limit temperature.
        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        self._check_status()
        return self._tcrit_limit

    @property
    def dev_temp_critical_hysteresis(self) -> int:
        """The critical temperature hysteresis for the device (measured by
        the internal sensor), in degrees centigrade.

        Hysteresis is a lag in fan switching activity added to prevent
        too-rapid switching. It results in the temperature needing to fall to
        a lower temperature before the fan switches off than the higher
        temperature that caused the fan to switch on. The value here is the
        number of degrees centigrade of this difference. The device does not to
        support setting this value to 0.

        """
        self._check_status()
        return self._tcrit_hyst

    @dev_temp_critical_hysteresis.setter
    def dev_temp_critical_hysteresis(self, hysteresis: int) -> None:
        """The critical temperature hysteresis for the device (measured by the
        internal sensor), in degrees centigrade (1..10).

        :param int hysteresis: the number of degrees centigrade of difference
        """
        if not 0 <= hysteresis <= 10:
            raise ValueError("dev_temp_critical_hysteresis must be from 1..10")
        self._tcrit_hyst = hysteresis
        self._check_status()

    @property
    def dev_temp_high_limit(self) -> int:
        """The high limit temperature for the internal sensor, in degrees
        centigrade."""
        self._check_status()
        return self._int_temp_limit

    @dev_temp_high_limit.setter
    def dev_temp_high_limit(self, temp: int) -> None:
        """The high limit temperature for the internal sensor, in degrees
        centigrade (0..85)."""
        # Device specced from 0C to 85C
        if not 0 <= temp <= 85:
            raise ValueError("dev_temp_high_limit must be from 0..85")
        self._int_temp_limit = temp
        self._check_status()

    @property
    def external_temp_low_limit(self) -> float:
        """The low limit temperature for the external sensor."""
        self._check_status()
        # No ordering restrictions here.
        temp_lsb = self._ext_temp_lo_limit_lsb
        temp_msb = self._ext_temp_lo_limit_msb
        temp = (temp_msb << 8) | (temp_lsb & 0xE0)
        temp >>= 5
        temp *= 0.125
        if not -64 <= temp <= 127:
            # This should be impossible, if it happens the i2c data is corrupted.
            raise OSError("Connection")
        return temp

    @external_temp_low_limit.setter
    def external_temp_low_limit(self, temp: float) -> None:
        """Set the low limit temperature for the external sensor. The device
        automatically compares live temp readings with this value and signal
        the current reading is too low by setting the status register.

        Reading the status register clears the alert, unless the condition
        persists.

        :param float temp: the new limit temperature
        :raises ValueError: if the supplied temperature is out of range.
        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """
        if not -64 <= temp <= 127:
            raise ValueError("dev_temp_high_limit must be from -64..127")

        # Multiply by 8 to get 3 bits of fraction within the integer.
        temp *= 8.0
        temp = int(temp)
        # Mask 3 bits & shift to bits 5,6,7 in byte
        temp_lsb = temp & 0x07
        temp_lsb <<= 5
        # Now drop 3 fraction bits.
        temp_msb = temp >> 3

        # No ordering restrictions here.
        self._ext_temp_lo_limit_lsb = temp_lsb
        self._ext_temp_lo_limit_msb = temp_msb
        self._check_status()

    @property
    def external_temp_high_limit(self) -> float:
        """The high limit temperature for the external sensor."""
        self._check_status()

        # No ordering restrictions here.
        temp_lsb = self._ext_temp_hi_limit_lsb
        temp_msb = self._ext_temp_hi_limit_msb
        # Mask bottom bits of lsb, or with shifted msb
        full_tmp = (temp_msb << 8) | (temp_lsb & 0xE0)
        full_tmp >>= 5
        full_tmp *= 0.125
        if not -64 <= full_tmp <= 127:
            # This should be impossible, if it happens the i2c data is corrupted.
            raise OSError("Connection")
        return full_tmp

    @external_temp_high_limit.setter
    def external_temp_high_limit(self, temp: float) -> None:
        """Set high limit temperature for the external sensor. The device
        automatically compares live temp readings with this value and signal
        the current reading is too high by setting the status register.

        Reading the status register clears the alert, unless the condition
        persists.

        :param float temp: the new limit temperature
        :raises ValueError: if the supplied temperature is out of range.
        :raises RuntimeError: if auto_check_status and an alert status bit is set
        """

        if not -64 <= temp <= 127:
            raise ValueError("dev_temp_high_limit must be from -64..127")

        # Multiply by 8 to get 3 bits of fraction.
        temp *= 8.0
        temp = int(temp)
        # Mask 3 bits & shift to bits 5,6,7 in byte
        temp_lsb = temp & 0x07
        temp_lsb <<= 5
        # Now drop 3 fraction bits.
        temp_msb = temp >> 3
        # No ordering restrictions here.
        self._ext_temp_hi_limit_lsb = temp_lsb
        self._ext_temp_hi_limit_msb = temp_msb
        self._check_status()
