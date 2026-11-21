# SPDX-FileCopyrightText: Copyright (c) 2020 Bryan Siepert for Adafruit Industries
#
# SPDX-License-Identifier: MIT
# pylint: disable=too-many-instance-attributes,import-outside-toplevel
"""
`adafruit_emc2101`
================================================================================

Brushless fan controller


* Author(s): Bryan Siepert

Implementation Notes
--------------------

**Hardware:**

* `Adafruit EMC2101 Breakout
  <https://adafruit.com/product/4808>`_ (Product ID: 4808)

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

* Adafruit's Bus Device library:
  https://github.com/adafruit/Adafruit_CircuitPython_BusDevice

* Adafruit's Register library:
  https://github.com/adafruit/Adafruit_CircuitPython_Register

"""

import adafruit_bus_device.i2c_device as i2cdevice
from adafruit_register.i2c_bit import RWBit
from adafruit_register.i2c_bits import RWBits
from adafruit_register.i2c_struct import ROUnaryStruct, UnaryStruct
from micropython import const

from adafruit_emc2101 import emc2101_regs

try:
    from typing import Tuple

    from busio import I2C
except ImportError:
    pass

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_EMC2101.git"


class EMC2101:
    """Basic driver for the EMC2101 Fan Controller.

    :param ~busio.I2C i2c_bus: The I2C bus the EMC is connected to.

    See :class:`adafruit_emc2101.EMC2101_EXT` for (almost) complete device register set.
    See :class:`adafruit_emc2101.EMC2101_LUT` for the temperature look up table functionality.

    **Quickstart: Importing and using the device**

        Here is an example of using the :class:`EMC2101` class.
        First you will need to import the libraries to use the sensor

        .. code-block:: python

            import board
            from adafruit_emc2101.emc2101_lut import EMC2101_LUT as EMC2101

        Once this is done you can define your `board.I2C` object and define your sensor object

        .. code-block:: python

            i2c = board.I2C()  # uses board.SCL and board.SDA
            emc = EMC2101(i2c)

        Now you have access to the :attr:`manual_fan_speed` attribute to setup the
        desired fanspeed

        .. code-block:: python

            emc.manual_fan_speed = 25


    If you need control over PWM frequency and the controller's built in temperature/speed
    look-up table (LUT), you will need :class:`emc2101_lut.EMC2101_LUT` which extends this
    class to add those features, at the cost of increased memory usage.

    Datasheet: https://ww1.microchip.com/downloads/en/DeviceDoc/2101.pdf
    """

    _part_id = ROUnaryStruct(emc2101_regs.REG_PARTID, "<B")
    """Device Part ID field value, see also _part_rev and _part_id."""
    _mfg_id = ROUnaryStruct(emc2101_regs.REG_MFGID, "<B")
    """Device Manufacturer ID field value, see also _part_rev and _part_id."""
    _part_rev = ROUnaryStruct(emc2101_regs.REG_REV, "<B")
    """Device Part revision field value, see also _mfg_id and _part_id."""
    _int_temp = ROUnaryStruct(emc2101_regs.INTERNAL_TEMP, "<b")

    _status = ROUnaryStruct(emc2101_regs.REG_STATUS, "<B")
    """Device status register. Read only. See STATUS_* constants."""
    _config = UnaryStruct(emc2101_regs.REG_CONFIG, "<B")
    """Device config register. See CONFIG_* constants."""

    # Some of these registers are defined as two halves because the chip does
    # not support multi-byte reads or writes, and there is currently no way to
    # tell Struct to do a transaction for each byte.

    # IMPORTANT!
    # The sign bit for the external temp is in the msbyte so mark it as signed
    #     and lsb as unsigned.
    # The Lsbyte is shadow-copied when Msbyte is read, so read Msbyte first to
    #     avoid risk of bad reads. See datasheet section 6.1 Data Read Interlock.
    _ext_temp_msb = ROUnaryStruct(emc2101_regs.EXTERNAL_TEMP_MSB, "<b")
    # Fractions of degree (b7:0.5, b6:0.25, b5:0.125)
    _ext_temp_lsb = ROUnaryStruct(emc2101_regs.EXTERNAL_TEMP_LSB, "<B")

    # IMPORTANT!
    # The Msbyte is shadow-copied when Lsbyte is read, so read Lsbyte first to
    #     avoid bad reads. See datasheet section 6.1 Data Read Interlock.
    _tach_read_lsb = ROUnaryStruct(emc2101_regs.TACH_LSB, "<B")
    """LS byte of the tachometer result reading. """
    _tach_read_msb = ROUnaryStruct(emc2101_regs.TACH_MSB, "<B")
    """MS byte of the tachometer result reading. """

    _tach_mode_enable = RWBit(emc2101_regs.REG_CONFIG, 2)
    """The 2 bits of the tach mode config register. """
    _tach_limit_lsb = UnaryStruct(emc2101_regs.TACH_LIMIT_LSB, "<B")
    _tach_limit_msb = UnaryStruct(emc2101_regs.TACH_LIMIT_MSB, "<B")

    # Temperature used to override current external temp measurement.
    # Value is 7-bit + sign (one's complement?)
    forced_ext_temp = UnaryStruct(emc2101_regs.TEMP_FORCE, "<b")
    """The value that the external temperature will be forced to read when
    `forced_temp_enabled` is set. This can be used to test the behavior of the
    LUT without real temperature changes. Force Temp is 7-bit + sign (one's
    complement?)."""
    # public for back-compat reasons only.
    forced_temp_enabled = RWBit(emc2101_regs.FAN_CONFIG, 6)
    """When True, the external temperature measurement will always be read as
    the value in `forced_ext_temp`. Not applicable if LUT disabled."""

    # PWM/Fan control
    _fan_setting = UnaryStruct(emc2101_regs.REG_FAN_SETTING, "<B")
    """Control register for the fan."""
    _pwm_freq = RWBits(5, emc2101_regs.PWM_FREQ, 0)
    """Fan/PWM frequency setting register. Source frequency is derived via
    the fan pwm divisor."""
    _pwm_freq_div = UnaryStruct(emc2101_regs.PWM_FREQ_DIV, "<B")
    """Fan/PWM frequency divisor register. Controls source frequency for the
    pwm_freq register."""
    # public for back-compat reasons only.
    invert_fan_output = RWBit(emc2101_regs.FAN_CONFIG, 4)
    """When set to True, the magnitude of the fan output signal is inverted, making 0 the maximum
    value and 100 the minimum value"""
    _fan_lut_prog = RWBit(emc2101_regs.FAN_CONFIG, 5)
    """Programming-enable (write-enable) bit for the LUT registers."""

    _fan_temp_hyst = RWBits(5, emc2101_regs.FAN_TEMP_HYST, 0)
    """The amount of hysteresis ("wiggle-room") applied to temp input to the
    look up table."""

    _dac_output_enabled = RWBit(emc2101_regs.REG_CONFIG, 4)
    """Bit controlling whether DAC output (pure analog, not PWM) control of
    fan speed is enabled. This should not be enabled unless the hardware is
    also set up for it as, typically, a power transistor is needed on the
    output line. See datasheet section 5.6 for more detail.
    """

    _conversion_rate = RWBits(4, emc2101_regs.CONVERT_RATE, 0)
    """The number of times/second the temperature is sampled, varying from
    1 every 16 seconds to 32 times per second.
    """

    # Fan spin-up
    _spin_drive = RWBits(2, emc2101_regs.FAN_SPINUP, 3)
    """Set the drive circuit power during spin up, from bypass, 50%, 75% and 100%."""
    _spin_time = RWBits(3, emc2101_regs.FAN_SPINUP, 0)
    """Set the time the fan drive stays in spin_up, from 0 to 3.2 sec."""
    _spin_tach_limit = RWBit(emc2101_regs.FAN_SPINUP, 5)
    """Set whether spin-up is aborted if measured speed is lower than the limit.
    Ignored unless _tach_mode_enable is 1."""

    def __init__(self, i2c_bus: I2C) -> None:
        # These devices don't ship with any other address.
        self.i2c_device = i2cdevice.I2CDevice(i2c_bus, emc2101_regs.I2C_ADDR)
        part = self._part_id
        mfg = self._mfg_id
        # print("EMC2101 (part={}.{})".format(part, mfg))

        if (
            part not in {emc2101_regs.PART_ID_EMC2101, emc2101_regs.PART_ID_EMC2101R}
            or mfg != emc2101_regs.MFG_ID_SMSC
        ):
            raise RuntimeError(f"No EMC2101 (part={part}.{mfg})")

        self._full_speed_lsb = None  # See _calculate_full_speed().
        self.initialize()

    def initialize(self) -> None:
        """Reset the controller to an initial default configuration"""
        self._tach_mode_enable = True
        self._enabled_forced_temp = False
        self._spin_tach_limit = False
        self._calculate_full_speed()

    @property
    def part_info(self) -> Tuple[int, int, int]:
        """The part information: manufacturer, part id and revision.
        Normally returns (0x5d, 0x16, 0x1).
        """
        return (self._mfg_id, self._part_id, self._part_rev)

    @property
    def devconfig(self) -> int:
        """Read the main device config register.
        See the CONFIG_* bit definitions in the emc2101_regs module, or refer
        to the datasheet for more detail. Note: this is not the Fan Config
        register!
        """
        return self._config

    @property
    def devstatus(self) -> int:
        """Read device status (alerts) register. See the STATUS_* bit
        definitions in the emc2101_regs module, or refer to the datasheet for
        more detail.
        """
        return self._status

    @property
    def internal_temperature(self) -> int:
        """The temperature as measured by the EMC2101's internal 8-bit
        temperature sensor, which validly ranges from 0 to 85 and does not
        support fractions (unlike the external readings).

        :return: int temperature in degrees centigrade.
        """
        return self._int_temp

    @property
    def external_temperature(self) -> float:
        """The temperature measured using the external diode. The value is
        read as a fixed-point 11-bit value ranging from -64 to approx 126,
        with fractional part of 1/8 degree.

        :return: float temperature in degrees centigrade.

        :raises RuntimeError: if the sensor pind (DP,DN) are open circuit
            (the sensor is disconnected).
        :raises RuntimeError: if the external temp sensor is a short circuit
            (not behaving like a diode).
        """

        temp_lsb = self._ext_temp_lsb
        temp_msb = self._ext_temp_msb
        full_tmp = (temp_msb << 8) | temp_lsb
        full_tmp >>= 5
        if full_tmp == emc2101_regs.TEMP_FAULT_OPENCIRCUIT:
            raise RuntimeError("Open circuit")
        if full_tmp == emc2101_regs.TEMP_FAULT_SHORT:
            raise RuntimeError("Short circuit")

        full_tmp *= 0.125
        return full_tmp

    @property
    def fan_speed(self) -> float:
        """The current speed in Revolutions per Minute (RPM).

        :return: float fan speed rounded to 2dp.
        """
        val = self._tach_read_lsb
        val |= self._tach_read_msb << 8
        if val < 1:
            raise OSError("Connection")
        return round(emc2101_regs.FAN_RPM_DIVISOR / val, 2)

    def _calculate_full_speed(self, pwm_f: int = None, dac: int = None) -> None:
        """Determine the LSB value for a 100% fan setting"""
        if dac is None:
            dac = self.dac_output_enabled

        if dac:
            # DAC mode is independent of PWM_F.
            self._full_speed_lsb = float(emc2101_regs.MAX_LUT_SPEED)
            return

        # PWM mode reaches 100% duty cycle at a 2*PWM_F setting.
        if pwm_f is None:
            pwm_f = self._pwm_freq

        # PWM_F=0 behaves like PWM_F=1.
        self._full_speed_lsb = 2.0 * max(1, pwm_f)

    def _speed_to_lsb(self, percentage: int) -> int:
        """Convert a fan speed percentage to a Fan Setting byte value"""
        return round((percentage / 100.0) * self._full_speed_lsb)

    @property
    def manual_fan_speed(self) -> float:
        """The fan speed used while the LUT is being updated and is unavailable. The
        speed is given as the fan's PWM duty cycle represented as a float percentage.
        The value roughly approximates the percentage of the fan's maximum speed.
        """
        raw_setting = self._fan_setting & emc2101_regs.MAX_LUT_SPEED
        fan_speed = self._full_speed_lsb
        if fan_speed < 1:
            raise OSError("Connection")
        return (raw_setting / fan_speed) * 100.0

    @manual_fan_speed.setter
    def manual_fan_speed(self, fan_speed: float) -> None:
        """The fan speed used while the LUT is being updated and is unavailable. The
        speed is given as the fan's PWM duty cycle represented as a float percentage.
        The value roughly approximates the percentage of the fan's maximum speed.

        :raises ValueError: if the fan_speed is not in the valid range
        """
        if not 0 <= fan_speed <= 100:
            raise ValueError("manual_fan_speed must be from 0-100")

        fan_speed_lsb = self._speed_to_lsb(fan_speed)
        lut_disabled = self._fan_lut_prog
        # Enable programming
        self._fan_lut_prog = True
        # Set
        self._fan_setting = fan_speed_lsb
        # Restore.
        self._fan_lut_prog = lut_disabled

    @property
    def dac_output_enabled(self) -> int:
        """When set, the fan control signal is output as a DC voltage instead
        of a PWM signal."""
        return self._dac_output_enabled

    @dac_output_enabled.setter
    def dac_output_enabled(self, value: int) -> None:
        """When set, the fan control signal is output as a DC voltage instead of
        a PWM signal.  Be aware that the DAC output very likely requires different
        hardware to the PWM output.  See datasheet and examples for info.
        """
        self._dac_output_enabled = value
        self._calculate_full_speed(dac=value)

    @property
    def lut_enabled(self) -> bool:
        """Enable or disable the internal look up table used to map a given
        temperature to a fan speed.

        When the LUT is disabled (the default), fan speed can be changed
        with `manual_fan_speed`. To actually set this to True and modify
        the LUT, you need to use the extended version of this driver,
        :class:`emc2101_lut.EMC2101_LUT`."""
        return not self._fan_lut_prog

    @property
    def tach_limit(self) -> float:
        """The maximum speed expected for the fan. If the fan exceeds this
        speed, the status register TACH bit will be set.

        :return float: fan speed limit in RPM
        :raises OSError: if the limit is 0 (not a permitted value)
        """
        low = self._tach_limit_lsb
        high = self._tach_limit_msb
        limit = high << 8 | low
        if limit < 1:
            raise OSError("Connection")
        return round(emc2101_regs.FAN_RPM_DIVISOR / limit, 2)

    @tach_limit.setter
    def tach_limit(self, new_limit: float) -> None:
        """Set the speed limiter on the fan PWM signal. The value of
        15000 is arbitrary, but very few fans run faster than this. If the
        fan exceeds this speed, the status register TACH bit will be set.

        Note that the device will _not_ automatically adjust the PWM speed to
        enforce this limit.

        :param new_limit: fan speed limit in RPM
        :raises OSError: if the limit is 0 (not a permitted value)
        :raises ValueError: if the new_limit is not in the valid range
        """
        if not 1 <= new_limit <= 15000:
            raise ValueError("tach_limit must be from 1-15000")
        num = int(emc2101_regs.FAN_RPM_DIVISOR / new_limit)
        self._tach_limit_lsb = num & 0xFF
        self._tach_limit_msb = (num >> 8) & 0xFF

    @property
    def spinup_time(self) -> int:
        """The amount of time the fan will spin at the currently set drive
        strength.

        :return int: corresponding to the SpinupTime enumeration.
        """
        return self._spin_time

    @spinup_time.setter
    def spinup_time(self, spin_time: int) -> None:
        """Set the time that the SpinupDrive value will be used to get the
        fan moving before the normal speed controls are activated. This is
        needed because fan motors typically need a 'kick' to get them moving,
        but after this they can slow down further.

        Usage:
        .. code-block:: python

            from adafruit_emc2101_enums import SpinupTime
            emc.spinup_drive = SpinupTime.SPIN_1_6_SEC

        :raises TypeError: if spin_drive is not an instance of SpinupTime
        """
        # Not importing at top level so the SpinupTime is not loaded
        # unless it is required, and thus 1KB bytecode can be avoided.
        from adafruit_emc2101.emc2101_enums import SpinupTime  # noqa: PLC0415

        if not SpinupTime.is_valid(spin_time):
            raise TypeError("spinup_time must be a SpinupTime")
        self._spin_time = spin_time

    @property
    def spinup_drive(self) -> int:
        """The drive strength of the fan on spinup in % max PWM duty cycle
        (which approximates to max fan speed).

        :return int: corresponding to the SpinupDrive enumeration.
        """
        return self._spin_drive

    @spinup_drive.setter
    def spinup_drive(self, spin_drive: int) -> None:
        """Set the drive (pwm duty percentage) that the SpinupTime value is applied
        to move the fan before the normal speed controls are activated. This is needed
        because fan motors typically need a 'kick' to get them moving, but after this
        they can slow down further.

        Usage:
        .. code-block:: python

            from adafruit_emc2101_enums import SpinupDrive
            emc.spinup_drive = SpinupDrive.DRIVE_50

        :raises TypeError: if spin_drive is not an instance of SpinupDrive
        """
        # Not importing at top level so the SpinupDrive is not loaded
        # unless it is required, and thus 1KB bytecode can be avoided.
        from adafruit_emc2101.emc2101_enums import SpinupDrive  # noqa: PLC0415

        if not SpinupDrive.is_valid(spin_drive):
            raise TypeError("spinup_drive must be a SpinupDrive")
        self._spin_drive = spin_drive

    @property
    def conversion_rate(self) -> int:
        """The rate at which temperature measurements are taken.

        :return int: corresponding to the ConversionRate enumeration."""
        return self._conversion_rate

    @conversion_rate.setter
    def conversion_rate(self, rate: int) -> None:
        """Set the rate at which the external temperature is checked by
        the device. Reducing this rate can reduce power consumption.

        Usage:

        .. code-block:: python

            from adafruit_emc2101_enums import ConversionRate
            emc.conversion_rate = ConversionRate.RATE_1_2

        :raises TypeError: if spin_drive is not an instance of ConversionRate
        """
        # Not importing at top level so the ConversionRate is not loaded
        # unless it is required, and thus 1KB bytecode can be avoided.
        from adafruit_emc2101.emc2101_enums import ConversionRate  # noqa: PLC0415

        if not ConversionRate.is_valid(rate):
            raise ValueError("conversion_rate must be a `ConversionRate`")
        self._conversion_rate = rate
