"""Unit tests for the pure logic in nsxt_robot.api (run with pytest)."""

import pytest

from nsxt_robot import NsxtApi


@pytest.fixture
def api():
    return NsxtApi()


# ── extraction ───────────────────────────────────────────────────────────────


def test_get_value_dotted(api):
    data = {"mgmt_cluster_status": {"status": "STABLE"}}
    assert api.get_value(data, "mgmt_cluster_status.status") == "STABLE"


def test_get_value_list_index(api):
    data = {"members": [{"status": "UP"}, {"status": "DOWN"}]}
    assert api.get_value(data, "members.1.status") == "DOWN"


def test_get_value_missing_key_raises(api):
    with pytest.raises(AssertionError, match="Key 'nope' not found"):
        api.get_value({"a": 1}, "nope")


def test_find_in_list_from_results_body(api):
    body = {"results": [{"id": "r1"}, {"id": "r2", "action": "SNAT"}]}
    assert api.find_in_list(body, "id", "r2")["action"] == "SNAT"


def test_find_in_list_not_found_raises(api):
    with pytest.raises(AssertionError, match="No item with id='x'"):
        api.find_in_list([{"id": "r1"}], "id", "x")


def test_get_ids_prefers_id_then_display_name(api):
    body = {"results": [{"id": "a"}, {"display_name": "b"}]}
    assert api.get_ids(body) == ["a", "b"]


# ── typed assertions ─────────────────────────────────────────────────────────


def test_realized_state_success(api):
    api.realized_state_should_be_success(
        {"consolidated_status": {"consolidated_status": "SUCCESS"}}
    )


def test_realized_state_failure_raises(api):
    with pytest.raises(AssertionError, match="expected 'SUCCESS'"):
        api.realized_state_should_be_success(
            {"consolidated_status": {"consolidated_status": "ERROR"}}
        )


def test_manager_cluster_stable(api):
    api.manager_cluster_should_be_stable({"mgmt_cluster_status": {"status": "STABLE"}})


def test_manager_cluster_unstable_raises(api):
    with pytest.raises(AssertionError):
        api.manager_cluster_should_be_stable(
            {"mgmt_cluster_status": {"status": "DEGRADED"}}
        )


def test_compute_manager_registered(api):
    api.compute_manager_should_be_registered({"registration_status": "REGISTERED"})


def test_bgp_established(api):
    api.bgp_neighbor_should_be_established({"connection_state": "ESTABLISHED"})


def test_bgp_not_established_raises(api):
    with pytest.raises(AssertionError):
        api.bgp_neighbor_should_be_established({"connection_state": "CONNECT"})


def test_bgp_neighbor_down(api):
    api.bgp_neighbor_should_be_down({"connection_state": "IDLE"})


def test_bgp_neighbor_down_but_established_raises(api):
    with pytest.raises(AssertionError, match="expected it to be down"):
        api.bgp_neighbor_should_be_down({"connection_state": "ESTABLISHED"})


def test_transport_node_in_maintenance(api):
    api.transport_node_should_be_in_maintenance({"maintenance_mode": "ENABLED"})


def test_transport_node_not_in_maintenance_raises(api):
    with pytest.raises(AssertionError, match="expected 'ENABLED'"):
        api.transport_node_should_be_in_maintenance({"maintenance_mode": "DISABLED"})


def test_bfd_healthy(api):
    api.bfd_should_be_healthy({"bfd_diagnostic_code": 0})


def test_bfd_unhealthy_raises(api):
    with pytest.raises(AssertionError):
        api.bfd_should_be_healthy({"bfd_diagnostic_code": 3})


def test_pool_member_up(api):
    api.pool_member_should_be_up({"members": [{"ip_address": "1.1.1.1", "status": "UP"}]})


def test_pool_member_down_raises(api):
    with pytest.raises(AssertionError, match="not UP"):
        api.pool_member_should_be_up(
            {"members": [{"ip_address": "1.1.1.1", "status": "DOWN"}]}
        )


def test_pool_member_empty_raises(api):
    with pytest.raises(AssertionError, match="No pool members"):
        api.pool_member_should_be_up({"members": []})


def test_nat_rule_should_exist_with_action_and_translated(api):
    body = {
        "results": [
            {"id": "snat-1", "action": "SNAT", "translated_network": "10.0.0.50"}
        ]
    }
    rule = api.nat_rule_should_exist(body, "snat-1", action="SNAT", translated="10.0.0.50")
    assert rule["id"] == "snat-1"


def test_nat_rule_wrong_translated_raises(api):
    body = {"results": [{"id": "snat-1", "action": "SNAT", "translated_network": "10.0.0.50"}]}
    with pytest.raises(AssertionError, match="translated_network"):
        api.nat_rule_should_exist(body, "snat-1", translated="10.0.0.99")


def test_nat_rule_dnat_action(api):
    body = {
        "results": [
            {"id": "dnat-1", "action": "DNAT", "translated_network": "172.16.1.10"}
        ]
    }
    rule = api.nat_rule_should_exist(body, "dnat-1", action="DNAT", translated="172.16.1.10")
    assert rule["action"] == "DNAT"


# ── VRF ──────────────────────────────────────────────────────────────────────


def test_vrf_linked_to_parent(api):
    body = {"id": "vrf-red", "vrf_config": {"tier0_path": "/infra/tier-0s/t0-gw"}}
    api.vrf_should_be_linked_to_parent(body, "/infra/tier-0s/t0-gw")


def test_vrf_wrong_parent_raises(api):
    body = {"id": "vrf-red", "vrf_config": {"tier0_path": "/infra/tier-0s/other-t0"}}
    with pytest.raises(AssertionError, match="expected parent"):
        api.vrf_should_be_linked_to_parent(body, "/infra/tier-0s/t0-gw")


def test_vrf_not_a_vrf_raises(api):
    with pytest.raises(AssertionError, match="Key 'vrf_config' not found"):
        api.vrf_should_be_linked_to_parent({"id": "plain-t0"}, "/infra/tier-0s/t0-gw")


# ── DFW / groups ─────────────────────────────────────────────────────────────


def test_dfw_rule_action_matches(api):
    body = {"results": [{"id": "deny-1", "action": "DROP"}, {"id": "allow-1", "action": "ALLOW"}]}
    assert api.dfw_rule_should_have_action(body, "deny-1", "DROP")["id"] == "deny-1"


def test_dfw_rule_wrong_action_raises(api):
    body = {"results": [{"id": "deny-1", "action": "ALLOW"}]}
    with pytest.raises(AssertionError, match="expected 'DROP'"):
        api.dfw_rule_should_have_action(body, "deny-1", "DROP")


def test_dfw_rule_missing_raises(api):
    with pytest.raises(AssertionError, match="No item with id='deny-1'"):
        api.dfw_rule_should_have_action({"results": []}, "deny-1", "DROP")


def test_gateway_firewall_rule_action_matches(api):
    body = {"results": [{"id": "deny-1", "action": "DROP"}, {"id": "allow-1", "action": "ALLOW"}]}
    assert api.gateway_firewall_rule_should_have_action(body, "deny-1", "DROP")["id"] == "deny-1"


def test_gateway_firewall_rule_wrong_action_raises(api):
    body = {"results": [{"id": "deny-1", "action": "ALLOW"}]}
    with pytest.raises(AssertionError, match="expected 'DROP'"):
        api.gateway_firewall_rule_should_have_action(body, "deny-1", "DROP")


def test_gateway_firewall_rule_missing_raises(api):
    with pytest.raises(AssertionError, match="No item with id='deny-1'"):
        api.gateway_firewall_rule_should_have_action({"results": []}, "deny-1", "DROP")


def test_group_member_matches_by_ip(api):
    body = {"results": [{"display_name": "web-vm", "ip_addresses": ["172.16.1.10"]}]}
    assert api.group_should_have_member(body, "172.16.1.10")["display_name"] == "web-vm"


def test_group_member_matches_by_name(api):
    body = {"results": [{"display_name": "web-vm", "ip_addresses": []}]}
    assert api.group_should_have_member(body, "web-vm")["display_name"] == "web-vm"


def test_group_member_missing_raises(api):
    with pytest.raises(AssertionError, match="No group member matching"):
        api.group_should_have_member({"results": []}, "172.16.1.10")
