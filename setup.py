# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT


"""A setuptools based setup module.
See:
https://packaging.python.org/guides/distributing-packages-using-setuptools/
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages

# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

install_requires = [
    "semver~=2.13",
    "Click>=7.0",
    "appdirs>=1.4.3",
    "requests>=2.22.0",
]

extras_require = {
    "tests": [
        "pytest",
        "pylint",
        "pytest-cov",
        "pytest-random-order>=1.0.0",
        "pytest-faulthandler",
        "coverage",
        "black",
    ],
    "docs": ["sphinx"],
    "package": [
        # Wheel building and PyPI uploading
        "wheel",
        "twine",
    ],
}

extras_require["dev"] = (
    extras_require["tests"] + extras_require["docs"] + extras_require["package"]
)

extras_require["all"] = list(
    {req for extra, reqs in extras_require.items() for req in reqs}
)

setup(
    name="circup",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description="A tool to manage/update libraries on CircuitPython devices.",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    # The project's main homepage.
    url="https://github.com/adafruit/circup",
    # Author details
    author="Adafruit Industries",
    author_email="circuitpython@adafruit.com",
    install_requires=install_requires,
    extras_require=extras_require,
    # Choose your license
    license="MIT",
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Education",
        "Topic :: Software Development :: Embedded Systems",
        "Topic :: System :: Software Distribution",
    ],
    entry_points={"console_scripts": ["circup=circup:main"]},
    # What does your project relate to?
    keywords="adafruit, blinka, circuitpython, micropython, libraries",
    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    py_modules=["circup"],
)
