*** Settings ***
Documentation    NSX Load Balancer L7 (HTTP) end-to-end: create an LB service, an active HTTP
...              health monitor, a monitored server pool, and an L7 HTTP virtual server (the LB
...              proxies HTTP rather than forwarding raw TCP). Verify realization and member
...              health, then validate an HTTP 2xx response through the L7 VIP.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      ALB L7 Suite Setup
Suite Teardown   ALB L7 Suite Teardown
Test Tags        alb    load-balancer    l7


*** Variables ***
${T1A_ID}           test-t1-albl7
${SEG_A_ID}         test-seg-albl7
${LB_SERVICE_ID}    test-lb7-service
${LB_POOL_ID}       test-lb7-pool
${LB_VS_ID}         test-lb7-vs
${LB_MONITOR_ID}    test-lb7-monitor
${T1A_PATH}         /infra/tier-1s/${T1A_ID}
${LB_SERVICE_PATH}  /infra/lb-services/${LB_SERVICE_ID}
${LB_POOL_PATH}     /infra/lb-pools/${LB_POOL_ID}
${LB_MONITOR_PATH}  /infra/lb-monitor-profiles/${LB_MONITOR_ID}


*** Keywords ***
ALB L7 Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    T1-ALB-L7    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}

ALB L7 Suite Teardown
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/lb-virtual-servers/${LB_VS_ID}
    ...    ${POLICY_BASE}/infra/lb-pools/${LB_POOL_ID}
    ...    ${POLICY_BASE}/infra/lb-monitor-profiles/${LB_MONITOR_ID}
    ...    ${POLICY_BASE}/infra/lb-services/${LB_SERVICE_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}

Verify LB Pool Member Is UP
    [Documentation]    Poll pool status until every member reports UP (driven by the HTTP monitor).
    ${status}=    Get LB Pool Status    ${LB_POOL_ID}    ${LB_SERVICE_ID}
    Pool Member Should Be Up    ${status}


*** Test Cases ***
Verify Topology Is Realized
    [Documentation]    Wait until the T1 and segment for the L7 LB tests reach SUCCESS.
    [Tags]    alb    realization
    [Template]    Wait For Realization
    /infra/tier-1s/${T1A_ID}
    /infra/segments/${SEG_A_ID}

Create LB Service On T1
    [Documentation]    Create an NSX LB service attached to the T1 gateway (size: SMALL).
    [Tags]    alb    config
    Create LB Service    ${LB_SERVICE_ID}    ${T1A_PATH}    SMALL

Create L7 HTTP Health Monitor
    [Documentation]    Create an active HTTP monitor that probes ${ALB_MONITOR_URL} on the
    ...                member port and treats 200 as healthy.
    [Tags]    alb    config    monitor
    Create LB HTTP Monitor    ${LB_MONITOR_ID}    ${ALB_MONITOR_PORT}    ${ALB_MONITOR_URL}

Create Monitored Server Pool
    [Documentation]    Create an LB pool bound to the HTTP monitor with the test VM as a member.
    [Tags]    alb    config
    Create LB Pool    ${LB_POOL_ID}    ${ALB_POOL_MEMBERS}    ${ALB_POOL_PORT}    ${LB_MONITOR_PATH}

Create L7 HTTP Virtual Server
    [Documentation]    Create an L7 HTTP virtual server on the L7 VIP using the default HTTP
    ...                application profile.
    [Tags]    alb    config
    Create LB HTTP Virtual Server
    ...    ${LB_VS_ID}
    ...    ${LB_POOL_PATH}
    ...    ${ALB_L7_VIP}
    ...    ${ALB_L7_VIP_PORT}
    ...    ${LB_SERVICE_PATH}

Verify L7 LB Objects Are Realized
    [Documentation]    Poll realization for the LB service, pool, and L7 virtual server.
    [Tags]    alb    realization
    Wait Until Keyword Succeeds    3 min    15 sec    Wait For Realization    /infra/lb-services/${LB_SERVICE_ID}
    Wait Until Keyword Succeeds    3 min    15 sec    Wait For Realization    /infra/lb-pools/${LB_POOL_ID}
    Wait Until Keyword Succeeds    3 min    15 sec    Wait For Realization    /infra/lb-virtual-servers/${LB_VS_ID}

Verify Pool Member Is Healthy
    [Documentation]    Poll the pool operational status until the member is UP per the monitor.
    [Tags]    alb    health
    Wait Until Keyword Succeeds    3 min    15 sec    Verify LB Pool Member Is UP

Verify L7 HTTP Traffic Through VIP
    [Documentation]    From VM2, send HTTP to the L7 VIP and assert a 2xx response via bbprobe,
    ...                confirming L7 HTTP load balancing works end to end.
    [Tags]    alb    traffic    end-to-end
    Probe Should Succeed    ${VM2_IP}    http_2xx    http://${ALB_L7_VIP}:${ALB_L7_VIP_PORT}
