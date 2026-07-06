# robotframework-nsxt

A reusable **Robot Framework library for testing VMware NSX-T 4.x**, plus an
acceptance-test suite that uses it. The library drives the **control plane** via the
NSX Policy/Management REST API (RESTinstance) and validates the **data plane** from test
VMs using [`bbprobe`](https://github.com/asnd/bbprobe) — a single-shot, agentless network
probe that emits parseable JSON over SSH.

- **Distribution:** `robotframework-nsxt` · **import name:** `nsxt_robot`
- Ships a Python keyword library (`nsxt_robot.NsxtApi`) and six `.robot` resource files
  under `nsxt_robot/resources/`, importable from any suite once installed.

## Layout

```
nsxt-robot/
├── pyproject.toml               # packaging (hatchling), deps, ruff/mypy/robocop config
├── env.example.yaml             # copy to env.yaml and edit (env.yaml is gitignored)
├── src/nsxt_robot/
│   ├── __init__.py              # exports NsxtApi, __version__
│   ├── api.py                   # NsxtApi: JSON extraction + typed status assertions
│   └── resources/
│       ├── common.robot         # REST session, realization polling, shared vars, teardown
│       ├── policy_api.robot     # NSX Policy/Mgmt API operations (T1/segment/BGP/NAT/LB/DFW/Gateway FW/…)
│       ├── ssh_keywords.robot   # pooled SSH connection management (reused per host)
│       ├── traffic_keywords.robot  # SSH traffic keywords (reachability delegates to bbprobe)
│       ├── bbprobe_keywords.robot  # deploy + run bbprobe; structured probe assertions
│       └── failure_keywords.robot  # fault injection: segment/BGP/edge-node + convergence asserts
├── tests_unit/                  # pytest unit tests for NsxtApi/BbprobeRelease (pure Python)
├── tests_mock/                  # contract tests: keyword wiring vs. an in-process mock NSX API
├── scripts/gen_docs.sh          # generate libdoc keyword docs into docs/
├── tests/                       # Robot acceptance suites (consume the library)
│   ├── 00_provision/            # deploy bbprobe to the VMs (runs first)
│   ├── 01_infra/  02_t1_connectivity/  03_static_routing/
│   ├── 04_bgp_bfd/  05_ha_vip/  06_snat/  (SNAT + DNAT)  07_alb_l4/
│   ├── 08_dfw/                  # distributed firewall micro-segmentation (groups, tags, allow/deny)
│   ├── 09_alb_l7/               # L7 HTTP load balancer + active health monitor
│   ├── 10_t0_vrf/               # T0-VRF gateway: uplink interface, static routing, BFD, BGP, EVPN
│   └── 11_failover/             # fault injection: segment/BGP/edge-node failures + recovery SLA
└── examples/                    # small, self-contained suites to copy as a starting point
    ├── 01_load_balancer_service/
    ├── 02_t1_gateway_firewall/
    └── 03_t0_vrf_bgp_bfd/
```

Service coverage: infra health, T1 connectivity, static routing, BGP/BFD, HA VIP,
NAT (SNAT + DNAT), L4 + L7 load balancing with health monitors, distributed firewall
micro-segmentation (IP + dynamic tag groups, allow/deny enforcement), Gateway Firewall
(centralized T0/T1 edge firewall, distinct from DFW), Tier-0 VRF gateways (VRF-lite and
EVPN: external interfaces, VRF static routing with BFD-protected next hops, VRF BGP,
RD/RT/transit-VNI), and fault injection with recovery-SLA assertions (segment/BGP/edge-node
failures). Data-plane assertions include reachability, latency SLA, deny-path verification,
and overlay MTU.

See [`examples/`](examples/) for copyable, focused suites covering NSX service testing
(load balancing), Gateway Firewall, and T0-VRF BGP/BFD.

## Install

```sh
uv venv && uv pip install -e ".[dev]"      # this repo (editable, with dev tools)
# or, as a dependency of your own test project:
uv pip install robotframework-nsxt          # (once published) or: uv pip install <path-or-git-url>
```

Then import the keywords from any suite:

```robotframework
*** Settings ***
Library     nsxt_robot.NsxtApi
Resource    nsxt_robot/resources/common.robot
Resource    nsxt_robot/resources/policy_api.robot
Resource    nsxt_robot/resources/traffic_keywords.robot
```

## Configure

```sh
cp env.example.yaml env.yaml    # then edit (env.yaml is gitignored)
```

- Fill in your NSX Manager, test-VM IPs, and per-service values (all `10.x.x.x` / `xxx`
  placeholders). **Credentials:** `NSX_PASSWORD` / `VM_PASSWORD` in `env.yaml` are used by
  default, but the `NSX_PASSWORD` / `VM_PASSWORD` **environment variables win when set**, so
  CI can inject secrets without a creds file on disk. Passwords are never logged.
- Two Linux test VMs reachable over SSH (`VM1_IP`, `VM2_IP`); override `VM_SSH_PORT`
  (default `22`) and `@{TEST_VM_IPS}` to change the port or the set of probed hosts.
- The **bbprobe binary**: by default, no setup needed — `deploy_bbprobe.robot` detects
  each test VM's own architecture over SSH and downloads + checksum-verifies the pinned
  `BBPROBE_VERSION` release from [asnd/bbprobe](https://github.com/asnd/bbprobe/releases),
  caching it under `~/.cache/nsxt-robot/bbprobe/`. To use a custom or offline/air-gapped
  build instead, set an absolute `BBPROBE_LOCAL_PATH` and it's used as-is, skipping the
  download.

## Running

```sh
# everything, with the environment file
robot -d results -V env.yaml tests/

# a single service area by tag
robot -d results -V env.yaml -i t1 tests/
robot -d results -V env.yaml -i bgp tests/

# structure check without touching the lab (no keywords execute)
robot --dryrun -V env.example.yaml tests/
```

The `00_provision` suite deploys bbprobe and must run before the traffic-dependent
suites (it is ordered first by the `00_` prefix, so a full `tests/` run is correct).

## bbprobe deployment (data plane)

`tests/00_provision/deploy_bbprobe.robot` copies the binary to every VM before any
traffic test runs. It uses the keywords in `nsxt_robot/resources/bbprobe_keywords.robot`:

- **`Deploy bbprobe To VM  ${vm_ip}`** — resolves a local bbprobe binary for the VM
  (see below), SCPs it to `${BBPROBE_REMOTE_PATH}` (`/usr/local/bin/bbprobe`) via
  SSHLibrary `Put File` (`mode=0755`), runs `bbprobe --version` to confirm it works,
  and grants unprivileged ICMP.
- **`Deploy bbprobe To All Test VMs`** — loops every host in `@{TEST_VM_IPS}`
  (default `VM1_IP`, `VM2_IP`; override to cover any number of VMs).
- **`Resolve bbprobe Binary For VM  ${vm_ip}`** — if `${BBPROBE_LOCAL_PATH}` is set,
  returns it as-is (custom/offline build). Otherwise runs `uname -s`/`uname -m` on the
  VM over the existing SSH connection, resolves the matching release asset name via
  `nsxt_robot.BbprobeRelease`'s `Get bbprobe Asset Name` keyword, and downloads +
  checksum-verifies it with `Ensure bbprobe Binary Is Cached` — checked against the
  release's published `SHA256SUMS` before it's ever SCP'd to a VM and executed there.
  Cached locally under `${BBPROBE_CACHE_DIR}` (default `~/.cache/nsxt-robot/bbprobe/`)
  keyed by `${BBPROBE_VERSION}`, so repeat deploys don't re-download. Only Linux
  amd64/386 and Darwin arm64 have published bbprobe releases today; deploying to any
  other target architecture requires `${BBPROBE_LOCAL_PATH}`.

### ICMP without root

The ICMP probe needs raw-socket capability. The deploy keyword applies one of
these on the VM automatically (VM_USER is root); if you provision the VMs
yourself, set one of:

```sh
setcap cap_net_raw+ep /usr/local/bin/bbprobe                 # per-binary
# or
sysctl -w net.ipv4.ping_group_range="0 2147483647"           # system-wide
```

## Probe keywords (`nsxt_robot/resources/bbprobe_keywords.robot`)

| Keyword | Purpose |
|---------|---------|
| `Run bbprobe  vm  module  target  [extra_args]` | Run a probe, return the parsed JSON dict + exit code |
| `Probe Should Succeed  vm  module  target` | Assert exit 0 and `summary.probe_success == 1` |
| `Probe Should Fail  vm  module  target` | Assert failure (for deny/DFW tests); bounded by `--deadline`/`--timeout` |
| `Probe Latency Should Be Below  vm  module  target  [max_s]` | Assert `summary.latency_seconds.max < max_s` |
| `Get Probe Result  vm  module  target` | Return the dict for custom assertions |
| `Service Data Plane Should Be Reachable  vm  module  target  @paths` | Wait for realization of `paths`, then probe |

`bbprobe` modules used: `icmp`, `tcp_connect` (target `host:port`), `http_2xx`.
The reachability keywords in `traffic_keywords.robot` (`Ping From VM`,
`TCP Connect From VM`, …) delegate to these. Three checks stay on shell tools because
bbprobe cannot express them: `Verify Source IP From VM` / `Verify HTTP Response From VM`
assert on the HTTP response **body** (curl), and `Verify Overlay MTU From VM` sends a
full-size **DF-bit** ICMP packet (`ping -M do -s`) to validate the overlay carries a
1500-byte inner frame without fragmenting.

## NSX-T API keywords (`nsxt_robot.NsxtApi`)

Used alongside RESTinstance — the `policy_api.robot` getters return bodies; these
keywords parse and assert on them, replacing `Get From Dictionary` chains and
`Evaluate next(...)`.

| Keyword | Purpose |
|---------|---------|
| `Get Value  data  path` | Dotted/indexed lookup, e.g. `members.0.status` |
| `Find In List  items  key  value` | First dict where `item[key] == value` (accepts a `results` body) |
| `Get Ids  list_body` | List of `id`/`display_name` for every item |
| `Realized State Should Be Success  body` | Assert realization consolidated status is SUCCESS |
| `Manager Cluster Should Be Stable  status` | Assert cluster status STABLE |
| `Compute Manager Should Be Registered  cm_status` | Assert REGISTERED |
| `BGP Neighbor Should Be Established  status` | Assert BGP connection_state ESTABLISHED |
| `BFD Should Be Healthy  status` | Assert BFD diagnostic code 0 |
| `Pool Member Should Be Up  pool_status` | Assert every LB pool member is UP |
| `NAT Rule Should Exist  rules  rule_id  [action]  [translated]` | Assert a NAT rule (SNAT/DNAT) exists with the expected fields |
| `DFW Rule Should Have Action  rules  rule_id  action` | Assert a DFW rule exists with ALLOW/DROP/REJECT |
| `Gateway Firewall Rule Should Have Action  rules  rule_id  action` | Assert a Gateway Firewall rule exists with ALLOW/DROP/REJECT |
| `Group Should Have Member  members  ip_or_name` | Assert a group's effective members include a VM by IP or name |

## Gateway Firewall vs DFW (`policy_api.robot`)

Two different firewalls live in the Policy API and this library covers both:

| | DFW (`tests/08_dfw`) | Gateway Firewall (`examples/02_t1_gateway_firewall`) |
|---|---|---|
| Enforcement point | Distributed — at the vNIC | Centralized — at the T0/T1 edge |
| Endpoint | `/infra/domains/{domain}/security-policies` | `/infra/domains/{domain}/gateway-policies` |
| Scope | Domain-wide, matched by group membership | Per-rule `scope`: the specific T0/T1 gateway path it applies to |
| Keywords | `Create Security Policy` / `Create DFW Rule` / `Get DFW Rules` / `Delete DFW Rule` / `Delete Security Policy` | `Create Gateway Firewall Policy` / `Create Gateway Firewall Rule` / `Get Gateway Firewall Rules` / `Delete Gateway Firewall Rule` / `Delete Gateway Firewall Policy` |

Gateway Firewall rule/policy `category` naming (e.g. `LocalGatewayRules`, the default here)
is version-sensitive across NSX releases, like EVPN below — verify against your release's
API reference on the first live run.

## T0-VRF and EVPN (`policy_api.robot` + `tests/10_t0_vrf`)

A T0-VRF is itself a tier-0 object, so every `... On T0` keyword (BGP, static routes,
interfaces, locale services) works against a VRF's ID unchanged. On top of that:

- `Create VRF Gateway On T0` — VRF-lite by default; optional `route_distinguisher`,
  `import_rts`/`export_rts` (L2VPN_EVPN route targets), and `evpn_transit_vni` for EVPN.
- `Create T0 Locale Service` / `Create T0 External Interface` — uplinks on VLAN segments
  (`Create VLAN Segment`), pinned to an edge node via `Get Edge Nodes In Cluster`.
- `Create Static Route On T0` + `Create BFD Profile` + `Create Static Route BFD Peer On T0`
  — VRF static routing with BFD-withdrawn next hops.
- `Enable BGP On T0 Locale Service` — for VRFs, which inherit the parent's ASN
  (use `Configure BGP On T0` only on the parent/standalone T0).
- `Create VNI Pool` / `Configure EVPN On T0` / `Create EVPN Tunnel Endpoint On T0` —
  EVPN INLINE / ROUTE_SERVER enablement on the parent T0.

The `tests/10_t0_vrf` suite runs the full lifecycle; its `evpn`-tagged tests mutate the
**parent** T0 (EVPN mode persists after teardown) — exclude them with `-e evpn` on
fabrics without EVPN. EVPN field names follow the NSX 4.x schemas and are the most
version-sensitive part of the Policy API; verify against your release's API reference
on the first live run.

## Failure simulation (`failure_keywords.robot` + `tests/11_failover`)

Resilience testing needs to *inject* failures, not just verify positive-path config. Every
injection keyword has a paired restore keyword, and convergence is measured from the data
plane with the existing bbprobe keywords via `Data Plane Should Recover Within` /
`Data Plane Should Be Down Within`.

| Failure | Keyword(s) | Restore |
|---|---|---|
| Segment (or T0/T0-VRF uplink — its backing VLAN segment) | `Fail Segment` | `Restore Segment` |
| BGP session (T0 or T0-VRF) | `Disable BGP On T0 Locale Service` | `Enable BGP On T0 Locale Service` (policy_api.robot) |
| BGP neighbor | `Delete BGP Neighbor On T0` (policy_api.robot) | `Create BGP Neighbor On T0` |
| Edge node drain/failover | `Enter Edge Maintenance Mode` | `Exit Edge Maintenance Mode` |
| Edge node hard failure (**destructive**) | `Restart Edge Dataplane`, `Reboot Edge Node` | recovers on its own; assert with `Data Plane Should Recover Within` |

`Restart Edge Dataplane` and `Reboot Edge Node` SSH into the edge CLI and cause a real
outage — they run only when `${EDGE_PASSWORD}` is set (empty by default, unlike
`NSX_PASSWORD`/`VM_PASSWORD`, so they're opt-in) and are tagged `destructive` for
wholesale exclusion with `-e destructive`. The edge maintenance-mode failover test is
tagged `ha` and needs ≥2 edges in `${EDGE_CLUSTER_ID}` (exclude with `-e ha` on a
single-edge lab). There is no API-level "power off a T0/T0-VRF" — its failure is
represented by its uplink path (segment admin-down) and by the edge node carrying it,
which is also what fails in production.

## Contract tests (`tests_mock/`)

`tests_unit/` only covers pure-Python logic (`NsxtApi`, `BbprobeRelease`) — it can't
verify that a keyword like `Create T1 Gateway` in `policy_api.robot` actually builds
the right HTTP method/path/JSON body, since that construction happens in Robot syntax,
not Python. `tests_mock/` runs the real keywords for real against
`mock_nsx_server.py`, a tiny in-process, stdlib-only HTTP server that records every
request and echoes PATCH bodies back on a matching GET (mirroring how NSX's Policy API
returns the object you just wrote). This catches body-shape regressions — a wrong
field name, an optional argument leaking into the body when it shouldn't — that a
`--dryrun` (structure/imports only) run cannot, without needing a live NSX Manager:

```sh
robot -V env.example.yaml -d results tests_mock/
```

The mock listens on a fixed port (`tests_mock/policy_api_contract.robot`'s
`${NSX_BASE_URL}`) rather than an OS-assigned one, because the `Library REST` import
in `common.robot` resolves that URL at parse time — before any Suite Setup runs — and
Robot Framework silently ignores a later `Import Library REST ...` with different
arguments for an already-imported library.

## Keyword docs

Generate browsable HTML keyword docs (libdoc) for `NsxtApi` and each resource file:

```sh
scripts/gen_docs.sh          # writes docs/*.html (gitignored)
```

## Development checks

The same gates run in CI (`.github/workflows/ci.yml`):

```sh
uv run ruff check .                          # lint Python
uv run mypy src/                             # type-check the library
uv run pytest -q                             # NsxtApi/BbprobeRelease unit tests (tests_unit/)
uv run robocop check src/ tests/ examples/ tests_mock/        # lint the Robot code
uv run robot --dryrun -V env.example.yaml tests/ examples/    # all keywords/imports resolve
uv run robot -V env.example.yaml tests_mock/                  # contract tests (real run vs. a mock)
uv build                                     # wheel + sdist in dist/
```

See [`CHANGELOG.md`](CHANGELOG.md) for what's changed.
