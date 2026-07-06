*** Settings ***
Documentation    NSX Load Balancer (L4/TCP) end-to-end: create LB service, pool, and virtual server
...              attached to a T1 gateway, verify realization and pool member health, then
...              validate L4 traffic through the VIP.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      ALB L4 Suite Setup
Suite Teardown   ALB L4 Suite Teardown
Test Tags        alb    load-balancer    l4


*** Variables ***
${T1A_ID}           test-t1-alb
${SEG_A_ID}         test-seg-alb
${LB_SERVICE_ID}    test-lb-service
${LB_POOL_ID}       test-lb-pool
${LB_VS_ID}         test-lb-vs
${LB_MONITOR_ID}    test-lb-monitor
${T1A_PATH}         /infra/tier-1s/${T1A_ID}
# ${T0_PATH} and ${OVERLAY_TZ_PATH} come from resources/common.robot
${LB_SERVICE_PATH}  /infra/lb-services/${LB_SERVICE_ID}
${LB_POOL_PATH}     /infra/lb-pools/${LB_POOL_ID}
${LB_MONITOR_PATH}  /infra/lb-monitor-profiles/${LB_MONITOR_ID}


*** Keywords ***
ALB L4 Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1A_ID}    T1-ALB    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_A_ID}    ${T1A_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}

ALB L4 Suite Teardown
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/lb-virtual-servers/${LB_VS_ID}
    ...    ${POLICY_BASE}/infra/lb-pools/${LB_POOL_ID}
    ...    ${POLICY_BASE}/infra/lb-monitor-profiles/${LB_MONITOR_ID}
    ...    ${POLICY_BASE}/infra/lb-services/${LB_SERVICE_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_A_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1A_ID}

Verify LB Service Realized
    [Documentation]    Check realization for the LB service.
    Verify Realized    /infra/lb-services/${LB_SERVICE_ID}

Verify LB Pool Realized
    [Documentation]    Check realization for the LB pool.
    Verify Realized    /infra/lb-pools/${LB_POOL_ID}

Verify LB VS Realized
    [Documentation]    Check realization for the LB virtual server.
    Verify Realized    /infra/lb-virtual-servers/${LB_VS_ID}

Verify Pool Member Is UP
    [Documentation]    Poll pool status until every member reports UP state.
    ${status}=    Get LB Pool Status    ${LB_POOL_ID}    ${LB_SERVICE_ID}
    Pool Member Should Be Up    ${status}


*** Test Cases ***
Verify T1 Gateway Is Realized
    [Documentation]    Wait until the T1 for ALB tests reaches realized state SUCCESS.
    [Tags]    alb    realization
    Wait For Realization    /infra/tier-1s/${T1A_ID}

Verify Segment Is Realized
    [Documentation]    Wait until the segment for ALB tests reaches realized state SUCCESS.
    [Tags]    alb    realization
    Wait For Realization    /infra/segments/${SEG_A_ID}

Create LB Service On T1
    [Documentation]    Create an NSX LB service attached to the T1 gateway (size: SMALL).
    [Tags]    alb    config
    Create LB Service    ${LB_SERVICE_ID}    ${T1A_PATH}    SMALL

Create LB Health Monitor
    [Documentation]    Create an active HTTP health monitor so pool members are only marked UP
    ...                when they actually answer HTTP on the monitor port.
    [Tags]    alb    config    monitor
    Create LB HTTP Monitor    ${LB_MONITOR_ID}    ${ALB_MONITOR_PORT}    ${ALB_MONITOR_URL}

Create LB Server Pool
    [Documentation]    Create an LB pool with the test VM as a member on the pool port,
    ...                bound to the active HTTP health monitor.
    [Tags]    alb    config
    Create LB Pool    ${LB_POOL_ID}    ${ALB_POOL_MEMBERS}    ${ALB_POOL_PORT}    ${LB_MONITOR_PATH}

Create L4 Virtual Server
    [Documentation]    Create a TCP L4 virtual server on the VIP with the pool and LB service.
    [Tags]    alb    config
    Create LB Virtual Server
    ...    ${LB_VS_ID}
    ...    ${LB_POOL_PATH}
    ...    ${ALB_VIP}
    ...    ${ALB_VIP_PORT}
    ...    ${LB_SERVICE_PATH}

Verify LB Service Is Realized
    [Documentation]    Poll realization until the LB service reaches SUCCESS.
    [Tags]    alb    realization
    Wait Until Keyword Succeeds    3 min    15 sec    Verify LB Service Realized

Verify LB Pool Is Realized
    [Documentation]    Poll realization until the LB pool reaches SUCCESS.
    [Tags]    alb    realization
    Wait Until Keyword Succeeds    3 min    15 sec    Verify LB Pool Realized

Verify LB Virtual Server Is Realized
    [Documentation]    Poll realization until the LB virtual server reaches SUCCESS.
    [Tags]    alb    realization
    Wait Until Keyword Succeeds    3 min    15 sec    Verify LB VS Realized

Verify Pool Member Is Healthy
    [Documentation]    Poll the LB pool operational status until the member reports UP.
    [Tags]    alb    health
    Wait Until Keyword Succeeds    3 min    15 sec    Verify Pool Member Is UP

Verify L4 Traffic Through VIP
    [Documentation]    From VM2, send HTTP traffic to the LB VIP and assert a successful
    ...                2xx response via bbprobe, confirming L4 load balancing is working.
    [Tags]    alb    traffic    end-to-end
    Probe Should Succeed    ${VM2_IP}    http_2xx    http://${ALB_VIP}:${ALB_VIP_PORT}
