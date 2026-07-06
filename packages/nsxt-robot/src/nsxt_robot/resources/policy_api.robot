*** Settings ***
Documentation    Reusable keywords wrapping NSX-T Policy API operations.
Resource         common.robot


*** Variables ***
${INFRA_BASE}    ${POLICY_BASE}/infra


*** Keywords ***
# ──────────────────────────────────────────────
# T1 Gateways
# ──────────────────────────────────────────────

Create T1 Gateway
    [Documentation]    Create or update a Tier-1 gateway linked to T0.
    ...    route_adv_types accepts a list such as: TIER1_CONNECTED  TIER1_STATIC_ROUTES
    [Arguments]    ${id}    ${display_name}    ${t0_path}    @{route_adv_types}
    IF    len($route_adv_types) > 0
        ${adv}=    Set Variable    ${route_adv_types}
    ELSE
        ${adv}=    Create List    TIER1_CONNECTED
    END
    ${body}=    Create Dictionary
    ...    display_name=${display_name}
    ...    tier0_path=${t0_path}
    ...    route_advertisement_types=${adv}
    NSX REST PATCH    ${INFRA_BASE}/tier-1s/${id}    ${body}
    Log    Created T1 gateway: ${id}

Delete T1 Gateway
    [Documentation]    Delete a Tier-1 gateway.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/tier-1s/${id}

Get T1 Gateway
    [Documentation]    Retrieve a Tier-1 gateway by ID.
    [Arguments]    ${id}
    ${body}=    NSX REST GET    ${INFRA_BASE}/tier-1s/${id}
    RETURN    ${body}

# ──────────────────────────────────────────────
# Segments
# ──────────────────────────────────────────────

Create Overlay Segment
    [Documentation]    Create an overlay segment attached to a T1 gateway.
    [Arguments]    ${id}    ${t1_path}    ${tz_path}    ${subnet_cidr}
    ${subnet}=    Create Dictionary    gateway_address=${subnet_cidr}
    ${subnets}=    Create List    ${subnet}
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    connectivity_path=${t1_path}
    ...    transport_zone_path=${tz_path}
    ...    subnets=${subnets}
    NSX REST PATCH    ${INFRA_BASE}/segments/${id}    ${body}
    Log    Created overlay segment: ${id}

Create VLAN Segment
    [Documentation]    Create a VLAN-backed segment on a VLAN transport zone. Used for
    ...    T0/VRF external (uplink) interfaces. ${vlan_ids} is one or more VLAN IDs.
    [Arguments]    ${id}    ${tz_path}    @{vlan_ids}
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    transport_zone_path=${tz_path}
    ...    vlan_ids=${vlan_ids}
    NSX REST PATCH    ${INFRA_BASE}/segments/${id}    ${body}
    Log    Created VLAN segment: ${id} (VLANs ${vlan_ids})

Delete Segment
    [Documentation]    Delete a segment by ID.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/segments/${id}

Get Segment
    [Documentation]    Retrieve a segment by ID.
    [Arguments]    ${id}
    ${body}=    NSX REST GET    ${INFRA_BASE}/segments/${id}
    RETURN    ${body}

# ──────────────────────────────────────────────
# Static Routes
# ──────────────────────────────────────────────

Create Static Route On T1
    [Documentation]    Add a static route to a Tier-1 gateway.
    [Arguments]    ${t1_id}    ${route_id}    ${network}    ${next_hop}
    ${hop}=    Create Dictionary    ip_address=${next_hop}
    ${next_hops}=    Create List    ${hop}
    ${body}=    Create Dictionary
    ...    display_name=${route_id}
    ...    network=${network}
    ...    next_hops=${next_hops}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-1s/${t1_id}/static-routes/${route_id}
    ...    ${body}
    Log    Created static route ${route_id} on T1 ${t1_id}

Delete Static Route On T1
    [Documentation]    Delete a static route from a Tier-1 gateway.
    [Arguments]    ${t1_id}    ${route_id}
    Safe Delete Policy Object    ${INFRA_BASE}/tier-1s/${t1_id}/static-routes/${route_id}

Get Static Routes On T1
    [Documentation]    List all static routes on a Tier-1 gateway.
    [Arguments]    ${t1_id}
    ${body}=    NSX REST GET    ${INFRA_BASE}/tier-1s/${t1_id}/static-routes
    RETURN    ${body}

# ──────────────────────────────────────────────
# T0 Gateways / VRF
# ──────────────────────────────────────────────

Get T0 Gateway
    [Documentation]    Retrieve a Tier-0 gateway (or a T0-VRF gateway) by ID.
    [Arguments]    ${id}
    ${body}=    NSX REST GET    ${INFRA_BASE}/tier-0s/${id}
    RETURN    ${body}

Create VRF Gateway On T0
    [Documentation]    Create (or update) a Tier-0 VRF gateway linked to a parent T0.
    ...    A VRF is itself a tier-0 object, so every "... On T0" keyword (BGP, static
    ...    routes, interfaces, locale services) also works against ${vrf_id}. The EVPN
    ...    fields are optional: ${route_distinguisher} (e.g. 65001:100),
    ...    ${import_rts}/${export_rts} (lists of ASN:nn route targets, L2VPN_EVPN
    ...    address family), and ${evpn_transit_vni} (must belong to the parent's VNI
    ...    pool). Plain VRF-lite needs only ${parent_t0_path}.
    [Arguments]    ${vrf_id}    ${display_name}    ${parent_t0_path}    ${route_distinguisher}=${EMPTY}
    ...            ${evpn_transit_vni}=${EMPTY}    ${import_rts}=${EMPTY}    ${export_rts}=${EMPTY}
    ${vrf_config}=    Create Dictionary    tier0_path=${parent_t0_path}
    IF    '${route_distinguisher}' != '${EMPTY}'
        Set To Dictionary    ${vrf_config}    route_distinguisher=${route_distinguisher}
    END
    IF    $import_rts or $export_rts
        ${rt}=    Create Dictionary    address_family=L2VPN_EVPN
        IF    $import_rts
            Set To Dictionary    ${rt}    import_route_targets=${import_rts}
        END
        IF    $export_rts
            Set To Dictionary    ${rt}    export_route_targets=${export_rts}
        END
        ${rts}=    Create List    ${rt}
        Set To Dictionary    ${vrf_config}    route_targets=${rts}
    END
    IF    '${evpn_transit_vni}' != '${EMPTY}'
        ${vni}=    Convert To Integer    ${evpn_transit_vni}
        Set To Dictionary    ${vrf_config}    evpn_transit_vni=${vni}
    END
    ${body}=    Create Dictionary    display_name=${display_name}    vrf_config=${vrf_config}
    NSX REST PATCH    ${INFRA_BASE}/tier-0s/${vrf_id}    ${body}
    Log    Created VRF gateway ${vrf_id} linked to ${parent_t0_path}

Delete VRF Gateway
    [Documentation]    Delete a Tier-0 VRF gateway by ID.
    [Arguments]    ${vrf_id}
    Safe Delete Policy Object    ${INFRA_BASE}/tier-0s/${vrf_id}

Create T0 Locale Service
    [Documentation]    Create (or update) a locale service on a T0 or T0-VRF gateway.
    ...    ${edge_cluster_path} is optional for a VRF (it inherits the parent's edge
    ...    cluster) but required for a standalone T0.
    [Arguments]    ${t0_id}    ${ls_id}=default    ${edge_cluster_path}=${EMPTY}
    ${body}=    Create Dictionary    display_name=${ls_id}
    IF    '${edge_cluster_path}' != '${EMPTY}'
        Set To Dictionary    ${body}    edge_cluster_path=${edge_cluster_path}
    END
    NSX REST PATCH    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${ls_id}    ${body}
    Log    Created locale service ${ls_id} on T0 ${t0_id}

Delete T0 Locale Service
    [Documentation]    Delete a locale service from a T0 or T0-VRF gateway.
    [Arguments]    ${t0_id}    ${ls_id}=default
    Safe Delete Policy Object    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${ls_id}

Create T0 External Interface
    [Documentation]    Create an EXTERNAL (uplink) interface on a T0 or T0-VRF locale
    ...    service, attached to a VLAN segment. ${edge_path} pins the interface to a
    ...    specific edge node (required for EXTERNAL interfaces).
    [Arguments]    ${t0_id}    ${ls_id}    ${if_id}    ${segment_path}    ${ip_address}    ${prefix_len}
    ...            ${edge_path}=${EMPTY}    ${mtu}=${EMPTY}
    ${prefix_int}=    Convert To Integer    ${prefix_len}
    ${ips}=    Create List    ${ip_address}
    ${subnet}=    Create Dictionary    ip_addresses=${ips}    prefix_len=${prefix_int}
    ${subnets}=    Create List    ${subnet}
    ${body}=    Create Dictionary
    ...    display_name=${if_id}
    ...    type=EXTERNAL
    ...    segment_path=${segment_path}
    ...    subnets=${subnets}
    IF    '${edge_path}' != '${EMPTY}'
        Set To Dictionary    ${body}    edge_path=${edge_path}
    END
    IF    '${mtu}' != '${EMPTY}'
        ${mtu_int}=    Convert To Integer    ${mtu}
        Set To Dictionary    ${body}    mtu=${mtu_int}
    END
    NSX REST PATCH    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${ls_id}/interfaces/${if_id}    ${body}
    Log    Created external interface ${if_id} (${ip_address}/${prefix_len}) on T0 ${t0_id}

Get T0 Interfaces
    [Documentation]    List the interfaces of a T0 (or T0-VRF) locale service.
    [Arguments]    ${t0_id}    ${ls_id}=default
    ${body}=    NSX REST GET    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${ls_id}/interfaces
    RETURN    ${body}

Delete T0 Interface
    [Documentation]    Delete an interface from a T0 (or T0-VRF) locale service.
    [Arguments]    ${t0_id}    ${ls_id}    ${if_id}
    Safe Delete Policy Object    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${ls_id}/interfaces/${if_id}

# ──────────────────────────────────────────────
# T0 Static Routing + BFD
# ──────────────────────────────────────────────

Create Static Route On T0
    [Documentation]    Add a static route to a T0 or T0-VRF gateway.
    [Arguments]    ${t0_id}    ${route_id}    ${network}    ${next_hop}
    ${hop}=    Create Dictionary    ip_address=${next_hop}
    ${next_hops}=    Create List    ${hop}
    ${body}=    Create Dictionary
    ...    display_name=${route_id}
    ...    network=${network}
    ...    next_hops=${next_hops}
    NSX REST PATCH    ${INFRA_BASE}/tier-0s/${t0_id}/static-routes/${route_id}    ${body}
    Log    Created static route ${route_id} on T0 ${t0_id}

Delete Static Route On T0
    [Documentation]    Delete a static route from a T0 or T0-VRF gateway.
    [Arguments]    ${t0_id}    ${route_id}
    Safe Delete Policy Object    ${INFRA_BASE}/tier-0s/${t0_id}/static-routes/${route_id}

Get Static Routes On T0
    [Documentation]    List all static routes on a T0 or T0-VRF gateway.
    [Arguments]    ${t0_id}
    ${body}=    NSX REST GET    ${INFRA_BASE}/tier-0s/${t0_id}/static-routes
    RETURN    ${body}

Create BFD Profile
    [Documentation]    Create a reusable BFD profile (/infra/bfd-profiles). ${interval} is
    ...    the transmit/receive interval in milliseconds; ${multiple} the declare-dead
    ...    multiplier.
    [Arguments]    ${id}    ${interval}=500    ${multiple}=3
    ${interval_int}=    Convert To Integer    ${interval}
    ${multiple_int}=    Convert To Integer    ${multiple}
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    interval=${interval_int}
    ...    multiple=${multiple_int}
    NSX REST PATCH    ${INFRA_BASE}/bfd-profiles/${id}    ${body}
    Log    Created BFD profile ${id} (interval ${interval}ms x${multiple})

Delete BFD Profile
    [Documentation]    Delete a BFD profile.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/bfd-profiles/${id}

Create Static Route BFD Peer On T0
    [Documentation]    Create a BFD peer for static routes on a T0 or T0-VRF gateway: the
    ...    static routes via ${peer_ip} are withdrawn when the BFD session goes down.
    [Arguments]    ${t0_id}    ${peer_id}    ${peer_ip}    ${bfd_profile_path}=${EMPTY}
    ${body}=    Create Dictionary
    ...    display_name=${peer_id}
    ...    peer_address=${peer_ip}
    ...    enabled=${True}
    IF    '${bfd_profile_path}' != '${EMPTY}'
        Set To Dictionary    ${body}    bfd_profile_path=${bfd_profile_path}
    END
    NSX REST PATCH    ${INFRA_BASE}/tier-0s/${t0_id}/static-routes/bfd-peers/${peer_id}    ${body}
    Log    Created static-route BFD peer ${peer_id} (${peer_ip}) on T0 ${t0_id}

Delete Static Route BFD Peer On T0
    [Documentation]    Delete a static-route BFD peer from a T0 or T0-VRF gateway.
    [Arguments]    ${t0_id}    ${peer_id}
    Safe Delete Policy Object    ${INFRA_BASE}/tier-0s/${t0_id}/static-routes/bfd-peers/${peer_id}

# ──────────────────────────────────────────────
# BGP
# ──────────────────────────────────────────────

Enable BGP On T0 Locale Service
    [Documentation]    Enable BGP on a T0/T0-VRF locale service without setting an ASN.
    ...    Use this for VRF gateways, which inherit the local ASN from the parent T0
    ...    (setting local_as_num on a VRF is rejected); use Configure BGP On T0 for a
    ...    parent/standalone T0 where the ASN must be set.
    [Arguments]    ${t0_id}    ${locale_service_id}=default
    ${body}=    Create Dictionary    enabled=${True}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}/bgp
    ...    ${body}
    Log    Enabled BGP on T0 ${t0_id} (ASN inherited)

Configure BGP On T0
    [Documentation]    Enable BGP and set local ASN on a T0 gateway locale service.
    [Arguments]    ${t0_id}    ${locale_service_id}    ${local_asn}
    ${body}=    Create Dictionary
    ...    local_as_num=${local_asn}
    ...    enabled=${True}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}/bgp
    ...    ${body}
    Log    Configured BGP on T0 ${t0_id} with ASN ${local_asn}

Create BGP Neighbor On T0
    [Documentation]    Create a BGP neighbor entry on a T0 gateway with optional BFD.
    [Arguments]    ${t0_id}    ${locale_service_id}    ${neighbor_id}    ${peer_ip}
    ...            ${remote_asn}    ${bfd_enabled}=${True}    ${bfd_interval}=500    ${bfd_multiplier}=3
    ${bfd}=    Create Dictionary
    ...    enabled=${bfd_enabled}
    ...    interval=${bfd_interval}
    ...    multiple=${bfd_multiplier}
    ${body}=    Create Dictionary
    ...    display_name=${neighbor_id}
    ...    neighbor_address=${peer_ip}
    ...    remote_as_num=${remote_asn}
    ...    bfd_config=${bfd}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}/bgp/neighbors/${neighbor_id}
    ...    ${body}
    Log    Created BGP neighbor ${neighbor_id} (${peer_ip}) on T0 ${t0_id}

Get BGP Neighbor Status
    [Documentation]    Retrieve BGP neighbor operational status.
    [Arguments]    ${t0_id}    ${locale_service_id}    ${neighbor_id}
    ${body}=    NSX REST GET
    ...    ${POLICY_BASE}/infra/tier-0s/${t0_id}/locale-services/${locale_service_id}/bgp/neighbors/${neighbor_id}/status
    RETURN    ${body}

Delete BGP Neighbor On T0
    [Documentation]    Delete a BGP neighbor from a T0 gateway.
    [Arguments]    ${t0_id}    ${locale_service_id}    ${neighbor_id}
    Safe Delete Policy Object
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}/bgp/neighbors/${neighbor_id}

Get BGP Routes On T0
    [Documentation]    Retrieve BGP routes learned from a specific neighbor on the T0 gateway.
    ...    Routes are reported per neighbor, not for the gateway as a whole.
    [Arguments]    ${t0_id}    ${locale_service_id}    ${neighbor_id}
    ${body}=    NSX REST GET
    ...    ${POLICY_BASE}/infra/tier-0s/${t0_id}/locale-services/${locale_service_id}/bgp/neighbors/${neighbor_id}/routes
    RETURN    ${body}

# ──────────────────────────────────────────────
# HA VIP
# ──────────────────────────────────────────────

Create HA VIP Config On T0
    [Documentation]    Configure an HA VIP on a T0 locale service.
    [Arguments]    ${t0_id}    ${locale_service_id}    ${vip_ip}    ${edge_path_1}    ${edge_path_2}
    ${vip_config}=    Create Dictionary
    ...    vip_subnets=@{EMPTY}
    ...    enabled=${True}
    ${vip_ip_list}=    Create List    ${vip_ip.split('/')[0]}
    ${subnet}=    Create Dictionary    prefix_len=${vip_ip.split('/')[1]}    ip_addresses=${vip_ip_list}
    ${vip_subnets}=    Create List    ${subnet}
    Set To Dictionary    ${vip_config}    vip_subnets=${vip_subnets}
    ${edge_paths}=    Create List    ${edge_path_1}    ${edge_path_2}
    Set To Dictionary    ${vip_config}    external_interface_paths=${edge_paths}
    ${ha_vip_configs}=    Create List    ${vip_config}
    ${body}=    Create Dictionary    ha_vip_configs=${ha_vip_configs}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}
    ...    ${body}
    Log    Configured HA VIP ${vip_ip} on T0 ${t0_id}

Remove HA VIP Config On T0
    [Documentation]    Remove HA VIP configuration from a T0 locale service.
    [Arguments]    ${t0_id}    ${locale_service_id}
    ${body}=    Create Dictionary    ha_vip_configs=@{EMPTY}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}
    ...    ${body}

Get T0 Locale Service
    [Documentation]    Retrieve the locale service config for a T0 gateway.
    [Arguments]    ${t0_id}    ${locale_service_id}
    ${body}=    NSX REST GET
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${locale_service_id}
    RETURN    ${body}

# ──────────────────────────────────────────────
# NAT
# ──────────────────────────────────────────────

Create SNAT Rule On T1
    [Documentation]    Create an SNAT rule on a Tier-1 gateway.
    [Arguments]    ${t1_id}    ${rule_id}    ${translated_ip}    ${source_network}
    ${body}=    Create Dictionary
    ...    display_name=${rule_id}
    ...    action=SNAT
    ...    translated_network=${translated_ip}
    ...    source_network=${source_network}
    ...    enabled=${True}
    ...    logging=${False}
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-1s/${t1_id}/nat/USER/nat-rules/${rule_id}
    ...    ${body}
    Log    Created SNAT rule ${rule_id} on T1 ${t1_id}

Create DNAT Rule On T1
    [Documentation]    Create a DNAT rule on a Tier-1 gateway: inbound traffic to
    ...    ${destination_ip} is translated to the internal ${translated_ip}. An optional
    ...    ${translated_port} restricts the rule to a single service port.
    [Arguments]    ${t1_id}    ${rule_id}    ${destination_ip}    ${translated_ip}    ${translated_port}=${EMPTY}
    ${body}=    Create Dictionary
    ...    display_name=${rule_id}
    ...    action=DNAT
    ...    destination_network=${destination_ip}
    ...    translated_network=${translated_ip}
    ...    enabled=${True}
    ...    logging=${False}
    IF    '${translated_port}' != '${EMPTY}'
        Set To Dictionary    ${body}    translated_ports=${translated_port}
    END
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-1s/${t1_id}/nat/USER/nat-rules/${rule_id}
    ...    ${body}
    Log    Created DNAT rule ${rule_id} on T1 ${t1_id}: ${destination_ip} → ${translated_ip}

Delete NAT Rule On T1
    [Documentation]    Delete a NAT rule from a Tier-1 gateway.
    [Arguments]    ${t1_id}    ${rule_id}
    Safe Delete Policy Object
    ...    ${INFRA_BASE}/tier-1s/${t1_id}/nat/USER/nat-rules/${rule_id}

Get NAT Rules On T1
    [Documentation]    List all NAT rules on a Tier-1 gateway.
    [Arguments]    ${t1_id}
    ${body}=    NSX REST GET    ${INFRA_BASE}/tier-1s/${t1_id}/nat/USER/nat-rules
    RETURN    ${body}

Get NAT Statistics On T1
    [Documentation]    Retrieve NAT statistics for a Tier-1 gateway.
    [Arguments]    ${t1_id}
    ${body}=    NSX REST GET
    ...    ${POLICY_BASE}/infra/tier-1s/${t1_id}/nat/USER/nat-rules?action=statistics
    RETURN    ${body}

# ──────────────────────────────────────────────
# Load Balancer (Basic NSX LB)
# ──────────────────────────────────────────────

Create LB Service
    [Documentation]    Create an NSX LB service attached to a T1 gateway.
    [Arguments]    ${id}    ${t1_path}    ${size}=SMALL
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    connectivity_path=${t1_path}
    ...    size=${size}
    NSX REST PATCH    ${INFRA_BASE}/lb-services/${id}    ${body}
    Log    Created LB service: ${id}

Create LB Pool
    [Documentation]    Create an NSX LB server pool with members. When ${monitor_path} is
    ...    provided the pool is bound to that active health monitor.
    [Arguments]    ${id}    ${members}    ${port}    ${monitor_path}=${EMPTY}
    ${member_list}=    Create List
    FOR    ${member_ip}    IN    @{members}
        ${member}=    Create Dictionary
        ...    display_name=${member_ip}
        ...    ip_address=${member_ip}
        ...    port=${port}
        Append To List    ${member_list}    ${member}
    END
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    members=${member_list}
    IF    '${monitor_path}' != '${EMPTY}'
        ${monitor_paths}=    Create List    ${monitor_path}
        Set To Dictionary    ${body}    active_monitor_paths=${monitor_paths}
    END
    NSX REST PATCH    ${INFRA_BASE}/lb-pools/${id}    ${body}
    Log    Created LB pool: ${id} (monitor: ${monitor_path})

Create LB HTTP Monitor
    [Documentation]    Create an active HTTP health monitor profile. The pool that binds it
    ...    marks members UP only when they answer ${request_url} with one of ${response_codes}.
    [Arguments]    ${id}    ${monitor_port}    ${request_url}=/    ${response_codes}=${{[200]}}
    ${port_int}=    Convert To Integer    ${monitor_port}
    ${body}=    Create Dictionary
    ...    resource_type=LBHttpMonitorProfile
    ...    display_name=${id}
    ...    monitor_port=${port_int}
    ...    request_url=${request_url}
    ...    request_method=GET
    ...    response_status_codes=${response_codes}
    NSX REST PATCH    ${INFRA_BASE}/lb-monitor-profiles/${id}    ${body}
    Log    Created LB HTTP monitor: ${id} (port ${monitor_port}, url ${request_url})

Delete LB Monitor
    [Documentation]    Delete an LB monitor profile.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/lb-monitor-profiles/${id}

Create LB Virtual Server
    [Documentation]    Create an NSX LB virtual server (TCP/L4).
    [Arguments]    ${id}    ${pool_path}    ${vip}    ${port}    ${lb_service_path}
    ${ports}=    Create List    ${port}
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    ip_address=${vip}
    ...    ports=${ports}
    ...    pool_path=${pool_path}
    ...    lb_service_path=${lb_service_path}
    ...    application_profile_path=/infra/lb-app-profiles/default-tcp-lb-app-profile
    NSX REST PATCH    ${INFRA_BASE}/lb-virtual-servers/${id}    ${body}
    Log    Created LB virtual server: ${id}

Create LB HTTP Virtual Server
    [Documentation]    Create an NSX L7 HTTP virtual server (uses the default HTTP application
    ...    profile, so the LB terminates and proxies HTTP rather than forwarding raw TCP).
    [Arguments]    ${id}    ${pool_path}    ${vip}    ${port}    ${lb_service_path}
    ${ports}=    Create List    ${port}
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    ip_address=${vip}
    ...    ports=${ports}
    ...    pool_path=${pool_path}
    ...    lb_service_path=${lb_service_path}
    ...    application_profile_path=/infra/lb-app-profiles/default-http-lb-app-profile
    NSX REST PATCH    ${INFRA_BASE}/lb-virtual-servers/${id}    ${body}
    Log    Created L7 HTTP LB virtual server: ${id}

Get LB Pool Status
    [Documentation]    Retrieve operational status of an LB pool.
    [Arguments]    ${id}    ${lb_service_id}
    ${body}=    NSX REST GET
    ...    ${POLICY_BASE}/infra/lb-services/${lb_service_id}/lb-pools/${id}/status
    RETURN    ${body}

Delete LB Virtual Server
    [Documentation]    Delete an LB virtual server.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/lb-virtual-servers/${id}

Delete LB Pool
    [Documentation]    Delete an LB pool.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/lb-pools/${id}

Delete LB Service
    [Documentation]    Delete an LB service.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/lb-services/${id}

# ──────────────────────────────────────────────
# Tags
# ──────────────────────────────────────────────

Set Tags On Segment
    [Documentation]    Replace the tag set on a segment. ${tags} is a list of
    ...    scope|value strings, e.g.    Create List    app|web    tier|frontend
    [Arguments]    ${segment_id}    @{tags}
    ${tag_list}=    Create List
    FOR    ${entry}    IN    @{tags}
        ${scope}    ${value}=    Evaluate    ($entry.split('|', 1) + [''])[:2]
        ${tag}=    Create Dictionary    scope=${scope}    tag=${value}
        Append To List    ${tag_list}    ${tag}
    END
    ${body}=    Create Dictionary    tags=${tag_list}
    NSX REST PATCH    ${INFRA_BASE}/segments/${segment_id}    ${body}
    Log    Set tags on segment ${segment_id}: ${tags}

# ──────────────────────────────────────────────
# Groups (NSGroups)
# ──────────────────────────────────────────────

Create IP Group
    [Documentation]    Create a group whose membership is a static set of IP addresses/CIDRs.
    [Arguments]    ${group_id}    ${ip_addresses}    ${domain}=default
    ${expr}=    Create Dictionary
    ...    resource_type=IPAddressExpression
    ...    ip_addresses=${ip_addresses}
    ${expressions}=    Create List    ${expr}
    ${body}=    Create Dictionary    display_name=${group_id}    expression=${expressions}
    NSX REST PATCH    ${INFRA_BASE}/domains/${domain}/groups/${group_id}    ${body}
    Log    Created IP group ${group_id}: ${ip_addresses}

Create Tag Group
    [Documentation]    Create a group with dynamic membership: VMs carrying the tag
    ...    ${scope_value} (a scope|value string, e.g. app|web) join the group.
    [Arguments]    ${group_id}    ${scope_value}    ${domain}=default
    ${expr}=    Create Dictionary
    ...    resource_type=Condition
    ...    member_type=VirtualMachine
    ...    key=Tag
    ...    operator=EQUALS
    ...    value=${scope_value}
    ${expressions}=    Create List    ${expr}
    ${body}=    Create Dictionary    display_name=${group_id}    expression=${expressions}
    NSX REST PATCH    ${INFRA_BASE}/domains/${domain}/groups/${group_id}    ${body}
    Log    Created tag group ${group_id}: VMs tagged '${scope_value}'

Get Group
    [Documentation]    Retrieve a group definition by ID.
    [Arguments]    ${group_id}    ${domain}=default
    ${body}=    NSX REST GET    ${INFRA_BASE}/domains/${domain}/groups/${group_id}
    RETURN    ${body}

Get Group Members
    [Documentation]    Retrieve the effective (realized) VM members of a group.
    [Arguments]    ${group_id}    ${domain}=default
    ${body}=    NSX REST GET
    ...    ${INFRA_BASE}/domains/${domain}/groups/${group_id}/members/virtual-machines
    RETURN    ${body}

Delete Group
    [Documentation]    Delete a group by ID.
    [Arguments]    ${group_id}    ${domain}=default
    Safe Delete Policy Object    ${INFRA_BASE}/domains/${domain}/groups/${group_id}

# ──────────────────────────────────────────────
# Distributed Firewall (DFW)
# ──────────────────────────────────────────────

Create Security Policy
    [Documentation]    Create (or update) an empty DFW security policy in a domain. Lower
    ...    ${sequence_number} values are evaluated first relative to other policies.
    [Arguments]    ${policy_id}    ${sequence_number}=10    ${category}=Application    ${domain}=default
    ${body}=    Create Dictionary
    ...    display_name=${policy_id}
    ...    category=${category}
    ...    sequence_number=${sequence_number}
    NSX REST PATCH    ${INFRA_BASE}/domains/${domain}/security-policies/${policy_id}    ${body}
    Log    Created security policy ${policy_id} (category ${category})

Create DFW Rule
    [Documentation]    Create a distributed firewall rule inside a security policy.
    ...    ${action} is ALLOW, DROP, or REJECT. ${source_groups}/${destination_groups}/${services}
    ...    are lists of Policy paths (or ["ANY"]).
    [Arguments]    ${policy_id}    ${rule_id}    ${source_groups}    ${destination_groups}
    ...    ${action}=ALLOW    ${services}=${{['ANY']}}    ${sequence_number}=10    ${domain}=default
    ${body}=    Create Dictionary
    ...    display_name=${rule_id}
    ...    source_groups=${source_groups}
    ...    destination_groups=${destination_groups}
    ...    services=${services}
    ...    action=${action}
    ...    direction=IN_OUT
    ...    ip_protocol=IPV4_IPV6
    ...    sequence_number=${sequence_number}
    NSX REST PATCH
    ...    ${INFRA_BASE}/domains/${domain}/security-policies/${policy_id}/rules/${rule_id}
    ...    ${body}
    Log    Created DFW rule ${rule_id} (${action}) in policy ${policy_id}

Get DFW Rules
    [Documentation]    List the rules of a security policy.
    [Arguments]    ${policy_id}    ${domain}=default
    ${body}=    NSX REST GET
    ...    ${INFRA_BASE}/domains/${domain}/security-policies/${policy_id}/rules
    RETURN    ${body}

Delete DFW Rule
    [Documentation]    Delete a single DFW rule from a security policy.
    [Arguments]    ${policy_id}    ${rule_id}    ${domain}=default
    Safe Delete Policy Object
    ...    ${INFRA_BASE}/domains/${domain}/security-policies/${policy_id}/rules/${rule_id}

Delete Security Policy
    [Documentation]    Delete a security policy (and all its rules) by ID.
    [Arguments]    ${policy_id}    ${domain}=default
    Safe Delete Policy Object    ${INFRA_BASE}/domains/${domain}/security-policies/${policy_id}

# ──────────────────────────────────────────────
# Gateway Firewall (T0/T1 edge/perimeter firewall)
# ──────────────────────────────────────────────
# Distinct from DFW above: DFW is distributed (east-west, enforced at the vNIC) and
# lives under .../security-policies. Gateway Firewall is centralized (north-south,
# enforced at the T0/T1 edge) and lives under .../gateway-policies, with each rule
# scoped to the specific gateway path it applies to. Category naming is
# version-sensitive across NSX releases, like EVPN below — LocalGatewayRules is the
# common default; verify against your release's API reference on the first live run.

Create Gateway Firewall Policy
    [Documentation]    Create (or update) an empty Gateway Firewall policy in a domain. Lower
    ...    ${sequence_number} values are evaluated first relative to other gateway policies.
    [Arguments]    ${policy_id}    ${sequence_number}=10    ${category}=LocalGatewayRules    ${domain}=default
    ${body}=    Create Dictionary
    ...    display_name=${policy_id}
    ...    category=${category}
    ...    sequence_number=${sequence_number}
    NSX REST PATCH    ${INFRA_BASE}/domains/${domain}/gateway-policies/${policy_id}    ${body}
    Log    Created gateway firewall policy ${policy_id} (category ${category})

Create Gateway Firewall Rule
    [Documentation]    Create a gateway (edge/perimeter) firewall rule inside a gateway policy,
    ...    scoped to ${gateway_path} (the T0/T1 Policy path this rule applies to, e.g.
    ...    /infra/tier-1s/T1_ID). ${action} is ALLOW, DROP, or REJECT.
    ...    ${source_groups}/${destination_groups}/${services} are lists of Policy paths
    ...    (or ["ANY"]).
    [Arguments]    ${policy_id}    ${rule_id}    ${gateway_path}    ${source_groups}    ${destination_groups}
    ...    ${action}=ALLOW    ${services}=${{['ANY']}}    ${sequence_number}=10    ${domain}=default
    ${scope}=    Create List    ${gateway_path}
    ${body}=    Create Dictionary
    ...    display_name=${rule_id}
    ...    source_groups=${source_groups}
    ...    destination_groups=${destination_groups}
    ...    services=${services}
    ...    action=${action}
    ...    direction=IN_OUT
    ...    ip_protocol=IPV4_IPV6
    ...    scope=${scope}
    ...    sequence_number=${sequence_number}
    NSX REST PATCH
    ...    ${INFRA_BASE}/domains/${domain}/gateway-policies/${policy_id}/rules/${rule_id}
    ...    ${body}
    Log    Created gateway firewall rule ${rule_id} (${action}) in policy ${policy_id}, scope ${gateway_path}

Get Gateway Firewall Rules
    [Documentation]    List the rules of a gateway firewall policy.
    [Arguments]    ${policy_id}    ${domain}=default
    ${body}=    NSX REST GET
    ...    ${INFRA_BASE}/domains/${domain}/gateway-policies/${policy_id}/rules
    RETURN    ${body}

Delete Gateway Firewall Rule
    [Documentation]    Delete a single gateway firewall rule from a gateway policy.
    [Arguments]    ${policy_id}    ${rule_id}    ${domain}=default
    Safe Delete Policy Object
    ...    ${INFRA_BASE}/domains/${domain}/gateway-policies/${policy_id}/rules/${rule_id}

Delete Gateway Firewall Policy
    [Documentation]    Delete a gateway firewall policy (and all its rules) by ID.
    [Arguments]    ${policy_id}    ${domain}=default
    Safe Delete Policy Object    ${INFRA_BASE}/domains/${domain}/gateway-policies/${policy_id}

# ──────────────────────────────────────────────
# EVPN (NSX 3.1+ / 4.x)
# ──────────────────────────────────────────────
# Field names follow the NSX 4.x EvpnConfig/VniPoolConfig schemas. EVPN endpoints
# are the most version-sensitive part of the Policy API — verify against your
# release's API reference before the first live run.

Create VNI Pool
    [Documentation]    Create a VNI pool (/infra/vni-pools) for EVPN VXLAN encapsulation.
    ...    VRF evpn_transit_vni values must fall inside [${start}, ${end}].
    [Arguments]    ${id}    ${start}    ${end}
    ${start_int}=    Convert To Integer    ${start}
    ${end_int}=    Convert To Integer    ${end}
    ${body}=    Create Dictionary
    ...    display_name=${id}
    ...    start=${start_int}
    ...    end=${end_int}
    NSX REST PATCH    ${INFRA_BASE}/vni-pools/${id}    ${body}
    Log    Created VNI pool ${id} (${start}-${end})

Delete VNI Pool
    [Documentation]    Delete a VNI pool.
    [Arguments]    ${id}
    Safe Delete Policy Object    ${INFRA_BASE}/vni-pools/${id}

Configure EVPN On T0
    [Documentation]    Enable EVPN on a parent T0 gateway. ${mode} is INLINE or
    ...    ROUTE_SERVER; ${vni_pool_path} selects the VXLAN VNI pool used for the
    ...    per-VRF transit VNIs (required for INLINE mode).
    [Arguments]    ${t0_id}    ${mode}=INLINE    ${vni_pool_path}=${EMPTY}
    ${body}=    Create Dictionary    mode=${mode}
    IF    '${vni_pool_path}' != '${EMPTY}'
        ${encap}=    Create Dictionary    encapsulation_type=VXLAN    vni_pool_path=${vni_pool_path}
        Set To Dictionary    ${body}    encapsulation_method=${encap}
    END
    NSX REST PATCH    ${INFRA_BASE}/tier-0s/${t0_id}/evpn    ${body}
    Log    Configured EVPN ${mode} on T0 ${t0_id}

Get EVPN Config On T0
    [Documentation]    Retrieve the EVPN configuration of a T0 gateway.
    [Arguments]    ${t0_id}
    ${body}=    NSX REST GET    ${INFRA_BASE}/tier-0s/${t0_id}/evpn
    RETURN    ${body}

Create EVPN Tunnel Endpoint On T0
    [Documentation]    Create an EVPN (VXLAN) tunnel endpoint on a T0 locale service,
    ...    pinned to an edge node. ${local_address} is the VTEP loopback IP advertised
    ...    to the DC gateways.
    [Arguments]    ${t0_id}    ${ls_id}    ${te_id}    ${edge_path}    ${local_address}    ${mtu}=${EMPTY}
    ${addresses}=    Create List    ${local_address}
    ${body}=    Create Dictionary
    ...    display_name=${te_id}
    ...    edge_path=${edge_path}
    ...    local_addresses=${addresses}
    IF    '${mtu}' != '${EMPTY}'
        ${mtu_int}=    Convert To Integer    ${mtu}
        Set To Dictionary    ${body}    mtu=${mtu_int}
    END
    NSX REST PATCH
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${ls_id}/evpn-tunnel-endpoints/${te_id}
    ...    ${body}
    Log    Created EVPN tunnel endpoint ${te_id} (${local_address}) on T0 ${t0_id}

Delete EVPN Tunnel Endpoint On T0
    [Documentation]    Delete an EVPN tunnel endpoint from a T0 locale service.
    [Arguments]    ${t0_id}    ${ls_id}    ${te_id}
    Safe Delete Policy Object
    ...    ${INFRA_BASE}/tier-0s/${t0_id}/locale-services/${ls_id}/evpn-tunnel-endpoints/${te_id}

# ──────────────────────────────────────────────
# Infra / Manager API
# ──────────────────────────────────────────────

Get Edge Nodes In Cluster
    [Documentation]    List the edge nodes of a Policy edge cluster. Each result carries
    ...    a ``path`` usable as ${edge_path} for external interfaces and EVPN endpoints.
    [Arguments]    ${edge_cluster_id}
    ${body}=    NSX REST GET
    ...    ${POLICY_BASE}/infra/sites/default/enforcement-points/default/edge-clusters/${edge_cluster_id}/edge-nodes
    RETURN    ${body}

Get Manager Cluster Status
    [Documentation]    Retrieve NSX Manager cluster status via the management API.
    ${body}=    NSX REST GET    ${MGMT_BASE}/cluster/status
    RETURN    ${body}

Get Transport Zones
    [Documentation]    List all transport zones.
    ${body}=    NSX REST GET    ${MGMT_BASE}/transport-zones
    RETURN    ${body}

Get Transport Node Status
    [Documentation]    Retrieve status for a specific transport node.
    [Arguments]    ${tn_id}
    ${body}=    NSX REST GET    ${MGMT_BASE}/transport-nodes/${tn_id}/status
    RETURN    ${body}

Get All Transport Node Statuses
    [Documentation]    List the status of all transport nodes.
    ${body}=    NSX REST GET    ${MGMT_BASE}/transport-nodes/status
    RETURN    ${body}

Get Compute Managers
    [Documentation]    List all registered compute managers (vCenter).
    ${body}=    NSX REST GET    ${MGMT_BASE}/fabric/compute-managers
    RETURN    ${body}

Get Compute Manager Status
    [Documentation]    Retrieve the registration and connectivity status of a compute manager.
    [Arguments]    ${cm_id}
    ${body}=    NSX REST GET    ${MGMT_BASE}/fabric/compute-managers/${cm_id}/status
    RETURN    ${body}
