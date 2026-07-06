*** Settings ***
Documentation    Example: validate an NSX network SERVICE (an L4 load balancer) end-to-end.
...              Builds a T1 gateway + segment, stands up an LB service/pool/virtual-server
...              with an active health monitor, confirms the pool member is healthy, then
...              proves the service actually works by sending real L4 traffic through the VIP.
...              Copy this file as a starting point for testing any NSX service (LB, NAT, ...).
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Resource         nsxt_robot/resources/traffic_keywords.robot
Suite Setup      LB Example Suite Setup
Suite Teardown   LB Example Suite Teardown
Test Tags        example    alb    load-balancer


*** Variables ***
${T1_ID}            example-t1-lb
${SEG_ID}           example-seg-lb
${LB_SERVICE_ID}    example-lb-service
${LB_POOL_ID}       example-lb-pool
${LB_VS_ID}         example-lb-vs
${LB_MONITOR_ID}    example-lb-monitor
${T1_PATH}          /infra/tier-1s/${T1_ID}
${LB_SERVICE_PATH}  /infra/lb-services/${LB_SERVICE_ID}
${LB_POOL_PATH}     /infra/lb-pools/${LB_POOL_ID}
${LB_MONITOR_PATH}  /infra/lb-monitor-profiles/${LB_MONITOR_ID}


*** Keywords ***
LB Example Suite Setup
    Initialize REST Session
    Create T1 Gateway    ${T1_ID}    Example-T1-LB    ${T0_PATH}    TIER1_CONNECTED    TIER1_STATIC_ROUTES
    Create Overlay Segment    ${SEG_ID}    ${T1_PATH}    ${OVERLAY_TZ_PATH}    ${T1A_SEGMENT_CIDR}
    Wait For Realizations    ${T1_PATH}    /infra/segments/${SEG_ID}

LB Example Suite Teardown
    # Children first: virtual server, then pool, then monitor and service, then the topology.
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/lb-virtual-servers/${LB_VS_ID}
    ...    ${POLICY_BASE}/infra/lb-pools/${LB_POOL_ID}
    ...    ${POLICY_BASE}/infra/lb-monitor-profiles/${LB_MONITOR_ID}
    ...    ${POLICY_BASE}/infra/lb-services/${LB_SERVICE_ID}
    ...    ${POLICY_BASE}/infra/segments/${SEG_ID}
    ...    ${POLICY_BASE}/infra/tier-1s/${T1_ID}

Verify Pool Member Is Healthy
    [Documentation]    Poll pool operational status until the member reports UP.
    ${status}=    Get LB Pool Status    ${LB_POOL_ID}    ${LB_SERVICE_ID}
    Pool Member Should Be Up    ${status}


*** Test Cases ***
Create LB Service, Monitor, And Pool
    [Documentation]    Attach an LB service to the T1, add an active HTTP health monitor
    ...                so members are only UP once they answer HTTP, then create a pool
    ...                with the example pool member bound to that monitor.
    [Tags]    config
    Create LB Service    ${LB_SERVICE_ID}    ${T1_PATH}    SMALL
    Create LB HTTP Monitor    ${LB_MONITOR_ID}    ${ALB_MONITOR_PORT}    ${ALB_MONITOR_URL}
    Create LB Pool    ${LB_POOL_ID}    ${ALB_POOL_MEMBERS}    ${ALB_POOL_PORT}    ${LB_MONITOR_PATH}
    Wait For Realizations    ${LB_SERVICE_PATH}    ${LB_POOL_PATH}

Create L4 Virtual Server On The VIP
    [Documentation]    Expose the pool on a VIP:port as a TCP virtual server, and wait for
    ...                it to realize.
    [Tags]    config
    Create LB Virtual Server    ${LB_VS_ID}    ${LB_POOL_PATH}    ${ALB_VIP}    ${ALB_VIP_PORT}    ${LB_SERVICE_PATH}
    Wait For Realization    /infra/lb-virtual-servers/${LB_VS_ID}

Verify Pool Member Health
    [Documentation]    The health monitor must mark the pool member UP before traffic
    ...                through the VIP can be expected to succeed.
    [Tags]    health
    Wait Until Keyword Succeeds    3 min    15 sec    Verify Pool Member Is Healthy

Verify L4 Traffic Through The VIP
    [Documentation]    From a test VM, send HTTP traffic to the LB VIP and assert a
    ...                successful 2xx response via bbprobe — the service actually works,
    ...                not just "realized" in NSX's control plane.
    [Tags]    traffic    end-to-end
    Probe Should Succeed    ${VM2_IP}    http_2xx    http://${ALB_VIP}:${ALB_VIP_PORT}
