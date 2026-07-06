*** Settings ***
Documentation    Provisioning suite: copy the bbprobe binary to the test VMs before any
...              data-plane tests run. Ordered first via the `00_` directory prefix.
Resource         nsxt_robot/resources/bbprobe_keywords.robot
Test Tags        provision


*** Test Cases ***
Deploy bbprobe To Test VMs
    [Documentation]    SCP the bbprobe binary to every test VM, make it executable, confirm
    ...                `bbprobe --version` runs, and enable unprivileged ICMP. This must pass
    ...                before the traffic-dependent suites (T1, static routing, SNAT, ALB).
    [Tags]    provision    bbprobe
    Deploy bbprobe To All Test VMs

Verify bbprobe Is Runnable On VM1
    [Documentation]    Sanity probe: run a loopback ICMP check on VM1 and confirm the JSON
    ...                result parses and reports success — proving the binary works end to end.
    [Tags]    provision    bbprobe    smoke
    Probe Should Succeed    ${VM1_IP}    icmp    127.0.0.1
