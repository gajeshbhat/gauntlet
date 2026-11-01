"""Shapes of names that end up on a command line: anything else is refused before it gets there."""

import re

IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]*$")  # a container image reference; never starts with "-"
MEMORY = re.compile(r"^[0-9]+[kmg]?$")  # 512m, 4g
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
