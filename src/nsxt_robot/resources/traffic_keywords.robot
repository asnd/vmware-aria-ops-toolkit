*** Settings ***
Documentation    SSH-based traffic validation keywords using SSHLibrary.
...              Reachability checks (ping/tcp) delegate to the structured `bbprobe`
...              keywords; body-content checks (source IP, response body) stay on curl.
Library          Collections
Library          String
Library          SSHLibrary
Resource         ssh_keywords.robot
Resource         bbprobe_keywords.robot


*** Keywords ***
Run Command On VM
    [Documentation]    Execute a shell command on a VM via SSH and return stdout. Reuses a
    ...                persistent connection per host (see Ensure SSH To VM).
    [Arguments]    ${vm_ip}    ${command}
    Ensure SSH To VM    ${vm_ip}
    ${stdout}    ${stderr}    ${rc}=    Execute Command    ${command}    return_stderr=True    return_rc=True
    Log    CMD: ${command} | RC: ${rc} | OUT: ${stdout} | ERR: ${stderr}
    RETURN    ${stdout}    ${stderr}    ${rc}

Ping From VM
    [Documentation]    ICMP reachability from a VM. Delegates to bbprobe (icmp); passes if
    ...                at least one of ${count} attempts succeeds (mirrors "not 100% loss").
    [Arguments]    ${vm_ip}    ${dest_ip}    ${count}=3
    Probe Should Succeed    ${vm_ip}    icmp    ${dest_ip}    --repeat ${count} --min-success 1

Ping Should Fail From VM
    [Documentation]    Assert ICMP from a VM to a destination fails. Delegates to bbprobe.
    [Arguments]    ${vm_ip}    ${dest_ip}    ${count}=3
    Probe Should Fail    ${vm_ip}    icmp    ${dest_ip}    --repeat ${count} --deadline 6s --timeout 2s

Curl From VM
    [Documentation]    SSH to a VM and perform an HTTP request. Assert expected HTTP status code.
    [Arguments]    ${vm_ip}    ${url}    ${expected_code}=200    ${extra_args}=${EMPTY}
    ${stdout}    ${stderr}    ${rc}=    Run Command On VM
    ...    ${vm_ip}    curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 15 ${extra_args} ${url}
    Should Be Equal As Strings    ${stdout.strip()}    ${expected_code}
    Log    Curl from ${vm_ip} to ${url}: HTTP ${stdout.strip()}

TCP Connect From VM
    [Documentation]    Verify TCP connectivity to host:port. Delegates to bbprobe (tcp_connect).
    [Arguments]    ${vm_ip}    ${dest_ip}    ${port}    ${timeout}=5
    Probe Should Succeed    ${vm_ip}    tcp_connect    ${dest_ip}:${port}    --timeout ${timeout}s

Verify Overlay MTU From VM
    [Documentation]    Send a full-size, do-not-fragment ICMP packet from a VM to prove the
    ...    overlay path carries a complete inner frame without fragmenting it. ${payload}=1472
    ...    bytes + 28 (ICMP+IP headers) = a 1500-byte inner frame; the NSX TEP MTU (typically
    ...    1600) must absorb the encapsulation overhead. Stays on ping: bbprobe cannot set the
    ...    DF bit or payload size. Fails on packet loss or a "Frag needed"/"too long" response.
    [Arguments]    ${vm_ip}    ${dest_ip}    ${payload}=1472    ${count}=3
    ${stdout}    ${stderr}    ${rc}=    Run Command On VM
    ...    ${vm_ip}    ping -c ${count} -W 2 -M do -s ${payload} ${dest_ip}
    Should Be Equal As Integers    ${rc}    0
    ...    msg=DF-bit ping (${payload}B) ${vm_ip} → ${dest_ip} failed — overlay MTU too small or fragmenting
    Should Not Contain    ${stdout}    100% packet loss
    Should Not Contain Any    ${stdout}    Frag needed    Message too long
    Log    Overlay MTU OK: ${vm_ip} → ${dest_ip} passed a ${payload}B DF-bit ICMP

Verify Source IP From VM
    [Documentation]    Verify that traffic from a VM to dest_ip uses expected_src_ip as source.
    ...    Requires an HTTP reflector at dest_ip that echoes the client's IP (e.g., httpbin /ip).
    [Arguments]    ${vm_ip}    ${dest_ip}    ${expected_src_ip}    ${port}=80    ${path}=/ip
    ${stdout}    ${stderr}    ${rc}=    Run Command On VM
    ...    ${vm_ip}    curl -s --connect-timeout 10 --max-time 15 http://${dest_ip}:${port}${path}
    Should Contain    ${stdout}    ${expected_src_ip}
    Log    Source IP verification: expected ${expected_src_ip} found in response from ${dest_ip}

Verify HTTP Response From VM
    [Documentation]    Perform a full HTTP GET from a VM and assert the response body contains expected text.
    [Arguments]    ${vm_ip}    ${url}    ${expected_text}
    ${stdout}    ${stderr}    ${rc}=    Run Command On VM
    ...    ${vm_ip}    curl -s --connect-timeout 10 --max-time 15 ${url}
    Should Contain    ${stdout}    ${expected_text}
    Log    HTTP response from ${url} contains expected text: ${expected_text}
