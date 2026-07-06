*** Settings ***
Documentation    T1 gateway lifecycle: create T1-A and T1-B, attach segments, verify realization
...              and connectivity between VMs on different T1s.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      T1 Connectivity Suite Setup
Suite Teardown   T1 Connectivity Suite Teardown
Test Tags        t1    routing


*** Variables ***
${T1A_ID}           test-t1-a
${T1B_ID}           test-t1-b
${SEG_A_ID}         test-seg-a
${SEG_B_ID}         test-seg-b
${T1A_PATH}         /infra/tier-1s/${T1A_ID}
${T1B_PATH}         /infra/tier-1s/${T1B_ID}
# ${T0_PATH} and ${OVERLAY_TZ_PATH} are now defined once in resources/common.robot


*** Keywords ***
T1 Connectivity Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    T1-Gateway-A    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create T1 Gateway    ${T1B_ID}    T1-Gateway-B    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}
    Create Overlay Segment    ${SEG_B_ID}    ${T1B_PATH}    ${OVERLAY_TZ_PATH}    ${T1B_SEGMENT_CIDR}

T1 Connectivity Suite Teardown
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_B_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1B_ID}


*** Test Cases ***
Verify Gateways And Segments Are Realized
    [Documentation]    Poll the realization API for both T1 gateways and both segments.
    ...                One data-driven test replaces four near-identical realization cases.
    [Tags]    t1    realization
    [Template]    Wait For Realization
    /infra/tier-1s/${T1A_ID}
    /infra/tier-1s/${T1B_ID}
    /infra/segments/${SEG_A_ID}
    /infra/segments/${SEG_B_ID}

Verify T1-A Gateway Configuration
    [Documentation]    GET the T1-A gateway and assert it is linked to the T0.
    [Tags]    t1    config
    ${t1}=    Get T1 Gateway    ${T1A_ID}
    Should Be Equal As Strings    ${t1['tier0_path']}    ${T0_PATH}
    Log    T1-A linked to T0: ${t1['tier0_path']}

Verify T1-B Gateway Configuration
    [Documentation]    GET the T1-B gateway and assert it is linked to the T0.
    [Tags]    t1    config
    ${t1}=    Get T1 Gateway    ${T1B_ID}
    Should Be Equal As Strings    ${t1['tier0_path']}    ${T0_PATH}
    Log    T1-B linked to T0: ${t1['tier0_path']}

Verify Inter-T1 Connectivity
    [Documentation]    Correlate control plane and data plane: wait until both segments are
    ...                realized, then probe VM1 → VM2 (traffic traverses VM1 → T1-A → T0 → T1-B → VM2).
    [Tags]    t1    traffic
    Service Data Plane Should Be Reachable    ${VM1_IP}    icmp    ${VM2_IP}
    ...    /infra/segments/${SEG_A_ID}    /infra/segments/${SEG_B_ID}

Verify Inter-T1 Latency Within SLA
    [Documentation]    Beyond reachability, assert the VM1 → VM2 round-trip stays under the
    ...                ${PROBE_MAX_LATENCY}s budget, catching a slow/degraded overlay path.
    [Tags]    t1    traffic    latency
    Probe Latency Should Be Below    ${VM1_IP}    icmp    ${VM2_IP}    ${PROBE_MAX_LATENCY}

Verify Overlay MTU End To End
    [Documentation]    Prove the VM1 → VM2 overlay path carries a full 1500-byte inner frame
    ...                without fragmenting (DF-bit ping), validating the NSX TEP MTU headroom.
    [Tags]    t1    traffic    mtu
    Verify Overlay MTU From VM    ${VM1_IP}    ${VM2_IP}    ${OVERLAY_MTU_PAYLOAD}

Verify T1 To External Connectivity
    [Documentation]    SSH to VM1 and ping an IP outside NSX to verify T0 uplink routing.
    [Tags]    t1    traffic    external
    Ping From VM    ${VM1_IP}    ${EXTERNAL_TEST_IP}
