"""nsxt_robot — a reusable Robot Framework library for testing VMware NSX-T.

Provides ``NsxtApi`` (JSON extraction + typed status assertions for the NSX-T
Policy/Management API) plus a set of ``.robot`` resource files — packaged under
``nsxt_robot/resources/`` — covering REST session/realization helpers, NSX-T
Policy API operations, SSH traffic keywords, and structured ``bbprobe``
data-plane probing.

Typical usage from a consuming suite::

    *** Settings ***
    Library     nsxt_robot.NsxtApi
    Resource    nsxt_robot/resources/common.robot
    Resource    nsxt_robot/resources/policy_api.robot
"""

from __future__ import annotations

from .api import NsxtApi
from .bbprobe_release import BbprobeRelease

__version__ = "0.1.0"
__all__ = ["BbprobeRelease", "NsxtApi", "__version__"]
