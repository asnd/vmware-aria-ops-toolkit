*** Settings ***
Documentation    HA VIP configuration on T0 gateway locale service: create, verify config,
...              verify realization. No failover testing (config-only validation).
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Suite Setup      HA VIP Suite Setup
Suite Teardown   HA VIP Suite Teardown
Test Tags        ha-vip    t0


*** Variables ***
${LOCALE_SERVICE_ID}    default


*** Keywords ***
HA VIP Suite Setup
    Initialize REST Session

HA VIP Suite Teardown
    Remove HA VIP Config On T0    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}

Verify HA VIP Realized
    [Documentation]    Check that the T0 locale service is in a realized state.
    ${body}=    Get T0 Locale Service    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}
    ${ls_path}=    Get From Dictionary    ${body}    path
    Verify Realized    ${ls_path}


*** Test Cases ***
Retrieve T0 Locale Service
    [Documentation]    GET the T0 locale service to confirm it exists and retrieve edge paths.
    [Tags]    ha-vip    prereq
    ${body}=    Get T0 Locale Service    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}
    Log    Locale service: ${body['id']} | Edge cluster: ${body.get('edge_cluster_path', 'N/A')}
    Set Suite Variable    ${LOCALE_SERVICE_BODY}    ${body}

Create HA VIP On T0 Locale Service
    [Documentation]    Configure an HA VIP IP on the T0 locale service using existing edge paths.
    [Tags]    ha-vip    config
    # Retrieve the first two interface paths from the locale service for HA VIP binding
    ${body}=    NSX REST GET
    ...    ${POLICY_BASE}/infra/tier-0s/${T0_GATEWAY_ID}/locale-services/${LOCALE_SERVICE_ID}/interfaces
    ${interfaces}=    Get From Dictionary    ${body}    results
    Should Be True    len(${interfaces}) >= 2    msg=Need at least 2 interfaces for HA VIP
    ${path1}=    Get From Dictionary    ${interfaces[0]}    path
    ${path2}=    Get From Dictionary    ${interfaces[1]}    path
    Create HA VIP Config On T0    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}    ${HA_VIP_IP}    ${path1}    ${path2}

Verify HA VIP Configuration
    [Documentation]    GET the locale service and assert ha_vip_configs contains the configured VIP.
    [Tags]    ha-vip    config
    ${body}=    Get T0 Locale Service    ${T0_GATEWAY_ID}    ${LOCALE_SERVICE_ID}
    ${vip_configs}=    Get From Dictionary    ${body}    ha_vip_configs
    Should Not Be Empty    ${vip_configs}    msg=No HA VIP configs found on locale service
    ${vip_ip}=    Evaluate    '${HA_VIP_IP}'.split('/')[0]
    ${all_vip_ips}=    Evaluate
    ...    [ip for cfg in ${vip_configs} for subnet in cfg.get('vip_subnets', []) for ip in subnet.get('ip_addresses', [])]
    Should Contain    ${all_vip_ips}    ${vip_ip}
    Log    HA VIP ${vip_ip} confirmed in locale service config

Verify HA VIP Is Realized
    [Documentation]    Poll realization state for the T0 locale service after HA VIP config.
    [Tags]    ha-vip    realization
    Wait Until Keyword Succeeds    2 min    10 sec    Verify HA VIP Realized
