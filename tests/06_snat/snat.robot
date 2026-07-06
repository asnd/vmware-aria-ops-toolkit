*** Settings ***
Documentation    NAT end-to-end (SNAT + DNAT): create T1 and segment, configure an SNAT rule
...              (outbound source translation) and a DNAT rule (inbound destination translation),
...              verify rule config and realization, then confirm SNAT traffic exits using the
...              translated source IP.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      SNAT Suite Setup
Suite Teardown   SNAT Suite Teardown
Test Tags        nat


*** Variables ***
${T1A_ID}               test-t1-snat
${SEG_A_ID}             test-seg-snat
${SNAT_RULE_ID}         test-snat-rule-1
${DNAT_RULE_ID}         test-dnat-rule-1
${T1A_PATH}             /infra/tier-1s/${T1A_ID}
# ${T0_PATH} and ${OVERLAY_TZ_PATH} come from resources/common.robot
${SOURCE_NETWORK}       172.16.1.0/24


*** Keywords ***
SNAT Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    T1-SNAT    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES    TIER1_NAT
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}

SNAT Suite Teardown
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}/nat/USER/nat-rules/${SNAT_RULE_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}/nat/USER/nat-rules/${DNAT_RULE_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}

Verify SNAT Realized
    [Documentation]    Check realization for the SNAT NAT rule.
    Verify Realized    /infra/tier-1s/${T1A_ID}/nat/USER/nat-rules/${SNAT_RULE_ID}

Verify DNAT Realized
    [Documentation]    Check realization for the DNAT NAT rule.
    Verify Realized    /infra/tier-1s/${T1A_ID}/nat/USER/nat-rules/${DNAT_RULE_ID}


*** Test Cases ***
Verify T1 Gateway Is Realized
    [Documentation]    Wait until the T1 for SNAT tests reaches realized state SUCCESS.
    [Tags]    nat    realization
    Wait For Realization    /infra/tier-1s/${T1A_ID}

Verify Segment Is Realized
    [Documentation]    Wait until the segment for SNAT tests reaches realized state SUCCESS.
    [Tags]    nat    realization
    Wait For Realization    /infra/segments/${SEG_A_ID}

Create SNAT Rule On T1
    [Documentation]    Create an SNAT rule translating traffic from ${SOURCE_NETWORK} to ${SNAT_TRANSLATED_IP}.
    [Tags]    nat    snat    config
    Create SNAT Rule On T1
    ...    ${T1A_ID}
    ...    ${SNAT_RULE_ID}
    ...    ${SNAT_TRANSLATED_IP}
    ...    ${SOURCE_NETWORK}

Verify SNAT Rule Exists
    [Documentation]    GET NAT rules on T1 and assert the SNAT rule is present with correct
    ...                action and translated IP (single typed assertion via NsxtApi).
    [Tags]    nat    snat    config
    ${rules}=    Get NAT Rules On T1    ${T1A_ID}
    NAT Rule Should Exist    ${rules}    ${SNAT_RULE_ID}    action=SNAT    translated=${SNAT_TRANSLATED_IP}
    Log    SNAT rule verified: ${SOURCE_NETWORK} → ${SNAT_TRANSLATED_IP}

Verify SNAT Rule Is Realized
    [Documentation]    Poll realization state for the SNAT rule until SUCCESS.
    [Tags]    nat    snat    realization
    Wait Until Keyword Succeeds    2 min    10 sec    Verify SNAT Realized

Verify Traffic Uses Translated Source IP
    [Documentation]    From VM1, make an HTTP request to an external reflector service and verify
    ...                the response contains the SNAT translated IP as the client address.
    ...                Requires an HTTP reflector (e.g., httpbin /ip) running at EXTERNAL_TEST_IP.
    [Tags]    nat    snat    traffic    end-to-end
    Verify Source IP From VM
    ...    ${VM1_IP}
    ...    ${EXTERNAL_TEST_IP}
    ...    ${SNAT_TRANSLATED_IP}

Create DNAT Rule On T1
    [Documentation]    Create a DNAT rule mapping inbound traffic for ${DNAT_DESTINATION_IP}
    ...                to the internal server ${DNAT_TRANSLATED_IP}.
    [Tags]    nat    dnat    config
    Create DNAT Rule On T1
    ...    ${T1A_ID}
    ...    ${DNAT_RULE_ID}
    ...    ${DNAT_DESTINATION_IP}
    ...    ${DNAT_TRANSLATED_IP}

Verify DNAT Rule Exists
    [Documentation]    GET NAT rules on T1 and assert the DNAT rule is present with the correct
    ...                action and translated (internal) IP.
    [Tags]    nat    dnat    config
    ${rules}=    Get NAT Rules On T1    ${T1A_ID}
    NAT Rule Should Exist    ${rules}    ${DNAT_RULE_ID}    action=DNAT    translated=${DNAT_TRANSLATED_IP}
    Log    DNAT rule verified: ${DNAT_DESTINATION_IP} → ${DNAT_TRANSLATED_IP}

Verify DNAT Rule Is Realized
    [Documentation]    Poll realization state for the DNAT rule until SUCCESS.
    [Tags]    nat    dnat    realization
    Wait Until Keyword Succeeds    2 min    10 sec    Verify DNAT Realized
