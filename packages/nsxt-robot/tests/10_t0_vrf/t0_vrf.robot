*** Settings ***
Documentation    Tier-0 VRF gateway end-to-end: create a VRF linked to the parent T0, give
...              it a locale service and an external (uplink) interface on a VLAN segment,
...              then exercise VRF-level static routing (with a BFD-protected next hop)
...              and BGP. The `evpn`-tagged tests additionally enable EVPN INLINE mode on
...              the PARENT T0 (a shared object — the mode persists after teardown) and
...              attach RD / route-targets / a transit VNI to the VRF; exclude them with
...              `-e evpn` on fabrics without EVPN support.
Resource         nsxt_robot/resources/common.robot
Resource         nsxt_robot/resources/policy_api.robot
Suite Setup      VRF Suite Setup
Suite Teardown   VRF Suite Teardown
Test Tags        vrf


*** Variables ***
${VRF_ID}                test-vrf-red
${VRF_LS_ID}             default
${VRF_PATH}              /infra/tier-0s/${VRF_ID}
${VRF_UPLINK_SEG_ID}     test-seg-vrf-uplink
${VRF_UPLINK_IF_ID}      test-if-vrf-uplink
${VRF_ROUTE_ID}          test-route-vrf-1
${VRF_BFD_PROFILE_ID}    test-bfd-profile-vrf
${VRF_BFD_PEER_ID}       test-bfd-peer-vrf-1
${VRF_NEIGHBOR_ID}       test-bgp-vrf-neighbor-1
${EVPN_VNI_POOL_ID}      test-vni-pool-evpn
${VLAN_TZ_PATH}          /infra/sites/default/enforcement-points/default/transport-zones/${VLAN_TZ_ID}


*** Keywords ***
VRF Suite Setup
    Initialize REST Session
    Create VLAN Segment    ${VRF_UPLINK_SEG_ID}    ${VLAN_TZ_PATH}    ${VRF_UPLINK_VLAN}

VRF Suite Teardown
    # Children first: routing/BGP objects on the VRF, then the interface and locale
    # service, then the VRF itself, and finally the shared objects it referenced.
    Standard Suite Teardown
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/locale-services/${VRF_LS_ID}/bgp/neighbors/${VRF_NEIGHBOR_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/static-routes/bfd-peers/${VRF_BFD_PEER_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/static-routes/${VRF_ROUTE_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/locale-services/${VRF_LS_ID}/interfaces/${VRF_UPLINK_IF_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}/locale-services/${VRF_LS_ID}
    ...    ${POLICY_BASE}/infra/tier-0s/${VRF_ID}
    ...    ${POLICY_BASE}/infra/segments/${VRF_UPLINK_SEG_ID}
    ...    ${POLICY_BASE}/infra/bfd-profiles/${VRF_BFD_PROFILE_ID}
    ...    ${POLICY_BASE}/infra/vni-pools/${EVPN_VNI_POOL_ID}

Get First Edge Node Path
    [Documentation]    Return the Policy path of the first edge node in ${EDGE_CLUSTER_ID},
    ...                for pinning external interfaces.
    ${nodes}=    Get Edge Nodes In Cluster    ${EDGE_CLUSTER_ID}
    ${edge_path}=    Get Value    ${nodes}    results.0.path
    RETURN    ${edge_path}


*** Test Cases ***
Create VRF Gateway Linked To Parent T0
    [Documentation]    Create a plain (VRF-lite) VRF gateway on the parent T0 and assert
    ...                the returned body carries a vrf_config linked to the parent.
    [Tags]    vrf    config
    Create VRF Gateway On T0    ${VRF_ID}    VRF-Red    ${T0_PATH}
    ${vrf}=    Get T0 Gateway    ${VRF_ID}
    Vrf Should Be Linked To Parent    ${vrf}    ${T0_PATH}

Verify VRF Gateway Is Realized
    [Documentation]    Poll realization for the VRF gateway until SUCCESS.
    [Tags]    vrf    realization
    Wait For Realization    ${VRF_PATH}

Create Locale Service On VRF
    [Documentation]    Create the VRF's locale service, inheriting the edge cluster from
    ...                the parent T0's locale service.
    [Tags]    vrf    config
    ${parent_ls}=    Get T0 Locale Service    ${T0_GATEWAY_ID}    ${VRF_PARENT_LS_ID}
    ${ec_path}=    Get Value    ${parent_ls}    edge_cluster_path
    Create T0 Locale Service    ${VRF_ID}    ${VRF_LS_ID}    ${ec_path}

Create External Uplink Interface On VRF
    [Documentation]    Attach an EXTERNAL interface to the VRF on the VLAN uplink segment,
    ...                pinned to the first edge node of the edge cluster, and wait for it
    ...                to realize.
    [Tags]    vrf    interfaces    config
    ${edge_path}=    Get First Edge Node Path
    Create T0 External Interface    ${VRF_ID}    ${VRF_LS_ID}    ${VRF_UPLINK_IF_ID}
    ...    /infra/segments/${VRF_UPLINK_SEG_ID}    ${VRF_UPLINK_IP}    ${VRF_UPLINK_PREFIX}
    ...    edge_path=${edge_path}
    Wait For Realization    ${VRF_PATH}/locale-services/${VRF_LS_ID}/interfaces/${VRF_UPLINK_IF_ID}

Configure Static Route On VRF
    [Documentation]    Add a static route inside the VRF's routing table and confirm it is
    ...                present with the expected network.
    [Tags]    vrf    routing    config
    Create Static Route On T0    ${VRF_ID}    ${VRF_ROUTE_ID}    ${VRF_STATIC_NETWORK}    ${VRF_STATIC_NEXTHOP}
    ${routes}=    Get Static Routes On T0    ${VRF_ID}
    ${route}=    Find In List    ${routes}    id    ${VRF_ROUTE_ID}
    Should Be Equal As Strings    ${route['network']}    ${VRF_STATIC_NETWORK}

Protect VRF Static Route Next Hop With BFD
    [Documentation]    Create a BFD profile and a static-route BFD peer for the next hop,
    ...                so the VRF withdraws the route when the peer goes down.
    [Tags]    vrf    bfd    config
    Create BFD Profile    ${VRF_BFD_PROFILE_ID}    ${BFD_INTERVAL}    ${BFD_MULTIPLIER}
    Create Static Route BFD Peer On T0    ${VRF_ID}    ${VRF_BFD_PEER_ID}    ${VRF_STATIC_NEXTHOP}
    ...    /infra/bfd-profiles/${VRF_BFD_PROFILE_ID}

Enable BGP And Create Neighbor On VRF
    [Documentation]    Enable BGP on the VRF locale service (the local ASN is inherited
    ...                from the parent T0) and create a BFD-enabled neighbor inside the VRF.
    [Tags]    vrf    bgp    config
    Enable BGP On T0 Locale Service    ${VRF_ID}    ${VRF_LS_ID}
    Create BGP Neighbor On T0    ${VRF_ID}    ${VRF_LS_ID}    ${VRF_NEIGHBOR_ID}
    ...    ${VRF_BGP_PEER_IP}    ${VRF_BGP_PEER_ASN}
    ...    bfd_enabled=${True}    bfd_interval=${BFD_INTERVAL}    bfd_multiplier=${BFD_MULTIPLIER}

Verify VRF Routing Objects Are Realized
    [Documentation]    The VRF with its interface, static route, and BGP neighbor must all
    ...                consolidate to realized SUCCESS.
    [Tags]    vrf    realization
    Wait For Realization    ${VRF_PATH}

Create VNI Pool For EVPN
    [Documentation]    Create the VXLAN VNI pool the parent T0's EVPN config and the VRF
    ...                transit VNI draw from.
    [Tags]    vrf    evpn    config
    Create VNI Pool    ${EVPN_VNI_POOL_ID}    ${EVPN_VNI_POOL_START}    ${EVPN_VNI_POOL_END}

Enable EVPN Inline Mode On Parent T0
    [Documentation]    Switch the PARENT T0 into EVPN INLINE mode using the VNI pool.
    ...                NOTE: this mutates a shared object and persists after the suite.
    [Tags]    vrf    evpn    config
    Configure EVPN On T0    ${T0_GATEWAY_ID}    INLINE    /infra/vni-pools/${EVPN_VNI_POOL_ID}
    ${evpn}=    Get EVPN Config On T0    ${T0_GATEWAY_ID}
    ${mode}=    Get Value    ${evpn}    mode
    Should Be Equal As Strings    ${mode}    INLINE

Attach EVPN RD RT And Transit VNI To VRF
    [Documentation]    PATCH the VRF with a route distinguisher, symmetric import/export
    ...                route targets, and an EVPN transit VNI from the pool, then verify
    ...                the RD landed on the object.
    [Tags]    vrf    evpn    config
    Create VRF Gateway On T0    ${VRF_ID}    VRF-Red    ${T0_PATH}
    ...    route_distinguisher=${VRF_RD}    evpn_transit_vni=${VRF_EVPN_TRANSIT_VNI}
    ...    import_rts=${{["$VRF_RT_IMPORT"]}}    export_rts=${{["$VRF_RT_EXPORT"]}}
    ${vrf}=    Get T0 Gateway    ${VRF_ID}
    ${rd}=    Get Value    ${vrf}    vrf_config.route_distinguisher
    Should Be Equal As Strings    ${rd}    ${VRF_RD}
