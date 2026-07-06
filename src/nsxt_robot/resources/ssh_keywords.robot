*** Settings ***
Documentation    SSH connection management for the test VMs. Connections are keyed by host
...              (alias = vm_ip) and reused across keywords, so a suite that runs many
...              commands/probes against a VM pays the TCP + auth cost only once. The VM
...              password prefers the VM_PASSWORD environment variable (CI secret injection)
...              over the ${VM_PASSWORD} suite variable, and is never logged.
Library          OperatingSystem
Library          SSHLibrary


*** Variables ***
${SSH_TIMEOUT}      30s
${SSH_PROMPT}       $
${VM_SSH_PORT}      22


*** Keywords ***
Get VM SSH Password
    [Documentation]    Return the VM SSH password, preferring the VM_PASSWORD environment
    ...                variable (for CI secret injection) over the ${VM_PASSWORD} variable.
    ${env_password}=    Get Environment Variable    VM_PASSWORD    ${EMPTY}
    IF    '${env_password}' != '${EMPTY}'
        RETURN    ${env_password}
    END
    RETURN    ${VM_PASSWORD}

Ensure SSH To VM
    [Documentation]    Return a live SSH connection to ${vm_ip}, reusing an existing one when
    ...                present (alias = vm_ip). Opens + logs in only on the first call per host,
    ...                so a suite that probes a VM many times pays the TCP/auth cost once.
    [Arguments]    ${vm_ip}
    ${status}=    Run Keyword And Return Status    Switch Connection    ${vm_ip}
    IF    ${status}
        RETURN
    END
    Open Connection    ${vm_ip}    alias=${vm_ip}    port=${VM_SSH_PORT}
    ...    timeout=${SSH_TIMEOUT}    prompt=${SSH_PROMPT}
    # Fetch the password and log in with logging suppressed so neither the
    # password value nor the assignment reaches the Robot log. BuiltIn-qualified
    # for consistency with common.robot (where REST also defines Set Log Level).
    ${previous_level}=    BuiltIn.Set Log Level    NONE
    ${password}=    Get VM SSH Password
    Login    ${VM_USER}    ${password}
    BuiltIn.Set Log Level    ${previous_level}
    Log    SSH connected to ${vm_ip}:${VM_SSH_PORT}

Open SSH To VM
    [Documentation]    Ensure a (reused) SSH connection to a test VM. Retained for backward
    ...                compatibility; delegates to Ensure SSH To VM.
    [Arguments]    ${vm_ip}
    Ensure SSH To VM    ${vm_ip}

Close SSH From VM
    [Documentation]    Close the active SSH connection. Prefer Close All VM Connections in
    ...                suite teardown when connections are reused across tests.
    Close Connection

Close All VM Connections
    [Documentation]    Close every open SSH connection. Use in suite teardown to release the
    ...                connections opened by Ensure SSH To VM.
    Close All Connections
