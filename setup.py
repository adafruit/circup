#!/usr/bin/env python3
import os
import re
from setuptools import setup


base_dir = os.path.dirname(__file__)


DUNDER_ASSIGN_RE = re.compile(r"""^__\w+__\s*=\s*['"].+['"]$""")
about = {}
with open(os.path.join(base_dir, "circup.py"), encoding="utf8") as f:
    for line in f:
        if DUNDER_ASSIGN_RE.search(line):
            exec(line, about)


with open(os.path.join(base_dir, "README.rst"), encoding="utf8") as f:
    readme = f.read()

with open(os.path.join(base_dir, "CHANGES.rst"), encoding="utf8") as f:
    changes = f.read()


install_requires = [
    "semver>=2.8.1",
    "Click>=7.0",
    "appdirs>=1.4.3",
    "requests>=2.22.0",
]

extras_require = {
    "tests": [
        "pytest",
        "pytest-cov",
        "pytest-random-order>=1.0.0",
        "pytest-faulthandler",
        "coverage",
        "pycodestyle",
        "pyflakes",
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
    name=about["__title__"],
    version=about["__version__"],
    description=about["__description__"],
    long_description="{}\n\n{}".format(readme, changes),
    author=about["__author__"],
    author_email=about["__email__"],
    url=about["__url__"],
    license=about["__license__"],
    py_modules=["circup"],
    install_requires=install_requires,
    extras_require=extras_require,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Education",
        "Topic :: Software Development :: Embedded Systems",
        "Topic :: System :: Software Distribution",
    ],
    entry_points={"console_scripts": ["circup=circup:main"]},
)
