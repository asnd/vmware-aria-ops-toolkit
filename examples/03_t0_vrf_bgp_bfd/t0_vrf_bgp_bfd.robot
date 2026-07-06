*** Settings ***
Documentation    Example: BGP + BFD peering on a Tier-0 VRF gateway. A VRF is itself a
...              tier-0 object, so the same "... On T0" BGP/BFD keywords used against a
...              standalone T0 work unchanged against a VRF's ID — only the ASN handling
...              differs (a VRF inherits its ASN from the parent T0). Builds a VRF linked
...              to the parent T0 with an external uplink, enables BGP, adds a
...              BFD-protected neighbor, and verifies both sessions come up.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Suite Setup      VRF BGP Example Suite Setup
Suite Teardown   VRF BGP Example Suite Teardown
Test Tags        example    vrf    bgp    bfd


*** Variables ***
${VRF_ID}                example-vrf-bgp
${VRF_LS_ID}             default
${VRF_PATH}              /infra/tier-0s/${VRF_ID}
${VRF_UPLINK_SEG_ID}     example-seg-vrf-bgp-uplink
${VRF_UPLINK_IF_ID}      example-if-vrf-bgp-uplink
${VRF_BFD_PROFILE_ID}    example-bfd-profile-vrf-bgp
${VRF_BFD_PEER_ID}       example-bfd-peer-vrf-bgp-1
${VRF_NEIGHBOR_ID}       example-bgp-vrf-bgp-neighbor-1
${VLAN_TZ_PATH}          /infra/sites/default/enforcement-points/default/transport-zones/${VLAN_TZ_ID}


*** Keywords ***
VRF BGP Example Suite Setup
    Initialize REST Session
    Create VLAN Segment    ${VRF_UPLINK_SEG_ID}    ${VLAN_TZ_PATH}    ${VRF_UPLINK_VLAN}
    Create VRF Gateway On T0    ${VRF_ID}    Example-VRF-BGP    ${T0_PATH}
    ${parent_ls}=    Get T0 Locale Service    ${T0_GATEWAY_ID}    ${VRF_PARENT_LS_ID}
    ${ec_path}=    Get Value    ${parent_ls}    edge_cluster_path
    Create T0 Locale Service    ${VRF_ID}    ${VRF_LS_ID}    ${ec_path}
    ${nodes}=    Get Edge Nodes In Cluster    ${EDGE_CLUSTER_ID}
    ${edge_path}=    Get Value    ${nodes}    results.0.path
    Create T0 External Interface    ${VRF_ID}    ${VRF_LS_ID}    ${VRF_UPLINK_IF_ID}
    ...    /infra/segments/${VRF_UPLINK_SEG_ID}    ${VRF_UPLINK_IP}    ${VRF_UPLINK_PREFIX}
    ...    edge_path=${edge_path}
    Wait For Realizations    ${VRF_PATH}    /infra/segments/${VRF_UPLINK_SEG_ID}

VRF BGP Example Suite Teardown
    # Children first: BGP neighbor and BFD peer, then the interface and locale service,
    # then the VRF itself, and finally the shared uplink segment and BFD profile.
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/locale-services/${VRF_LS_ID}/bgp/neighbors/${VRF_NEIGHBOR_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/static-routes/bfd-peers/${VRF_BFD_PEER_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/locale-services/${VRF_LS_ID}/interfaces/${VRF_UPLINK_IF_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/locale-services/${VRF_LS_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}
    ...    ${POLICY_BASE}/infra/segments/${VRF_UPLINK_SEG_ID}
    ...    ${POLICY_BASE}/infra/bfd-profiles/${VRF_BFD_PROFILE_ID}

Verify BGP Session State
    [Documentation]    Poll BGP neighbor status and assert it is ESTABLISHED.
    ${status}=    Get BGP Neighbor Status    ${VRF_ID}    ${VRF_LS_ID}    ${VRF_NEIGHBOR_ID}
    BGP Neighbor Should Be Established    ${status}

Verify BFD Session State
    [Documentation]    Poll BFD status embedded in the BGP neighbor status (diagnostic code
    ...                0 = healthy).
    ${status}=    Get BGP Neighbor Status    ${VRF_ID}    ${VRF_LS_ID}    ${VRF_NEIGHBOR_ID}
    BFD Should Be Healthy    ${status}


*** Test Cases ***
Enable BGP On The VRF
    [Documentation]    Enable BGP on the VRF's locale service. Unlike a standalone T0, the
    ...                local ASN is inherited from the parent T0 — do not set it here.
    [Tags]    config
    Enable BGP On T0 Locale Service    ${VRF_ID}    ${VRF_LS_ID}

Protect The BGP Peer With A BFD-Enabled Neighbor
    [Documentation]    Create a BFD profile, then a BGP neighbor with BFD enabled so the
    ...                session fails fast on a peer/link outage instead of waiting for the
    ...                BGP hold timer.
    [Tags]    config
    Create BFD Profile    ${VRF_BFD_PROFILE_ID}    ${BFD_INTERVAL}    ${BFD_MULTIPLIER}
    Create BGP Neighbor On T0    ${VRF_ID}    ${VRF_LS_ID}    ${VRF_NEIGHBOR_ID}
    ...    ${VRF_BGP_PEER_IP}    ${VRF_BGP_PEER_ASN}
    ...    bfd_enabled=${True}    bfd_interval=${BFD_INTERVAL}    bfd_multiplier=${BFD_MULTIPLIER}

Verify VRF Routing Objects Are Realized
    [Documentation]    The VRF with its BGP neighbor must consolidate to realized SUCCESS.
    [Tags]    realization
    Wait For Realization    ${VRF_PATH}

Verify BGP Session Is Established
    [Documentation]    Poll BGP neighbor operational status until ESTABLISHED.
    [Tags]    bgp    session
    Wait Until Keyword Succeeds    3 min    15 sec    Verify BGP Session State

Verify BFD Session Is Healthy
    [Documentation]    Assert the BFD session protecting the BGP peer reports no diagnostic.
    [Tags]    bfd    session
    Wait Until Keyword Succeeds    2 min    10 sec    Verify BFD Session State
