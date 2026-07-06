*** Settings ***
Documentation    Fault-injection keywords for resilience testing: segment / T0-uplink /
...              BGP / edge-node failures, each paired with a restore keyword, plus
...              data-plane convergence assertions built on bbprobe. Edge-node SSH
...              actions (Restart Edge Dataplane, Reboot Edge Node) are destructive and
...              gated behind ${EDGE_PASSWORD} — skip a test with
...              `Skip If  '${EDGE_PASSWORD}' == '${EMPTY}'` when it is not set, and
...              exclude the whole category with `-e destructive` on fabrics you don't
...              want to reboot.
Library          Collections
Library          String
Library          SSHLibrary
Resource         common.robot
Resource         policy_api.robot
Resource         bbprobe_keywords.robot


*** Variables ***
${FAILOVER_MAX_RECOVERY}    120 sec
${EDGE_USER}                admin
${EDGE_PASSWORD}             ${EMPTY}
${EDGE_SSH_PORT}             22
${EDGE_SSH_TIMEOUT}          30s
${EDGE_SSH_PROMPT}           >


*** Keywords ***
# ──────────────────────────────────────────────
# Segment / T0 uplink failures
# ──────────────────────────────────────────────

Set Segment Admin State
    [Documentation]    Set a segment's admin_state to UP or DOWN. Used both for direct
    ...                segment failures and to represent a T0/T0-VRF uplink failure (a
    ...                Tier0Interface itself has no admin-state flag; its backing VLAN
    ...                segment is the reversible failure point).
    [Arguments]    ${segment_id}    ${state}
    ${body}=    Create Dictionary    admin_state=${state}
    NSX REST PATCH    ${INFRA_BASE}/segments/${segment_id}    ${body}
    Log    Segment ${segment_id} admin_state -> ${state}

Fail Segment
    [Documentation]    Simulate a segment (or T0/T0-VRF uplink) failure by setting
    ...                admin_state to DOWN.
    [Arguments]    ${segment_id}
    Set Segment Admin State    ${segment_id}    DOWN

Restore Segment
    [Documentation]    Undo Fail Segment: set admin_state back to UP.
    [Arguments]    ${segment_id}
    Set Segment Admin State    ${segment_id}    UP

# ──────────────────────────────────────────────
# BGP failures
# ──────────────────────────────────────────────

Disable BGP On T0 Locale Service
    [Documentation]    Simulate a BGP failure on a T0 or T0-VRF locale service by setting
    ...                enabled=false. Restore with Enable BGP On T0 Locale Service
    ...                (policy_api.robot) — for a standalone T0 that needs its ASN
    ...                re-asserted, use Configure BGP On T0 instead.
    [Arguments]    ${t0_id}    ${locale_service_id}=default
    ${body}=    Create Dictionary    enabled=${False}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}/bgp
    ...    ${body}
    Log    Disabled BGP on T0 ${t0_id}

# ──────────────────────────────────────────────
# Edge node failures (Management API — reversible)
# ──────────────────────────────────────────────

Get Transport Node
    [Documentation]    Retrieve a transport node (edge or host) by management-plane ID.
    [Arguments]    ${node_id}
    ${body}=    NSX REST GET    ${MGMT_BASE}/transport-nodes/${node_id}
    RETURN    ${body}

Get Edge Node Nsx Id From Cluster
    [Documentation]    Return the management-plane nsx_id of the ${index}'th edge node
    ...                (0-based) in a Policy edge cluster — the ID Enter/Exit Edge
    ...                Maintenance Mode and Get Transport Node need. The field mapping
    ...                Policy edge-node -> mgmt transport-node ID is release-sensitive;
    ...                if 'nsx_id' is absent on your NSX version, GET the same path
    ...                manually and adjust the Get Value path below.
    [Arguments]    ${edge_cluster_id}    ${index}=0
    ${nodes}=    Get Edge Nodes In Cluster    ${edge_cluster_id}
    ${nsx_id}=    Get Value    ${nodes}    results.${index}.nsx_id
    RETURN    ${nsx_id}

Enter Edge Maintenance Mode
    [Documentation]    Drain an edge transport node (graceful failover of its hosted
    ...                logical routers to the peer edge). Reversible with
    ...                Exit Edge Maintenance Mode.
    [Arguments]    ${node_id}
    NSX REST POST    ${MGMT_BASE}/transport-nodes/${node_id}?action=enter_maintenance_mode
    Log    Edge transport node ${node_id} entering maintenance mode

Exit Edge Maintenance Mode
    [Documentation]    Undo Enter Edge Maintenance Mode.
    [Arguments]    ${node_id}
    NSX REST POST    ${MGMT_BASE}/transport-nodes/${node_id}?action=exit_maintenance_mode
    Log    Edge transport node ${node_id} exiting maintenance mode

# ──────────────────────────────────────────────
# Edge node failures (SSH — destructive; gated on ${EDGE_PASSWORD})
# ──────────────────────────────────────────────

Open SSH To Edge
    [Documentation]    Open (or reuse) an SSH connection to an NSX edge node's management
    ...                CLI. Connections are aliased "edge-${edge_ip}" so they don't collide
    ...                with test-VM connections opened by Ensure SSH To VM. Credentials
    ...                come from ${EDGE_USER}/${EDGE_PASSWORD}; the password is never
    ...                logged.
    [Arguments]    ${edge_ip}
    ${alias}=    Set Variable    edge-${edge_ip}
    ${status}=    Run Keyword And Return Status    Switch Connection    ${alias}
    IF    ${status}
        RETURN
    END
    Open Connection    ${edge_ip}    alias=${alias}    port=${EDGE_SSH_PORT}
    ...    timeout=${EDGE_SSH_TIMEOUT}    prompt=${EDGE_SSH_PROMPT}
    ${previous_level}=    BuiltIn.Set Log Level    NONE
    Login    ${EDGE_USER}    ${EDGE_PASSWORD}
    BuiltIn.Set Log Level    ${previous_level}
    Log    SSH connected to edge ${edge_ip}:${EDGE_SSH_PORT}

Restart Edge Dataplane
    [Documentation]    DESTRUCTIVE: restart the dataplane service on an edge node over
    ...                SSH (NSX edge CLI). Causes a real, brief data-plane outage on that
    ...                edge — pair with Data Plane Should Recover Within. Requires
    ...                ${EDGE_PASSWORD} to be set; guard callers with
    ...                `Skip If  '${EDGE_PASSWORD}' == '${EMPTY}'`.
    [Arguments]    ${edge_ip}
    Open SSH To Edge    ${edge_ip}
    ${out}    ${rc}=    Execute Command    restart service dataplane    return_rc=True
    Log    Restarted dataplane on edge ${edge_ip} (rc=${rc}): ${out}

Reboot Edge Node
    [Documentation]    DESTRUCTIVE: reboot an edge node over SSH (NSX edge CLI). The SSH
    ...                connection drops by design; this does not wait for the node to come
    ...                back — pair with Data Plane Should Recover Within using a generous
    ...                timeout (edge reboot is minutes, not seconds). Requires
    ...                ${EDGE_PASSWORD}; guard callers with
    ...                `Skip If  '${EDGE_PASSWORD}' == '${EMPTY}'`.
    [Arguments]    ${edge_ip}
    Open SSH To Edge    ${edge_ip}
    Run Keyword And Ignore Error    Execute Command    reboot    timeout=5s
    Log    Reboot issued to edge ${edge_ip}

# ──────────────────────────────────────────────
# Convergence / observation
# ──────────────────────────────────────────────

Data Plane Should Recover Within
    [Documentation]    Assert a bbprobe check starts succeeding again within ${max_time}
    ...                after a failure was injected — the standard post-restore /
    ...                post-failover convergence assertion.
    [Arguments]    ${vm_ip}    ${module}    ${target}    ${max_time}=${FAILOVER_MAX_RECOVERY}
    Wait Until Keyword Succeeds    ${max_time}    5 sec    Probe Should Succeed    ${vm_ip}    ${module}    ${target}
    Log    Data plane recovered: ${module} -> ${target} within ${max_time}

Data Plane Should Be Down Within
    [Documentation]    Assert a bbprobe check starts failing within ${max_time} after a
    ...                failure was injected — confirms the injection actually took effect.
    [Arguments]    ${vm_ip}    ${module}    ${target}    ${max_time}=${FAILOVER_MAX_RECOVERY}
    Wait Until Keyword Succeeds    ${max_time}    5 sec    Probe Should Fail    ${vm_ip}    ${module}    ${target}
    Log    Data plane down as expected: ${module} -> ${target} within ${max_time}
