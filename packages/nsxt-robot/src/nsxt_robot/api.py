"""NsxtApi — Robot Framework keyword library for extracting and asserting on
NSX-T Policy/Management API JSON responses.

Used *alongside* RESTinstance: the ``policy_api.robot`` keywords still make the
HTTP calls and return parsed bodies; these keywords operate on those bodies to
replace the verbose ``Get From Dictionary`` chains and ``Evaluate next(...)``
patterns scattered through the suites.

Pure Python, no third-party dependencies.
"""

from __future__ import annotations

from typing import Any

from robot.api.deco import keyword, library


def _unwrap(data: Any) -> Any:
    """Return the ``results`` list when handed a list-style API body."""
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def _walk(data: Any, path: str) -> Any:
    """Walk a dotted path with numeric list indices, e.g. ``a.b.0.c``."""
    current = data
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise AssertionError(
                    f"Path segment '{part}' is not a valid index into a list of "
                    f"length {len(current)} (full path: '{path}')"
                ) from exc
        elif isinstance(current, dict):
            if part not in current:
                raise AssertionError(
                    f"Key '{part}' not found while resolving path '{path}'. "
                    f"Available keys: {sorted(current)}"
                )
            current = current[part]
        else:
            raise AssertionError(
                f"Cannot descend into '{part}' of a {type(current).__name__} "
                f"(full path: '{path}')"
            )
    return current


@library(scope="GLOBAL", auto_keywords=False)
class NsxtApi:
    """Extraction and typed-assertion keywords for NSX-T API responses."""

    ROBOT_LIBRARY_VERSION = "1.0.0"

    # ── extraction ───────────────────────────────────────────────────────────

    @keyword
    def get_value(self, data: Any, path: str) -> Any:
        """Return the value at a dotted/indexed ``path`` inside ``data``.

        Example: ``Get Value  ${status}  mgmt_cluster_status.status`` or
        ``Get Value  ${pool}  members.0.status``.
        """
        return _walk(data, path)

    @keyword
    def find_in_list(self, items: Any, key: str, value: Any) -> dict:
        """Return the first dict in ``items`` whose ``key`` equals ``value``.

        ``items`` may be a raw list or an API body containing ``results``.
        Replaces ``Evaluate  next(r for r in ... )``.
        """
        for item in _unwrap(items):
            if isinstance(item, dict) and str(item.get(key)) == str(value):
                return item
        raise AssertionError(
            f"No item with {key}={value!r} found in list of {len(_unwrap(items))} item(s)"
        )

    @keyword
    def get_ids(self, list_body: Any) -> list:
        """Return the ``id`` (or ``display_name``) of every item in a list body."""
        return [
            item.get("id", item.get("display_name", ""))
            for item in _unwrap(list_body)
            if isinstance(item, dict)
        ]

    # ── typed status assertions ──────────────────────────────────────────────

    @keyword
    def realized_state_should_be_success(self, body: Any) -> None:
        """Assert a realized-state status body reports ``SUCCESS``."""
        status = _walk(body, "consolidated_status.consolidated_status")
        if status != "SUCCESS":
            raise AssertionError(f"Realization status is '{status}', expected 'SUCCESS'")

    @keyword
    def manager_cluster_should_be_stable(self, status: Any) -> None:
        """Assert the NSX Manager cluster overall status is ``STABLE``."""
        state = _walk(status, "mgmt_cluster_status.status")
        if state != "STABLE":
            raise AssertionError(f"Manager cluster status is '{state}', expected 'STABLE'")

    @keyword
    def compute_manager_should_be_registered(self, cm_status: Any) -> None:
        """Assert a compute manager reports ``REGISTERED``."""
        state = _walk(cm_status, "registration_status")
        if state != "REGISTERED":
            raise AssertionError(
                f"Compute manager registration_status is '{state}', expected 'REGISTERED'"
            )

    @keyword
    def bgp_neighbor_should_be_established(self, status: Any) -> None:
        """Assert a BGP neighbor status body reports ``ESTABLISHED``."""
        state = _walk(status, "connection_state")
        if state != "ESTABLISHED":
            raise AssertionError(
                f"BGP connection_state is '{state}', expected 'ESTABLISHED'"
            )

    @keyword
    def bgp_neighbor_should_be_down(self, status: Any) -> None:
        """Assert a BGP neighbor status body does NOT report ``ESTABLISHED``.

        For asserting a fault injection (e.g. BGP disabled) actually took effect.
        """
        state = _walk(status, "connection_state")
        if state == "ESTABLISHED":
            raise AssertionError("BGP connection_state is 'ESTABLISHED', expected it to be down")

    @keyword
    def transport_node_should_be_in_maintenance(self, node_body: Any) -> None:
        """Assert a transport node body reports maintenance mode ``ENABLED``."""
        state = _walk(node_body, "maintenance_mode")
        if state != "ENABLED":
            raise AssertionError(
                f"Transport node maintenance_mode is '{state}', expected 'ENABLED'"
            )

    @keyword
    def bfd_should_be_healthy(self, status: Any) -> None:
        """Assert BFD diagnostic code is 0 (No Diagnostic = healthy)."""
        code = int(_walk(status, "bfd_diagnostic_code"))
        if code != 0:
            raise AssertionError(
                f"BFD diagnostic code is {code}, expected 0 (healthy session)"
            )

    @keyword
    def pool_member_should_be_up(self, pool_status: Any) -> None:
        """Assert every LB pool member reports ``UP``."""
        members = _walk(pool_status, "members")
        if not members:
            raise AssertionError("No pool members present in status")
        down = [m for m in members if m.get("status") != "UP"]
        if down:
            raise AssertionError(
                f"{len(down)} of {len(members)} pool member(s) not UP: "
                f"{[(m.get('ip_address'), m.get('status')) for m in down]}"
            )

    @keyword
    def dfw_rule_should_have_action(
        self, rules_body: Any, rule_id: str, action: str
    ) -> dict:
        """Assert a DFW rule exists in ``rules_body`` with the expected ``action``.

        ``action`` is one of ``ALLOW`` / ``DROP`` / ``REJECT``.
        """
        rule = self.find_in_list(rules_body, "id", rule_id)
        if rule.get("action") != action:
            raise AssertionError(
                f"DFW rule {rule_id} action is '{rule.get('action')}', expected '{action}'"
            )
        return rule

    @keyword
    def gateway_firewall_rule_should_have_action(
        self, rules_body: Any, rule_id: str, action: str
    ) -> dict:
        """Assert a Gateway Firewall rule exists in ``rules_body`` with the expected ``action``.

        ``action`` is one of ``ALLOW`` / ``DROP`` / ``REJECT``.
        """
        rule = self.find_in_list(rules_body, "id", rule_id)
        if rule.get("action") != action:
            raise AssertionError(
                f"Gateway Firewall rule {rule_id} action is '{rule.get('action')}', "
                f"expected '{action}'"
            )
        return rule

    @keyword
    def group_should_have_member(self, members_body: Any, ip_or_name: str) -> dict:
        """Assert a group's effective-member list contains a VM matching ``ip_or_name``.

        Matches against the member's ``display_name`` or any of its ``ip_addresses``.
        """
        for member in _unwrap(members_body):
            if not isinstance(member, dict):
                continue
            if member.get("display_name") == ip_or_name:
                return member
            if ip_or_name in (member.get("ip_addresses") or []):
                return member
        raise AssertionError(
            f"No group member matching '{ip_or_name}' in "
            f"{len(_unwrap(members_body))} effective member(s)"
        )

    @keyword
    def vrf_should_be_linked_to_parent(self, body: Any, parent_t0_path: str) -> None:
        """Assert a Tier-0 body is a VRF gateway linked to ``parent_t0_path``.

        Fails if the body has no ``vrf_config`` (i.e. it is not a VRF gateway)
        or if it is linked to a different parent Tier-0.
        """
        path = _walk(body, "vrf_config.tier0_path")
        if path != parent_t0_path:
            raise AssertionError(
                f"VRF is linked to '{path}', expected parent '{parent_t0_path}'"
            )

    @keyword
    def nat_rule_should_exist(
        self,
        rules_body: Any,
        rule_id: str,
        action: str | None = None,
        translated: str | None = None,
    ) -> dict:
        """Assert a NAT rule exists (optionally with ``action``/``translated``)."""
        rule = self.find_in_list(rules_body, "id", rule_id)
        if action is not None and rule.get("action") != action:
            raise AssertionError(
                f"NAT rule {rule_id} action is '{rule.get('action')}', expected '{action}'"
            )
        if translated is not None and rule.get("translated_network") != translated:
            raise AssertionError(
                f"NAT rule {rule_id} translated_network is "
                f"'{rule.get('translated_network')}', expected '{translated}'"
            )
        return rule
