*** Settings ***
Documentation    Static routing on a T1 gateway: create route, verify in routing table,
...              verify reachability via the static route.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      Static Routing Suite Setup
Suite Teardown   Static Routing Suite Teardown
Test Tags        routing    static-route


*** Variables ***
${T1A_ID}               test-t1-static
${SEG_A_ID}             test-seg-static
${ROUTE_ID}             test-static-route-1
${T1A_PATH}             /infra/tier-1s/${T1A_ID}
# ${T0_PATH} and ${OVERLAY_TZ_PATH} come from resources/common.robot
${STATIC_ROUTE_NETWORK}    192.168.100.0/24
${STATIC_ROUTE_NEXTHOP}    172.16.1.1


*** Keywords ***
Static Routing Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    T1-Static-Routing    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}

Static Routing Suite Teardown
    Safe Delete Policy Object    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}/static-routes/${ROUTE_ID}
    Safe Delete Policy Object    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    Safe Delete Policy Object    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}


*** Test Cases ***
Verify T1 Gateway Is Realized
    [Documentation]    Wait until the T1 gateway reaches realized state SUCCESS.
    [Tags]    routing    realization
    Wait For Realization    /infra/tier-1s/${T1A_ID}

Create Static Route On T1 Gateway
    [Documentation]    Add a static route for ${STATIC_ROUTE_NETWORK} via ${STATIC_ROUTE_NEXTHOP}.
    [Tags]    routing    static-route
    Create Static Route On T1
    ...    ${T1A_ID}
    ...    ${ROUTE_ID}
    ...    ${STATIC_ROUTE_NETWORK}
    ...    ${STATIC_ROUTE_NEXTHOP}

Verify Static Route Is Present
    [Documentation]    GET static routes on T1 and assert the test route appears in the list.
    [Tags]    routing    static-route
    ${routes}=    Get Static Routes On T1    ${T1A_ID}
    ${route_list}=    Get From Dictionary    ${routes}    results
    ${route_networks}=    Evaluate    [r.get('network', '') for r in ${route_list}]
    Should Contain    ${route_networks}    ${STATIC_ROUTE_NETWORK}
    Log    Static route ${STATIC_ROUTE_NETWORK} found on T1 ${T1A_ID}

Verify Static Route Is Realized
    [Documentation]    Poll realization for the static route object.
    [Tags]    routing    static-route    realization
    Wait For Realization    /infra/tier-1s/${T1A_ID}/static-routes/${ROUTE_ID}

Verify Static Route Next Hop Is Correct
    [Documentation]    Assert the configured next hop IP matches the expected value
    ...                (Find In List + Get Value replace the manual dict walking).
    [Tags]    routing    static-route    config
    ${routes}=    Get Static Routes On T1    ${T1A_ID}
    ${test_route}=    Find In List    ${routes}    network    ${STATIC_ROUTE_NETWORK}
    ${hop_ip}=    Get Value    ${test_route}    next_hops.0.ip_address
    Should Be Equal As Strings    ${hop_ip}    ${STATIC_ROUTE_NEXTHOP}
    Log    Static route next-hop verified: ${hop_ip}

Verify Reachability Via Static Route
    [Documentation]    From VM1 on the T1 segment, ping the static route destination network prefix.
    [Tags]    routing    static-route    traffic
    ${dest_ip}=    Evaluate    '${STATIC_ROUTE_NETWORK}'.split('/')[0].rsplit('.', 1)[0] + '.1'
    Ping From VM    ${VM1_IP}    ${dest_ip}
