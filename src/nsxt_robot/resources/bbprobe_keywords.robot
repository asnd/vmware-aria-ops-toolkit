*** Settings ***
Documentation    Structured data-plane validation using the `bbprobe` binary over SSH.
...              Replaces string-scraping ping/curl/nc with JSON-parseable probes that
...              carry success, per-attempt results, and latency. Also deploys the binary
...              to the test VMs via SCP (SSHLibrary Put File): by default, the release
...              matching each VM's own architecture is downloaded from the pinned
...              ${BBPROBE_VERSION} GitHub release, checksum-verified against its
...              published SHA256SUMS, and cached locally — set ${BBPROBE_LOCAL_PATH} to
...              use a custom or offline/air-gapped build instead.
Library          Collections
Library          String
Library          SSHLibrary
Library          nsxt_robot.BbprobeRelease
Resource         common.robot
Resource         ssh_keywords.robot


*** Variables ***
# Set an absolute path to use a custom or offline/air-gapped build instead of the
# auto-downloaded, checksum-verified release below.
${BBPROBE_LOCAL_PATH}          ${EMPTY}
${BBPROBE_VERSION}             v0.9.0
${BBPROBE_RELEASE_BASE_URL}    https://github.com/asnd/bbprobe/releases/download
${BBPROBE_CACHE_DIR}           %{HOME}/.cache/nsxt-robot/bbprobe
${BBPROBE_REMOTE_PATH}         /usr/local/bin/bbprobe
${BBPROBE_SSH_TIMEOUT}         30s
${PROBE_MAX_LATENCY}           2.0
# Test VMs to deploy bbprobe onto. Defaults to the two-VM pair from env.yaml, but a
# consuming suite can override @{TEST_VM_IPS} to cover any number of hosts.
@{TEST_VM_IPS}                 ${VM1_IP}    ${VM2_IP}


*** Keywords ***
# ──────────────────────────────────────────────
# Deployment
# ──────────────────────────────────────────────

Resolve bbprobe Binary For VM
    [Documentation]    Return a local path to a bbprobe binary that will run on ${vm_ip}.
    ...    Uses ${BBPROBE_LOCAL_PATH} as-is when set (custom/offline build). Otherwise
    ...    detects the VM's own architecture over the (already open) SSH connection and
    ...    downloads + checksum-verifies the pinned ${BBPROBE_VERSION} release for it,
    ...    caching the result under ${BBPROBE_CACHE_DIR} so repeat deploys don't re-fetch.
    [Arguments]    ${vm_ip}
    IF    '${BBPROBE_LOCAL_PATH}' != '${EMPTY}'
        RETURN    ${BBPROBE_LOCAL_PATH}
    END
    ${uname_s}    ${rc_s}=    Execute Command    uname -s    return_rc=True
    Should Be Equal As Integers    ${rc_s}    0    msg=uname -s failed on ${vm_ip}: ${uname_s}
    ${uname_m}    ${rc_m}=    Execute Command    uname -m    return_rc=True
    Should Be Equal As Integers    ${rc_m}    0    msg=uname -m failed on ${vm_ip}: ${uname_m}
    ${asset_name}=    Get bbprobe Asset Name    ${BBPROBE_VERSION}    ${uname_s.strip()}    ${uname_m.strip()}
    ${local_path}=    Ensure bbprobe Binary Is Cached
    ...    ${BBPROBE_VERSION}    ${asset_name}    ${BBPROBE_CACHE_DIR}    ${BBPROBE_RELEASE_BASE_URL}
    RETURN    ${local_path}

Deploy bbprobe To VM
    [Documentation]    SCP the bbprobe binary to a VM, make it executable, verify it runs,
    ...                and grant unprivileged ICMP (setcap, else ping_group_range).
    [Arguments]    ${vm_ip}
    Ensure SSH To VM    ${vm_ip}
    ${local_path}=    Resolve bbprobe Binary For VM    ${vm_ip}
    Put File    ${local_path}    ${BBPROBE_REMOTE_PATH}    mode=0755
    ${out}    ${rc}=    Execute Command    ${BBPROBE_REMOTE_PATH} --version    return_rc=True
    Should Be Equal As Integers    ${rc}    0    msg=bbprobe --version failed on ${vm_ip}: ${out}
    ${cap_out}    ${cap_rc}=    Execute Command
    ...    setcap cap_net_raw+ep ${BBPROBE_REMOTE_PATH} 2>/dev/null || sysctl -w net.ipv4.ping_group_range="0 2147483647"
    ...    return_rc=True
    Log    Deployed bbprobe to ${vm_ip}: ${out} (icmp-setup rc=${cap_rc})

Deploy bbprobe To All Test VMs
    [Documentation]    Deploy bbprobe to every VM in @{TEST_VM_IPS} (default: VM1_IP, VM2_IP).
    FOR    ${vm_ip}    IN    @{TEST_VM_IPS}
        Deploy bbprobe To VM    ${vm_ip}
    END

# ──────────────────────────────────────────────
# Probe execution
# ──────────────────────────────────────────────

Run bbprobe
    [Documentation]    Run bbprobe on a VM and return the parsed JSON result dict and exit code.
    ...                Reuses a persistent SSH connection per host (see Ensure SSH To VM).
    [Arguments]    ${vm_ip}    ${module}    ${target}    ${extra_args}=${EMPTY}
    Ensure SSH To VM    ${vm_ip}
    ${cmd}=    Set Variable
    ...    ${BBPROBE_REMOTE_PATH} --module ${module} --target ${target} --format json ${extra_args}
    ${stdout}    ${stderr}    ${rc}=    Execute Command    ${cmd}    return_stderr=True    return_rc=True
    ${status}    ${value}=    Run Keyword And Ignore Error    Evaluate    json.loads($stdout)    modules=json
    IF    '${status}' == 'FAIL'
        ${msg}=    Catenate
        ...    bbprobe produced non-JSON output for ${module} → ${target} (rc=${rc}): ${value}
        ...    | stdout: ${stdout}
        ...    | stderr: ${stderr}
        Fail    ${msg}
    END
    Log    bbprobe ${module} → ${target} (rc=${rc}): ${value['summary']}
    RETURN    ${value}    ${rc}

Get Probe Result
    [Documentation]    Return the parsed bbprobe result dict for custom assertions.
    [Arguments]    ${vm_ip}    ${module}    ${target}    ${extra_args}=${EMPTY}
    ${result}    ${rc}=    Run bbprobe    ${vm_ip}    ${module}    ${target}    ${extra_args}
    RETURN    ${result}

# ──────────────────────────────────────────────
# Assertions
# ──────────────────────────────────────────────

Probe Should Succeed
    [Documentation]    Assert bbprobe exits 0 and summary.probe_success == 1.
    [Arguments]    ${vm_ip}    ${module}    ${target}    ${extra_args}=${EMPTY}
    ${result}    ${rc}=    Run bbprobe    ${vm_ip}    ${module}    ${target}    ${extra_args}
    Should Be Equal As Integers    ${rc}    0    msg=bbprobe rc=${rc} for ${module} → ${target}
    Should Be Equal As Integers    ${result['summary']['probe_success']}    1
    ...    msg=probe_success != 1 for ${module} → ${target}
    Log    Probe ${module} → ${target} from ${vm_ip}: SUCCESS

Probe Should Fail
    [Documentation]    Assert the probe fails (summary.probe_success == 0). For deny/DFW tests.
    ...                Bounded with --deadline/--timeout so failure returns quickly.
    [Arguments]    ${vm_ip}    ${module}    ${target}    ${extra_args}=--deadline 6s --timeout 2s
    ${result}    ${rc}=    Run bbprobe    ${vm_ip}    ${module}    ${target}    ${extra_args}
    Should Be Equal As Integers    ${result['summary']['probe_success']}    0
    ...    msg=expected probe failure but it succeeded for ${module} → ${target}
    Log    Probe ${module} → ${target} from ${vm_ip}: FAILED as expected

Probe Latency Should Be Below
    [Documentation]    Assert the max probe latency is below max_seconds (seconds, float).
    [Arguments]    ${vm_ip}    ${module}    ${target}    ${max_seconds}=${PROBE_MAX_LATENCY}
    ${result}    ${rc}=    Run bbprobe    ${vm_ip}    ${module}    ${target}
    Should Be Equal As Integers    ${rc}    0    msg=bbprobe rc=${rc} for ${module} → ${target}
    ${latency}=    Set Variable    ${result['summary']['latency_seconds']['max']}
    Should Be True    ${latency} < ${max_seconds}
    ...    msg=latency ${latency}s exceeded threshold ${max_seconds}s for ${module} → ${target}
    Log    Probe ${module} → ${target} latency ${latency}s < ${max_seconds}s

# ──────────────────────────────────────────────
# Control-plane + data-plane correlation
# ──────────────────────────────────────────────

Service Data Plane Should Be Reachable
    [Documentation]    Wait for realization of the given intent paths, then assert the
    ...                data plane is reachable with a bbprobe from a VM. One keyword that
    ...                ties control-plane realization to data-plane connectivity.
    [Arguments]    ${vm_ip}    ${module}    ${target}    @{intent_paths}
    Wait For Realizations    @{intent_paths}
    Probe Should Succeed    ${vm_ip}    ${module}    ${target}
