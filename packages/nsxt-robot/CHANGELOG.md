# Changelog

All notable changes to `robotframework-nsxt` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project has not yet
made a first release, so versions below are tracked as `[Unreleased]` until the
first tag is cut.

## [Unreleased]

### Added
- `tests_mock/`: contract tests that run real Policy API keywords against an
  in-process mock NSX server, verifying the actual HTTP method/path/JSON body each
  keyword sends — coverage `tests_unit/`'s pure-Python tests can't provide, since
  request-body construction happens in Robot syntax, not Python.
- `nsxt_robot.BbprobeRelease`: resolves each test VM's own architecture over SSH and
  downloads + checksum-verifies the matching `bbprobe` release binary, caching it
  under `~/.cache/nsxt-robot/bbprobe/`. `BBPROBE_LOCAL_PATH` remains as an explicit
  override for custom/offline/air-gapped builds.
- Gateway Firewall keywords (`Create/Delete Gateway Firewall Policy`,
  `Create/Get/Delete Gateway Firewall Rule`) wrapping NSX's `gateway-policies` API —
  the centralized T0/T1 edge firewall, distinct from the existing distributed DFW.
- `examples/`: three copyable, self-contained, live-runnable suites (NSX load-balancer
  service, T1 Gateway Firewall, T0-VRF BGP/BFD) for consumers to use as a starting point.
- `py.typed` marker so consumers can type-check against this package.
- `${NSX_REQUEST_TIMEOUT}` (30s default) applied to every NSX REST call, so an
  unresponsive NSX Manager fails a keyword instead of hanging the suite indefinitely.
- CI now runs the full gate matrix against Python 3.11 and 3.12.

### Changed
- `pyproject.toml` now sources its version from `nsxt_robot/__init__.py` (single
  source of truth) instead of duplicating the version string.
- Non-JSON `bbprobe` output now raises a clear error with stdout/stderr/rc instead of
  a raw `JSONDecodeError`.
- `scripts/gen_docs.sh` now uses `uv run python` and generates docs for
  `failure_keywords.robot` and `BbprobeRelease` (both previously missing).

### Fixed
- README/`env.example.yaml` no longer point at the private, inaccessible
  `blackbox-ssh` sibling repo for building `bbprobe`.

## Earlier history

Predates this changelog. See `git log` for full detail; summary:

- Distributed firewall (DFW) micro-segmentation, NAT (SNAT/DNAT), L4/L7 load
  balancing with health monitors.
- Tier-0 VRF gateways (VRF-lite and EVPN): external interfaces, VRF static routing
  with BFD-protected next hops, VRF BGP, RD/RT/transit-VNI.
- Fault-injection keywords for segment/BGP/edge-node failures with recovery-SLA
  assertions.
- Initial packaging as the `robotframework-nsxt` library (MIT license, PyPI
  trusted-publishing workflow).
