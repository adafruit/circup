# SPDX-FileCopyrightText: Copyright (c) 2020 Bryan Siepert for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2022 Ruth Ivimey-Cook
#
# SPDX-License-Identifier: MIT
"""
`adafruit_emc2101.emc2101_enums`
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

try:
    from typing import Iterable, Optional, Tuple
except ImportError:
    pass


class CV:
    """struct helper"""

    @classmethod
    def add_values(
        cls, value_tuples: Iterable[Tuple[str, int, str, Optional[float]]]
    ) -> None:
        """Creates CV entries"""
        cls.string = {}
        cls.lsb = {}
        for value_tuple in value_tuples:
            name, value, string, lsb = value_tuple
            setattr(cls, name, value)
            cls.string[value] = string
            cls.lsb[value] = lsb

    @classmethod
    def is_valid(cls, value: int) -> bool:
        "Returns true if the given value is a member of the CV"
        return value in cls.string


class ConversionRate(CV):
    """Options for ``conversion_rate``"""


ConversionRate.add_values(
    (
        ("RATE_1_16", 0, str(1 / 16.0), None),
        ("RATE_1_8", 1, str(1 / 8.0), None),
        ("RATE_1_4", 2, str(1 / 4.0), None),
        ("RATE_1_2", 3, str(1 / 2.0), None),
        ("RATE_1", 4, str(1.0), None),
        ("RATE_2", 5, str(2.0), None),
        ("RATE_4", 6, str(4.0), None),
        ("RATE_8", 7, str(8.0), None),
        ("RATE_16", 8, str(16.0), None),
        ("RATE_32", 9, str(32.0), None),
    )
)


class SpinupDrive(CV):
    """Options for ``spinup_drive``"""


SpinupDrive.add_values(
    (
        ("BYPASS", 0, "Disabled", None),
        ("DRIVE_50", 1, "50% Duty Cycle", None),
        ("DRIVE_75", 2, "25% Duty Cycle", None),
        ("DRIVE_100", 3, "100% Duty Cycle", None),
    )
)


class SpinupTime(CV):
    """Options for ``spinup_time``"""


SpinupTime.add_values(
    (
        ("BYPASS", 0, "Disabled", None),
        ("SPIN_0_05_SEC", 1, "0.05 seconds", None),
        ("SPIN_0_1_SEC", 2, "0.1 seconds", None),
        ("SPIN_0_2_SEC", 3, "0.2 seconds", None),
        ("SPIN_0_4_SEC", 4, "0.4 seconds", None),
        ("SPIN_0_8_SEC", 5, "0.8 seconds", None),
        ("SPIN_1_6_SEC", 6, "1.6 seconds", None),
        ("SPIN_3_2_SEC", 7, "3.2 seconds", None),
    )
)
