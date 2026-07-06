*** Settings ***
Documentation    Distributed Firewall (DFW) micro-segmentation end-to-end. Builds a two-T1
...              topology so VM1 and VM2 can reach each other, then:
...                1. defines an IP group (VM1) and an IP group (VM2), plus a dynamic tag group;
...                2. proves baseline VM1 → VM2 connectivity BEFORE any DFW rule;
...                3. applies a DROP rule (src=VM1 group, dst=VM2 group) and proves the data
...                   plane is now blocked (the deny-path assertions built into bbprobe);
...                4. removes the rule and proves connectivity is restored.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      DFW Suite Setup
Suite Teardown   DFW Suite Teardown
Test Tags        dfw    security


*** Variables ***
${T1A_ID}           test-t1-dfw-a
${T1B_ID}           test-t1-dfw-b
${SEG_A_ID}         test-seg-dfw-a
${SEG_B_ID}         test-seg-dfw-b
${T1A_PATH}         /infra/tier-1s/${T1A_ID}
${T1B_PATH}         /infra/tier-1s/${T1B_ID}

${SRC_GROUP_ID}     test-grp-dfw-src
${DST_GROUP_ID}     test-grp-dfw-dst
${TAG_GROUP_ID}     test-grp-dfw-tag
${SRC_GROUP_PATH}   /infra/domains/default/groups/${SRC_GROUP_ID}
${DST_GROUP_PATH}   /infra/domains/default/groups/${DST_GROUP_ID}

${DFW_POLICY_ID}    test-dfw-policy
${DFW_RULE_ID}      test-dfw-deny-1


*** Keywords ***
DFW Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    T1-DFW-A    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create T1 Gateway    ${T1B_ID}    T1-DFW-B    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}
    Create Overlay Segment    ${SEG_B_ID}    ${T1B_PATH}    ${OVERLAY_TZ_PATH}    ${T1B_SEGMENT_CIDR}

DFW Suite Teardown
    # Order matters: rule + policy first, then groups, then topology.
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/domains/default/security-policies/${DFW_POLICY_ID}
    ...    ${POLICY_BASE}${SRC_GROUP_PATH}
    ...    ${POLICY_BASE}${DST_GROUP_PATH}
    ...    ${POLICY_BASE}/infra/domains/default/groups/${TAG_GROUP_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_B_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1B_ID}

Verify Destination Group Has VM2
    [Documentation]    The IP group's effective membership must include VM2.
    ${members}=    Get Group Members    ${DST_GROUP_ID}
    Group Should Have Member    ${members}    ${VM2_IP}


*** Test Cases ***
Verify DFW Topology Is Realized
    [Documentation]    Wait for both T1 gateways and both segments to realize.
    [Tags]    dfw    realization
    [Template]    Wait For Realization
    /infra/tier-1s/${T1A_ID}
    /infra/tier-1s/${T1B_ID}
    /infra/segments/${SEG_A_ID}
    /infra/segments/${SEG_B_ID}

Create Source And Destination IP Groups
    [Documentation]    Create static IP groups for the VM1 (source) and VM2 (destination)
    ...                addresses — the match criteria for the DFW rule.
    [Tags]    dfw    groups    config
    Create IP Group    ${SRC_GROUP_ID}    ${{["$VM1_IP"]}}
    Create IP Group    ${DST_GROUP_ID}    ${{["$VM2_IP"]}}

Verify Groups Are Realized
    [Documentation]    Both groups must reach realized state before the rule references them.
    [Tags]    dfw    groups    realization
    [Template]    Wait For Realization
    ${SRC_GROUP_PATH}
    ${DST_GROUP_PATH}

Verify Destination Group Membership
    [Documentation]    Confirm the destination group's effective members include VM2
    ...                (effective membership can lag realization, so poll).
    [Tags]    dfw    groups
    Wait Until Keyword Succeeds    2 min    10 sec    Verify Destination Group Has VM2

Create Dynamic Tag Group
    [Documentation]    Demonstrate dynamic membership: tag segment-A and create a group whose
    ...                members are VMs carrying the ${DFW_TEST_TAG} tag. Verify the group is
    ...                realized with the expected Condition expression.
    [Tags]    dfw    groups    tags    config
    Set Tags On Segment    ${SEG_A_ID}    ${DFW_TEST_TAG}
    Create Tag Group    ${TAG_GROUP_ID}    ${DFW_TEST_TAG}
    Wait For Realization    /infra/domains/default/groups/${TAG_GROUP_ID}
    ${group}=    Get Group    ${TAG_GROUP_ID}
    ${value}=    Get Value    ${group}    expression.0.value
    Should Be Equal As Strings    ${value}    ${DFW_TEST_TAG}

Verify Baseline Connectivity Before DFW
    [Documentation]    Before any DFW rule, VM1 must be able to reach VM2.
    [Tags]    dfw    traffic    baseline
    Ping From VM    ${VM1_IP}    ${VM2_IP}

Create DFW Deny Policy And Rule
    [Documentation]    Create a security policy with a single DROP rule from the source group
    ...                to the destination group.
    [Tags]    dfw    config
    Create Security Policy    ${DFW_POLICY_ID}    sequence_number=10
    Create DFW Rule    ${DFW_POLICY_ID}    ${DFW_RULE_ID}
    ...    ${{["$SRC_GROUP_PATH"]}}    ${{["$DST_GROUP_PATH"]}}    action=DROP

Verify DFW Rule Configuration
    [Documentation]    GET the policy's rules and assert the deny rule exists with action DROP.
    [Tags]    dfw    config
    ${rules}=    Get DFW Rules    ${DFW_POLICY_ID}
    DFW Rule Should Have Action    ${rules}    ${DFW_RULE_ID}    DROP

Verify DFW Rule Is Realized
    [Documentation]    Poll realization for the security policy until SUCCESS.
    [Tags]    dfw    realization
    Wait For Realization    /infra/domains/default/security-policies/${DFW_POLICY_ID}

Verify Traffic Is Blocked By DFW
    [Documentation]    With the DROP rule enforced, VM1 → VM2 ICMP must now fail. Exercises the
    ...                bbprobe deny-path assertions (bounded so failure returns quickly).
    [Tags]    dfw    traffic    deny    end-to-end
    Wait Until Keyword Succeeds    2 min    15 sec    Ping Should Fail From VM    ${VM1_IP}    ${VM2_IP}

Restore Connectivity By Removing DFW Rule
    [Documentation]    Delete the deny rule and confirm VM1 → VM2 connectivity is restored,
    ...                proving the block was caused by the rule and not the topology.
    [Tags]    dfw    traffic    end-to-end
    Delete DFW Rule    ${DFW_POLICY_ID}    ${DFW_RULE_ID}
    Wait Until Keyword Succeeds    2 min    15 sec    Ping From VM    ${VM1_IP}    ${VM2_IP}
