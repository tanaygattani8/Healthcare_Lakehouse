"""Deliberately broken. Exists to prove the PR gate can fail (errors.md E33).

Delete this file and the ci/prove-red branch once the gate has been seen red.
"""
import os
import sys


def unused_and_unsorted():
    x = 1
    return 2
