*** Settings ***
Documentation    BGP and BFD on the T0 gateway: configure BGP, add a neighbor with BFD,
...              verify session establishment and learned routes.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Suite Setup      BGP BFD Suite Setup
Suite Teardown   BGP BFD Suite Teardown
Test Tags        bgp    bfd    routing


*** Variables ***
${NEIGHBOR_ID}          test-bgp-neighbor-1
${LOCALE_SERVICE_ID}    default


*** Keywords ***
BGP BFD Suite Setup
    Initialize REST Session

BGP BFD Suite Teardown
    Safe Delete Policy Object
    ...    ${POLICY_BASE}/infra/tier-0s/${T0_GATEWAY_ID}/locale-services/${LOCALE_SERVICE_ID}/bgp/neighbors/${NEIGHBOR_ID}

Verify BGP Session State
    [Documentation]    Poll BGP neighbor status and assert it is ESTABLISHED.
    ${status}=    Get BGP Neighbor Status    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}    ${NEIGHBOR_ID}
    BGP Neighbor Should Be Established    ${status}

Verify BFD Session State
    [Documentation]    Poll BFD status embedded in BGP neighbor status (diagnostic code 0 = healthy).
    ${status}=    Get BGP Neighbor Status    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}    ${NEIGHBOR_ID}
    BFD Should Be Healthy    ${status}


*** Test Cases ***
Configure BGP On T0 Gateway
    [Documentation]    Enable BGP on the T0 gateway and set the local ASN.
    [Tags]    bgp    config
    Configure BGP On T0    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}    ${BGP_LOCAL_ASN}

Create BGP Neighbor With BFD
    [Documentation]    Add a BGP neighbor entry with BFD enabled.
    [Tags]    bgp    bfd    config
    Create BGP Neighbor On T0
    ...    ${T0_GATEWAY_ID}
    ...    ${LOCALE_SERVICE_ID}
    ...    ${NEIGHBOR_ID}
    ...    ${BGP_PEER_IP}
    ...    ${BGP_PEER_ASN}
    ...    bfd_enabled=${True}
    ...    bfd_interval=${BFD_INTERVAL}
    ...    bfd_multiplier=${BFD_MULTIPLIER}

Verify BGP Session Is Established
    [Documentation]    Poll BGP neighbor operational status until ESTABLISHED (up to 3 minutes).
    [Tags]    bgp    session
    Wait Until Keyword Succeeds    3 min    15 sec    Verify BGP Session State

Verify BFD Session Is Up
    [Documentation]    Assert BFD session for the BGP neighbor shows no diagnostic (healthy).
    [Tags]    bgp    bfd    session
    Wait Until Keyword Succeeds    2 min    10 sec    Verify BFD Session State

Verify BGP Routes Received From Peer
    [Documentation]    Assert at least one BGP route has been learned from the peer.
    [Tags]    bgp    routes
    ${routes}=    Get BGP Routes On T0    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}    ${NEIGHBOR_ID}
    ${route_entries}=    Get From Dictionary    ${routes}    results
    Should Not Be Empty    ${route_entries}    msg=No BGP routes learned from peer ${BGP_PEER_IP}
    Log    BGP routes received: ${route_entries.__len__()} prefix(es)

Verify BGP Neighbor Configuration
    [Documentation]    GET the BGP neighbor config and assert key parameters are correct.
    [Tags]    bgp    config
    ${body}=    NSX REST GET
    ...    ${POLICY_BASE}/infra/tier-0s/${T0_GATEWAY_ID}/locale-services/${LOCALE_SERVICE_ID}/bgp/neighbors/${NEIGHBOR_ID}
    Should Be Equal As Strings    ${body['neighbor_address']}    ${BGP_PEER_IP}
    Should Be Equal As Strings    ${body['remote_as_num']}    ${BGP_PEER_ASN}
    ${bfd}=    Get From Dictionary    ${body}    bfd_config
    Should Be True    ${bfd['enabled']}
    Log    BGP neighbor config verified: peer ${BGP_PEER_IP} ASN ${BGP_PEER_ASN}
