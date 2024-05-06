#!/bin/bash

# SPDX-FileCopyrightText: 2024 Jev Kuznetsov, ROX Automation
#
# SPDX-License-Identifier: MIT


# this script prepares the host for the devcontainer.


# it is easier to use this script to pre-build the image, instead of using
# `build` directive in `devcontainer.json`. Less chance of errors ducing container start.

IMG_NAME="local/circup-dev"
# Get the directory of the script
SCRIPT_DIR=$(dirname "$0")

# create a directory for the container extensions to avoid reinstallation
# on container rebuild. Mounted inside devcontainer.
mkdir -p /var/tmp/container-extensions


# buld image
echo "Building image $IMG_NAME"
docker build -t $IMG_NAME --build-arg UID=$(id -u) --build-arg GID=$(id -g) -f $SCRIPT_DIR/Dockerfile $SCRIPT_DIR
