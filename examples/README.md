# Examples

Small, self-contained Robot suites showing how to use `nsxt_robot` as a library —
copy one as a starting point for your own suite. These are separate from `tests/`,
which is the maintainer's own acceptance suite: `tests/` builds shared topology
across numbered suites and is tuned to one specific lab, while each file here
stands on its own (its own topology, its own teardown) and favors readability
over exhaustive coverage.

Each example is **live-runnable** against a real NSX-T + test-VM environment,
exactly like `tests/` — configure `env.yaml` first (see the main
[README](../README.md#configure)), then:

```sh
robot -d results -V env.yaml examples/01_load_balancer_service/
```

| Example | Demonstrates |
|---|---|
| [`01_load_balancer_service`](01_load_balancer_service/load_balancer_service.robot) | Standing up an NSX network **service** (L4 load balancer) and proving it works with real traffic — the general pattern for testing any NSX service (LB, NAT, ...). |
| [`02_t1_gateway_firewall`](02_t1_gateway_firewall/t1_gateway_firewall.robot) | **Gateway Firewall** (T1 edge/perimeter firewall) — distinct from the distributed firewall (DFW) covered in `tests/08_dfw`: enforced at the gateway edge via `gateway-policies`, not per-vNIC. |
| [`03_t0_vrf_bgp_bfd`](03_t0_vrf_bgp_bfd/t0_vrf_bgp_bfd.robot) | **BGP + BFD peering on a Tier-0 VRF** — the same `... On T0` BGP/BFD keywords used against a standalone T0 work unchanged against a VRF, aside from ASN inheritance. |

A structure check without touching the lab (no keywords execute):

```sh
robot --dryrun -V env.example.yaml examples/
```
