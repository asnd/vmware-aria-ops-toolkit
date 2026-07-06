*** Settings ***
Documentation    Example: Gateway Firewall (T1 edge/perimeter firewall) end-to-end. Distinct
...              from DFW (distributed, enforced at the vNIC): Gateway Firewall is
...              centralized and enforced at the T1's edge, so it filters traffic crossing
...              INTO that gateway — here, traffic arriving at T1B from T1A via the T0.
...              Builds a two-T1 topology so VM1 (behind T1A) and VM2 (behind T1B) can
...              reach each other, then:
...                1. proves baseline VM1 -> VM2 connectivity before any Gateway FW rule;
...                2. applies a DROP rule scoped to T1B (src=VM1 group, dst=VM2 group) and
...                   proves the data plane is now blocked;
...                3. removes the rule and proves connectivity is restored.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      Gateway FW Example Suite Setup
Suite Teardown   Gateway FW Example Suite Teardown
Test Tags        example    gateway-firewall    security


*** Variables ***
${T1A_ID}           example-t1-gwfw-a
${T1B_ID}           example-t1-gwfw-b
${SEG_A_ID}         example-seg-gwfw-a
${SEG_B_ID}         example-seg-gwfw-b
${T1A_PATH}         /infra/tier-1s/${T1A_ID}
${T1B_PATH}         /infra/tier-1s/${T1B_ID}

${SRC_GROUP_ID}     example-grp-gwfw-src
${DST_GROUP_ID}     example-grp-gwfw-dst
${SRC_GROUP_PATH}   /infra/domains/default/groups/${SRC_GROUP_ID}
${DST_GROUP_PATH}   /infra/domains/default/groups/${DST_GROUP_ID}

${GWFW_POLICY_ID}   example-gwfw-policy
${GWFW_RULE_ID}     example-gwfw-deny-1


*** Keywords ***
Gateway FW Example Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    Example-T1-GWFW-A    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create T1 Gateway    ${T1B_ID}    Example-T1-GWFW-B    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}
    Create Overlay Segment    ${SEG_B_ID}    ${T1B_PATH}    ${OVERLAY_TZ_PATH}    ${T1B_SEGMENT_CIDR}
    Create IP Group    ${SRC_GROUP_ID}    ${{["$VM1_IP"]}}
    Create IP Group    ${DST_GROUP_ID}    ${{["$VM2_IP"]}}
    Wait For Realizations
    ...    ${T1A_PATH}    ${T1B_PATH}
    ...    /infra/segments/${SEG_A_ID}    /infra/segments/${SEG_B_ID}
    ...    ${SRC_GROUP_PATH}    ${DST_GROUP_PATH}

Gateway FW Example Suite Teardown
    # Rule + policy first, then groups, then the topology.
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/domains/default/gateway-policies/${GWFW_POLICY_ID}
    ...    ${POLICY_BASE}${SRC_GROUP_PATH}
    ...    ${POLICY_BASE}${DST_GROUP_PATH}
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_B_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1B_ID}


*** Test Cases ***
Verify Baseline Connectivity Before Gateway Firewall
    [Documentation]    Before any Gateway Firewall rule, VM1 must be able to reach VM2.
    [Tags]    traffic    baseline
    Ping From VM    ${VM1_IP}    ${VM2_IP}

Create Gateway Firewall Deny Policy And Rule On T1B
    [Documentation]    Create a Gateway Firewall policy and a DROP rule scoped to T1B,
    ...                matching traffic from the VM1 group to the VM2 group — this filters
    ...                at T1B's edge, not per-vNIC like DFW would.
    [Tags]    config
    Create Gateway Firewall Policy    ${GWFW_POLICY_ID}    sequence_number=10
    Create Gateway Firewall Rule    ${GWFW_POLICY_ID}    ${GWFW_RULE_ID}    ${T1B_PATH}
    ...    ${{["$SRC_GROUP_PATH"]}}    ${{["$DST_GROUP_PATH"]}}    action=DROP

Verify Gateway Firewall Rule Configuration
    [Documentation]    GET the policy's rules and assert the deny rule exists with action DROP.
    [Tags]    config
    ${rules}=    Get Gateway Firewall Rules    ${GWFW_POLICY_ID}
    Gateway Firewall Rule Should Have Action    ${rules}    ${GWFW_RULE_ID}    DROP

Verify Gateway Firewall Rule Is Realized
    [Documentation]    Poll realization for the gateway policy until SUCCESS.
    [Tags]    realization
    Wait For Realization    /infra/domains/default/gateway-policies/${GWFW_POLICY_ID}

Verify Traffic Is Blocked By Gateway Firewall
    [Documentation]    With the DROP rule enforced at T1B's edge, VM1 -> VM2 ICMP must now
    ...                fail. Exercises the bbprobe deny-path assertions (bounded so failure
    ...                returns quickly).
    [Tags]    traffic    deny    end-to-end
    Wait Until Keyword Succeeds    2 min    15 sec    Ping Should Fail From VM    ${VM1_IP}    ${VM2_IP}

Restore Connectivity By Removing Gateway Firewall Rule
    [Documentation]    Delete the deny rule and confirm VM1 -> VM2 connectivity is restored,
    ...                proving the block was caused by the rule and not the topology.
    [Tags]    traffic    end-to-end
    Delete Gateway Firewall Rule    ${GWFW_POLICY_ID}    ${GWFW_RULE_ID}
    Wait Until Keyword Succeeds    2 min    15 sec    Ping From VM    ${VM1_IP}    ${VM2_IP}
