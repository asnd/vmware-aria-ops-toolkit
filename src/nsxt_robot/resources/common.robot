*** Settings ***
Documentation    Common setup, teardown, and utility keywords shared across all test suites.
Library          Collections
Library          OperatingSystem
Library          String
Library          REST    ${NSX_BASE_URL}    ssl_verify=${VERIFY_SSL}
Library          nsxt_robot.NsxtApi


*** Variables ***
# Override to point at a mock/local NSX API (e.g. tests_mock/) — must be set before
# this file is parsed, since the Library import above resolves it at import time.
${NSX_BASE_URL}     https://${NSX_MANAGER}
${POLICY_BASE}      /policy/api/v1
${MGMT_BASE}        /api/v1
# Shared topology paths (previously redefined in every suite). Resolved from env.yaml.
${T0_PATH}          /infra/tier-0s/${T0_GATEWAY_ID}
${OVERLAY_TZ_PATH}  /infra/sites/default/enforcement-points/default/transport-zones/${OVERLAY_TZ_ID}
# Per-request timeout (seconds) for every NSX REST call below, so an unresponsive
# NSX Manager fails a keyword instead of hanging the suite indefinitely. Override
# in env.yaml if your fabric's realization-adjacent calls are legitimately slower.
${NSX_REQUEST_TIMEOUT}    30


*** Keywords ***
Initialize REST Session
    [Documentation]    Configure authentication headers on the shared RESTinstance session.
    ...                The password comes from the ${NSX_PASSWORD} variable (env.yaml) but the
    ...                NSX_PASSWORD environment variable, when set, wins — so CI can inject a
    ...                secret without a creds file on disk. Credential assembly runs with logging
    ...                suppressed so the password and the Basic-auth header never reach the log.
    # BuiltIn-qualified: RESTinstance also defines 'Set Log Level' (which controls only
    # its own logging), so an unqualified call would not suppress the Robot log.
    ${previous_level}=    BuiltIn.Set Log Level    NONE
    ${password}=    Set Variable    ${NSX_PASSWORD}
    ${env_password}=    Get Environment Variable    NSX_PASSWORD    ${EMPTY}
    IF    '${env_password}' != '${EMPTY}'
        ${password}=    Set Variable    ${env_password}
    END
    ${raw}=    Set Variable    ${NSX_USER}:${password}
    ${auth}=    Evaluate    base64.b64encode($raw.encode()).decode()    modules=base64
    Set Headers    {"Authorization": "Basic ${auth}", "Content-Type": "application/json", "Accept": "application/json"}
    BuiltIn.Set Log Level    ${previous_level}
    Log    REST auth headers configured for ${NSX_MANAGER}

NSX REST GET
    [Documentation]    Perform a GET request against the NSX API and return the parsed body.
    [Arguments]    ${path}
    GET    ${path}    timeout=${NSX_REQUEST_TIMEOUT}
    Integer    response status    200
    ${body}=    Output    response body
    RETURN    ${body}

NSX REST PATCH
    [Documentation]    Perform a PATCH request and return the parsed response body.
    [Arguments]    ${path}    ${body}
    PATCH    ${path}    ${body}    timeout=${NSX_REQUEST_TIMEOUT}
    Integer    response status    200
    ${resp_body}=    Output    response body
    RETURN    ${resp_body}

NSX REST POST
    [Documentation]    Perform a POST request (e.g. an action endpoint) and return the
    ...                parsed response body. Accepts 200 or 202 (action accepted/async).
    [Arguments]    ${path}    ${body}=${EMPTY}
    IF    '${body}' != '${EMPTY}'
        POST    ${path}    ${body}    timeout=${NSX_REQUEST_TIMEOUT}
    ELSE
        POST    ${path}    timeout=${NSX_REQUEST_TIMEOUT}
    END
    ${status}=    Output    response status
    Should Be True    ${status} in [200, 202]    msg=POST ${path} returned unexpected status: ${status}
    ${resp_body}=    Output    response body
    RETURN    ${resp_body}

NSX REST DELETE
    [Documentation]    Perform a DELETE request. Accepts 200 or 204 responses.
    [Arguments]    ${path}
    DELETE    ${path}    timeout=${NSX_REQUEST_TIMEOUT}
    ${status}=    Output    response status
    Should Be True    ${status} in [200, 204]    msg=DELETE ${path} returned unexpected status: ${status}
    RETURN    ${status}

NSX REST DELETE Ignore Error
    [Documentation]    DELETE that logs warnings but does not fail — for use in teardowns.
    [Arguments]    ${path}
    ${result}    ${value}=    Run Keyword And Ignore Error    NSX REST DELETE    ${path}
    IF    '${result}' == 'FAIL'
        Log    DELETE ${path} failed (ignored): ${value}    WARN
    END

Verify Realized
    [Documentation]    Assert the realization status for a Policy API intent path is SUCCESS.
    [Arguments]    ${intent_path}
    ${encoded}=    Evaluate    urllib.parse.quote($intent_path, safe='')    modules=urllib.parse
    ${body}=    NSX REST GET    ${POLICY_BASE}/infra/realized-state/status?intent_path=${encoded}
    Realized State Should Be Success    ${body}

Wait For Realization
    [Documentation]    Poll realization status up to 2 minutes until SUCCESS.
    [Arguments]    ${intent_path}
    Wait Until Keyword Succeeds    2 min    10 sec    Verify Realized    ${intent_path}

Wait For Realizations
    [Documentation]    Wait for realization of every intent path in the given list.
    [Arguments]    @{intent_paths}
    FOR    ${path}    IN    @{intent_paths}
        Wait For Realization    ${path}
    END

Standard Suite Teardown
    [Documentation]    Safe-delete a list of Policy API paths — replaces the per-suite
    ...                teardown blocks. Deletes in the given order (children first).
    [Arguments]    @{paths}
    FOR    ${path}    IN    @{paths}
        Safe Delete Policy Object    ${path}
    END

Safe Delete Policy Object
    [Documentation]    Delete a Policy API object, suppressing errors for teardown safety.
    [Arguments]    ${path}
    NSX REST DELETE Ignore Error    ${path}
