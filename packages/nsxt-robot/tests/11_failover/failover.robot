*** Settings ***
Documentation    Fault-injection / resilience regression suite: segment (T0/T0-VRF uplink
...              proxy), BGP, and edge-node failures, each verified from the data plane
...              with bbprobe and then restored. Builds the same two-T1 topology as
...              tests/08_dfw (VM1 on SEG_A/T1A, VM2 on SEG_B/T1B) so a segment failure
...              has an observable effect on VM1 -> VM2 reachability.
...
...              Tags: `ha` needs >= 2 edge nodes in ${EDGE_CLUSTER_ID} (one drains, the
...              other carries traffic) — skip with `-e ha` on a single-edge lab.
...              `destructive` tests (edge dataplane restart / reboot) run only when
...              ${EDGE_PASSWORD} is set; they cause a real outage on that edge — lab use
...              only. Exclude the whole category with `-e destructive`.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Resource         nsxt_robot/resources/failure_keywords.robot
Suite Setup      Failover Suite Setup
Suite Teardown   Failover Suite Teardown
Test Tags        failover


*** Variables ***
${T1A_ID}      test-t1-failover-a
${T1B_ID}      test-t1-failover-b
${SEG_A_ID}    test-seg-failover-a
${SEG_B_ID}    test-seg-failover-b
${T1A_PATH}    /infra/tier-1s/${T1A_ID}
${T1B_PATH}    /infra/tier-1s/${T1B_ID}
# Owned by this suite (distinct from 04_bgp_bfd's neighbor) so the BGP-failure test is
# self-contained regardless of suite run order.
${FAILOVER_NEIGHBOR_ID}    test-bgp-neighbor-failover


*** Keywords ***
Failover Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    T1-Failover-A    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create T1 Gateway    ${T1B_ID}    T1-Failover-B    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}
    Create Overlay Segment    ${SEG_B_ID}    ${T1B_PATH}    ${OVERLAY_TZ_PATH}    ${T1B_SEGMENT_CIDR}
    Wait For Realizations    ${POLICY_BASE}${T1A_PATH}    ${POLICY_BASE}${T1B_PATH}
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}    ${POLICY_BASE}/infra/segments/${SEG_B_ID}
    Configure BGP On T0    ${T0_GATEWAY_ID}    default    ${BGP_LOCAL_ASN}
    Create BGP Neighbor On T0    ${T0_GATEWAY_ID}    default    ${FAILOVER_NEIGHBOR_ID}    ${BGP_PEER_IP}    ${BGP_PEER_ASN}
    ${edge1_nsx_id}=    Get Edge Node Nsx Id From Cluster    ${EDGE_CLUSTER_ID}    0
    Set Suite Variable    ${EDGE1_NSX_ID}    ${edge1_nsx_id}

Verify Failover BGP Is Established
    [Documentation]    Composes GET + assert into one keyword — Wait Until Keyword
    ...                Succeeds retries a single keyword call, not a keyword chain.
    ${status}=    Get BGP Neighbor Status    ${T0_GATEWAY_ID}    default    ${FAILOVER_NEIGHBOR_ID}
    BGP Neighbor Should Be Established    ${status}

Verify Failover BGP Is Down
    [Documentation]    Composes GET + assert for the down-state poll (see above).
    ${status}=    Get BGP Neighbor Status    ${T0_GATEWAY_ID}    default    ${FAILOVER_NEIGHBOR_ID}
    BGP Neighbor Should Be Down    ${status}

Failover Suite Teardown
    # Best-effort undo of any failure left injected by a failed test, before tearing
    # down the topology itself.
    Run Keyword And Ignore Error    Restore Segment    ${SEG_B_ID}
    Run Keyword And Ignore Error    Enable BGP On T0 Locale Service    ${T0_GATEWAY_ID}
    Run Keyword And Ignore Error    Exit Edge Maintenance Mode    ${EDGE1_NSX_ID}
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/tier-0s/${T0_GATEWAY_ID}/locale-services/default/bgp/neighbors/${FAILOVER_NEIGHBOR_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_B_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1B_ID}


*** Test Cases ***
Verify Baseline Connectivity
    [Documentation]    Before any fault injection, VM1 must reach VM2 across the topology.
    [Tags]    baseline
    Ping From VM    ${VM1_IP}    ${VM2_IP}

Segment Failure Blocks Then Recovers Traffic
    [Documentation]    Setting SEG_B admin_state DOWN represents a segment (or T0/T0-VRF
    ...                uplink) failure: VM2's segment goes down, so VM1 -> VM2 must stop
    ...                working, then recover once the segment is restored.
    [Tags]    segment
    Fail Segment    ${SEG_B_ID}
    Data Plane Should Be Down Within    ${VM1_IP}    icmp    ${VM2_IP}
    Restore Segment    ${SEG_B_ID}
    Data Plane Should Recover Within    ${VM1_IP}    icmp    ${VM2_IP}

BGP Session Failure Is Detected And Restored
    [Documentation]    Disabling BGP on the parent T0's locale service must move the
    ...                suite's own neighbor (created in Suite Setup) out of ESTABLISHED;
    ...                re-enabling must restore it.
    [Tags]    bgp
    Wait Until Keyword Succeeds    3 min    15 sec    Verify Failover BGP Is Established
    Disable BGP On T0 Locale Service    ${T0_GATEWAY_ID}
    Wait Until Keyword Succeeds    1 min    5 sec    Verify Failover BGP Is Down
    Enable BGP On T0 Locale Service    ${T0_GATEWAY_ID}
    Wait Until Keyword Succeeds    2 min    10 sec    Verify Failover BGP Is Established

Edge Maintenance Mode Fails Traffic Over
    [Documentation]    Draining edge 0 must not break VM1 -> VM2 connectivity for longer
    ...                than ${FAILOVER_MAX_RECOVERY} — traffic should fail over to the
    ...                peer edge. Requires >= 2 edges in ${EDGE_CLUSTER_ID}.
    [Tags]    ha
    Enter Edge Maintenance Mode    ${EDGE1_NSX_ID}
    ${node}=    Wait Until Keyword Succeeds    1 min    5 sec    Get Transport Node    ${EDGE1_NSX_ID}
    Transport Node Should Be In Maintenance    ${node}
    Data Plane Should Recover Within    ${VM1_IP}    icmp    ${VM2_IP}
    Exit Edge Maintenance Mode    ${EDGE1_NSX_ID}

Edge Dataplane Restart Recovers Within SLA
    [Documentation]    DESTRUCTIVE: restarts the dataplane service on EDGE1_MGMT_IP over
    ...                SSH and asserts traffic recovers within ${FAILOVER_MAX_RECOVERY}.
    ...                Skipped unless ${EDGE_PASSWORD} is set.
    [Tags]    destructive
    Skip If    '${EDGE_PASSWORD}' == '${EMPTY}'    EDGE_PASSWORD not set — skipping destructive edge test
    Restart Edge Dataplane    ${EDGE1_MGMT_IP}
    Data Plane Should Recover Within    ${VM1_IP}    icmp    ${VM2_IP}

Edge Reboot Recovers Within Extended SLA
    [Documentation]    DESTRUCTIVE: reboots EDGE1_MGMT_IP over SSH and asserts traffic
    ...                recovers within ${EDGE_REBOOT_MAX_RECOVERY} (minutes, not seconds).
    ...                Skipped unless ${EDGE_PASSWORD} is set.
    [Tags]    destructive    reboot
    Skip If    '${EDGE_PASSWORD}' == '${EMPTY}'    EDGE_PASSWORD not set — skipping destructive edge test
    Reboot Edge Node    ${EDGE1_MGMT_IP}
    Data Plane Should Recover Within    ${VM1_IP}    icmp    ${VM2_IP}    ${EDGE_REBOOT_MAX_RECOVERY}
