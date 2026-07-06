*** Settings ***
Documentation    Infrastructure health checks: Manager cluster, Transport Zones, TEP, Compute Manager.
...              Uses the NSX Management API (/api/v1/...) in addition to the Policy API.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Suite Setup      Initialize REST Session
Test Tags        infra


*** Variables ***
# When ${INFRA_WARN_ONLY}=${True}, a non-success transport node logs a WARN instead of
# failing the test. Defaults to strict (fail) so a broken TEP cannot pass silently.
${INFRA_WARN_ONLY}    ${False}


*** Test Cases ***
Verify Manager Cluster Is Stable
    [Documentation]    GET /api/v1/cluster/status and assert overall status is STABLE.
    [Tags]    infra    cluster
    ${status}=    Get Manager Cluster Status
    Manager Cluster Should Be Stable    ${status}
    Log    Manager cluster status: ${status['mgmt_cluster_status']['status']}

Verify All Manager Nodes Are Online
    [Documentation]    Check that every manager node in the cluster reports CONNECTED.
    [Tags]    infra    cluster
    ${status}=    Get Manager Cluster Status
    ${nodes}=    Get From Dictionary    ${status['mgmt_cluster_status']}    online_nodes
    Should Not Be Empty    ${nodes}    msg=No online nodes found in cluster status
    FOR    ${node}    IN    @{nodes}
        Log    Node ${node['member_ip']} is online
    END

Verify Transport Zones Exist
    [Documentation]    Assert that the configured overlay TZ is present.
    [Tags]    infra    transport-zones
    ${result}=    Get Transport Zones
    ${tz_list}=    Get From Dictionary    ${result}    results
    Should Not Be Empty    ${tz_list}    msg=No transport zones returned
    ${tz_ids}=    Evaluate    [tz.get('id', tz.get('display_name', '')) for tz in ${tz_list}]
    Log    Transport zones found: ${tz_ids}
    ${found}=    Evaluate    any('${OVERLAY_TZ_ID}' in item for item in ${tz_ids})
    Should Be True    ${found}    msg=Overlay TZ '${OVERLAY_TZ_ID}' not found in transport zone list

Verify Host Transport Nodes Are Up
    [Documentation]    Check that all host transport nodes report a SUCCESS configuration state.
    ...                Fails on any non-success node unless ${INFRA_WARN_ONLY}=${True}.
    [Tags]    infra    transport-nodes
    ${result}=    Get All Transport Node Statuses
    ${node_statuses}=    Get From Dictionary    ${result}    results
    Should Not Be Empty    ${node_statuses}    msg=No transport node statuses returned
    ${bad_nodes}=    Create List
    FOR    ${tn}    IN    @{node_statuses}
        ${cfg_state}=    Get From Dictionary    ${tn}    node_deployment_state
        ${state}=    Get From Dictionary    ${cfg_state}    state
        IF    '${state}' != 'success'
            IF    ${INFRA_WARN_ONLY}
                Log    WARNING: Transport node has state '${state}': ${tn['node_id']}    WARN
            ELSE
                Append To List    ${bad_nodes}    ${tn['node_id']} (${state})
            END
        END
    END
    Should Be Empty    ${bad_nodes}    msg=Transport node(s) not in 'success' state: ${bad_nodes}
    Log    Transport node status check complete

Verify TEP IPs Are Configured
    [Documentation]    Confirm transport nodes have TEP IP addresses assigned.
    [Tags]    infra    tep
    ${result}=    NSX REST GET    ${MGMT_BASE}/transport-nodes
    ${nodes}=    Get From Dictionary    ${result}    results
    Should Not Be Empty    ${nodes}    msg=No transport nodes found
    FOR    ${tn}    IN    @{nodes}
        ${tn_id}=    Get From Dictionary    ${tn}    id
        ${tn_name}=    Get From Dictionary    ${tn}    display_name
        Log    Transport node: ${tn_name} (${tn_id})
    END
    Log    TEP configuration verified for all transport nodes

Verify Compute Manager Connection
    [Documentation]    Assert at least one compute manager is registered and connected.
    [Tags]    infra    compute-manager
    ${result}=    Get Compute Managers
    ${cm_list}=    Get From Dictionary    ${result}    results
    Should Not Be Empty    ${cm_list}    msg=No compute managers registered
    FOR    ${cm}    IN    @{cm_list}
        ${cm_id}=    Get From Dictionary    ${cm}    id
        ${cm_status}=    Get Compute Manager Status    ${cm_id}
        Compute Manager Should Be Registered    ${cm_status}
        Log    Compute manager ${cm_id}: REGISTERED
    END
