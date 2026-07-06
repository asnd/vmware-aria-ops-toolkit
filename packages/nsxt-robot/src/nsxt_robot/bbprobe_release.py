"""Resolve, download, and checksum-verify bbprobe release binaries.

bbprobe runs on the test VM being probed — a possibly different OS/architecture than
the control host running Robot — so the binary is fetched per target arch from tagged
GitHub releases (https://github.com/asnd/bbprobe/releases) rather than bundled into
this package's own wheel (which would only match the one arch it happened to be built
on). Downloads are checksum-verified against the release's published ``SHA256SUMS``
and cached locally by version, so repeat deployments don't re-fetch. Pure Python, no
third-party dependencies.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from robot.api.deco import keyword, library

#: Maps (uname -s, uname -m) on the target VM to bbprobe's published release asset
#: suffixes. Extend this when bbprobe publishes a new platform's binary.
_ASSET_SUFFIXES = {
    ("Linux", "x86_64"): "linux-amd64",
    ("Linux", "i686"): "linux-386",
    ("Linux", "i386"): "linux-386",
    ("Darwin", "arm64"): "darwin-arm64",
}


def _asset_suffix(uname_s: str, uname_m: str) -> str:
    key = (uname_s.strip(), uname_m.strip())
    if key not in _ASSET_SUFFIXES:
        supported = ", ".join(f"{s}/{m}" for s, m in _ASSET_SUFFIXES)
        raise AssertionError(
            f"No published bbprobe release asset for uname -s='{uname_s}' -m='{uname_m}'. "
            f"Supported target platforms (uname -s/uname -m): {supported}"
        )
    return _ASSET_SUFFIXES[key]


def _parse_sha256sums(text: str, asset_name: str) -> str:
    """Return the expected sha256 digest for ``asset_name`` from a SHA256SUMS body."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, name = parts
        if name.lstrip("*") == asset_name:
            return digest
    raise AssertionError(f"No checksum entry for '{asset_name}' in SHA256SUMS")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


@library(scope="GLOBAL", auto_keywords=False)
class BbprobeRelease:
    """Resolve/download/verify bbprobe release binaries for a test VM's architecture."""

    ROBOT_LIBRARY_VERSION = "1.0.0"

    @keyword("Get bbprobe Asset Name")
    def get_asset_name(self, version: str, uname_s: str, uname_m: str) -> str:
        """Return the release asset filename for ``version`` matching a VM's ``uname``.

        ``version`` is a bbprobe tag (e.g. ``v0.9.0``); ``uname_s``/``uname_m`` are the
        raw output of ``uname -s``/``uname -m`` run on the target VM.
        """
        return f"bbprobe-{version}-{_asset_suffix(uname_s, uname_m)}"

    @keyword("Ensure bbprobe Binary Is Cached")
    def ensure_binary_is_cached(
        self,
        version: str,
        asset_name: str,
        cache_dir: str,
        base_url: str = "https://github.com/asnd/bbprobe/releases/download",
    ) -> str:
        """Return a local path to ``asset_name``, downloading it on first use.

        Fetches ``SHA256SUMS`` from the same release and verifies the downloaded
        binary against it before caching — an integrity check, not just a courtesy,
        since this binary is about to be SCP'd to a test VM and executed there.
        Subsequent calls for the same ``version``/``asset_name`` reuse the cached,
        already-verified file without re-downloading.
        """
        cache_path = Path(cache_dir) / version / asset_name
        if cache_path.exists():
            return str(cache_path)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        release_url = f"{base_url}/{version}"

        with urllib.request.urlopen(f"{release_url}/SHA256SUMS", timeout=30) as resp:
            sums_text = resp.read().decode()
        expected = _parse_sha256sums(sums_text, asset_name)

        tmp_path = cache_path.with_name(cache_path.name + ".part")
        try:
            urllib.request.urlretrieve(f"{release_url}/{asset_name}", tmp_path)  # noqa: S310
            actual = _sha256_of(tmp_path)
            if actual != expected:
                raise AssertionError(
                    f"Checksum mismatch for {asset_name} ({version}): "
                    f"expected {expected}, got {actual}"
                )
            tmp_path.rename(cache_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        return str(cache_path)
