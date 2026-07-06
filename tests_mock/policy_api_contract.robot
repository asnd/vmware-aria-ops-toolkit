*** Settings ***
Documentation    Contract tests for Policy API keyword wiring: verify that keywords in
...              policy_api.robot / common.robot / failure_keywords.robot build the
...              correct HTTP method, path, and JSON request body — without a live NSX
...              Manager. Runs against an in-process mock (mock_nsx_server.py) that
...              records every request and echoes PATCH bodies back on a matching GET,
...              catching body-shape regressions that a --dryrun (structure-only) run
...              cannot: e.g. a keyword silently sending the wrong field name, or an
...              optional argument leaking into the body when it shouldn't.
Library          Collections
Library          mock_nsx_server.py
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/failure_keywords.robot
Suite Setup      Contract Suite Setup
Suite Teardown   Stop Mock NSX Server
Test Setup       Reset Mock NSX Requests
Test Tags        contract


*** Variables ***
# The REST library import in common.robot resolves ${NSX_BASE_URL} at parse time —
# before any Suite Setup runs — so a fixed, known port is required here (Robot
# Framework ignores a later `Import Library REST ...` with different arguments for an
# already-imported library, so the mock's actual listening port must be decided before
# import time, not after). Change this if 28417 is ever in use in your environment.
${NSX_BASE_URL}    http://127.0.0.1:28417
${MOCK_PORT}       28417


*** Keywords ***
Contract Suite Setup
    [Documentation]    Start the mock listening on the exact port ${NSX_BASE_URL}
    ...                (resolved when the REST library was imported) points at.
    Start Mock NSX Server    port=${MOCK_PORT}
    Initialize REST Session

Last Request Should Be
    [Documentation]    Assert the most recent request the mock received matches
    ...                ${method}/${path}, and return its body for further assertions.
    [Arguments]    ${method}    ${path}
    ${req}=    Get Mock NSX Last Request
    Should Be Equal As Strings    ${req}[method]    ${method}
    Should Be Equal As Strings    ${req}[path]    ${path}
    RETURN    ${req}[body]


*** Test Cases ***
Create T1 Gateway Sends Expected Body
    [Documentation]    display_name/tier0_path/route_advertisement_types land correctly.
    Create T1 Gateway    test-t1    Test-T1    /infra/tier-0s/t0-gw    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    ${body}=    Last Request Should Be    PATCH    /policy/api/v1/infra/tier-1s/test-t1
    Should Be Equal As Strings    ${body}[display_name]    Test-T1
    Should Be Equal As Strings    ${body}[tier0_path]    /infra/tier-0s/t0-gw
    Should Be Equal As Strings    ${body}[route_advertisement_types][0]    TIER1_CONNECTED
    Should Be Equal As Strings    ${body}[route_advertisement_types][1]    TIER1_STATIC_ROUTES

Create T1 Gateway Defaults Route Advertisement When Omitted
    [Documentation]    No route_adv_types given -> defaults to a single-item
    ...                [TIER1_CONNECTED] list, not an empty one.
    Create T1 Gateway    test-t1    Test-T1    /infra/tier-0s/t0-gw
    ${body}=    Last Request Should Be    PATCH    /policy/api/v1/infra/tier-1s/test-t1
    Length Should Be    ${body}[route_advertisement_types]    1
    Should Be Equal As Strings    ${body}[route_advertisement_types][0]    TIER1_CONNECTED

Create Overlay Segment Sends Expected Subnet
    [Documentation]    connectivity_path and the nested subnets[0].gateway_address land correctly.
    Create Overlay Segment    test-seg    /infra/tier-1s/test-t1
    ...    /infra/sites/default/enforcement-points/default/transport-zones/tz1    172.16.1.1/24
    ${body}=    Last Request Should Be    PATCH    /policy/api/v1/infra/segments/test-seg
    Should Be Equal As Strings    ${body}[connectivity_path]    /infra/tier-1s/test-t1
    Should Be Equal As Strings    ${body}[subnets][0][gateway_address]    172.16.1.1/24

Create DFW Rule Defaults Action And Services
    [Documentation]    action defaults to ALLOW, services to [ANY], direction to IN_OUT.
    Create Security Policy    test-policy
    Create DFW Rule    test-policy    test-rule
    ...    ${{["/infra/domains/default/groups/src"]}}    ${{["/infra/domains/default/groups/dst"]}}
    ${body}=    Last Request Should Be    PATCH
    ...    /policy/api/v1/infra/domains/default/security-policies/test-policy/rules/test-rule
    Should Be Equal As Strings    ${body}[action]    ALLOW
    Should Be Equal As Strings    ${body}[services][0]    ANY
    Should Be Equal As Strings    ${body}[direction]    IN_OUT

Create Gateway Firewall Rule Sets Scope To Given Gateway
    [Documentation]    scope[0] carries the gateway path this rule is centralized on —
    ...                the field that distinguishes Gateway Firewall from DFW.
    Create Gateway Firewall Policy    test-gwfw-policy
    Create Gateway Firewall Rule    test-gwfw-policy    test-gwfw-rule    /infra/tier-1s/test-t1b
    ...    ${{["/infra/domains/default/groups/src"]}}    ${{["/infra/domains/default/groups/dst"]}}    action=DROP
    ${body}=    Last Request Should Be    PATCH
    ...    /policy/api/v1/infra/domains/default/gateway-policies/test-gwfw-policy/rules/test-gwfw-rule
    Should Be Equal As Strings    ${body}[action]    DROP
    Should Be Equal As Strings    ${body}[scope][0]    /infra/tier-1s/test-t1b

Create BGP Neighbor Sets Nested BFD Config
    [Documentation]    neighbor_address/remote_as_num plus the nested bfd_config dict
    ...                (enabled/interval) all land correctly.
    Create BGP Neighbor On T0    t0-gw    default    test-neighbor    192.168.1.1    65000
    ...    bfd_enabled=${True}    bfd_interval=500    bfd_multiplier=3
    ${body}=    Last Request Should Be    PATCH
    ...    /policy/api/v1/infra/tier-0s/t0-gw/locale-services/default/bgp/neighbors/test-neighbor
    Should Be Equal As Strings    ${body}[neighbor_address]    192.168.1.1
    Should Be Equal As Integers    ${body}[remote_as_num]    65000
    Should Be True    ${body}[bfd_config][enabled]
    Should Be Equal As Integers    ${body}[bfd_config][interval]    500

Create DNAT Rule Adds Translated Port Only When Given
    [Documentation]    translated_port, when passed, lands as translated_ports on the body.
    Create DNAT Rule On T1    test-t1    test-dnat    10.0.0.5    172.16.1.10    translated_port=8080
    ${body}=    Last Request Should Be    PATCH    /policy/api/v1/infra/tier-1s/test-t1/nat/USER/nat-rules/test-dnat
    Should Be Equal As Strings    ${body}[translated_ports]    8080

Create DNAT Rule Omits Translated Port When Not Given
    [Documentation]    The optional translated_ports field must NOT leak into the body
    ...                when translated_port wasn't passed.
    Create DNAT Rule On T1    test-t1    test-dnat2    10.0.0.6    172.16.1.11
    ${body}=    Last Request Should Be    PATCH    /policy/api/v1/infra/tier-1s/test-t1/nat/USER/nat-rules/test-dnat2
    Dictionary Should Not Contain Key    ${body}    translated_ports

Get T1 Gateway Returns What Was Patched
    [Documentation]    A GET after a PATCH round-trips the same object (validates the
    ...                mock and the GET wiring together).
    Create T1 Gateway    test-t1-roundtrip    RoundTrip    /infra/tier-0s/t0-gw
    ${gw}=    Get T1 Gateway    test-t1-roundtrip
    Should Be Equal As Strings    ${gw}[display_name]    RoundTrip

Delete T1 Gateway Sends DELETE To Expected Path
    [Documentation]    Delete T1 Gateway issues a DELETE to the gateway's own path.
    Create T1 Gateway    test-t1-del    ToDelete    /infra/tier-0s/t0-gw
    Delete T1 Gateway    test-t1-del
    ${req}=    Get Mock NSX Last Request
    Should Be Equal As Strings    ${req}[method]    DELETE
    Should Be Equal As Strings    ${req}[path]    /policy/api/v1/infra/tier-1s/test-t1-del

Wait For Realization Polls The Realized State Endpoint
    [Documentation]    Wait For Realization actually GETs realized-state/status, not
    ...                some other endpoint.
    Wait For Realization    /infra/tier-1s/test-t1
    ${req}=    Get Mock NSX Last Request
    Should Be Equal As Strings    ${req}[method]    GET
    Should Contain    ${req}[path]    /realized-state/status

Disable BGP On T0 Locale Service Sends Enabled False
    [Documentation]    The fault-injection keyword PATCHes enabled=false, not some
    ...                other truthy/falsy representation.
    Disable BGP On T0 Locale Service    t0-gw
    ${body}=    Last Request Should Be    PATCH    /policy/api/v1/infra/tier-0s/t0-gw/locale-services/default/bgp
    Should Be Equal    ${body}[enabled]    ${False}
