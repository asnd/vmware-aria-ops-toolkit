"""Unit tests for nsxt_robot.bbprobe_release (run with pytest)."""

import hashlib

import pytest

from nsxt_robot import BbprobeRelease
from nsxt_robot.bbprobe_release import _asset_suffix, _parse_sha256sums, _sha256_of


@pytest.fixture
def release():
    return BbprobeRelease()


# ── asset name resolution ─────────────────────────────────────────────────────


def test_asset_suffix_linux_amd64():
    assert _asset_suffix("Linux", "x86_64") == "linux-amd64"


def test_asset_suffix_darwin_arm64():
    assert _asset_suffix("Linux", "x86_64") == "linux-amd64"
    assert _asset_suffix("Darwin", "arm64") == "darwin-arm64"


def test_asset_suffix_strips_whitespace():
    assert _asset_suffix("Linux\n", " x86_64\n") == "linux-amd64"


def test_asset_suffix_unsupported_platform_raises():
    with pytest.raises(AssertionError, match="No published bbprobe release asset"):
        _asset_suffix("Windows_NT", "AMD64")


def test_get_asset_name(release):
    assert release.get_asset_name("v0.9.0", "Linux", "x86_64") == "bbprobe-v0.9.0-linux-amd64"


# ── SHA256SUMS parsing ────────────────────────────────────────────────────────


def test_parse_sha256sums_finds_entry():
    text = (
        "aaaa111  bbprobe-v0.9.0-linux-amd64\n"
        "bbbb222  bbprobe-v0.9.0-darwin-arm64\n"
    )
    assert _parse_sha256sums(text, "bbprobe-v0.9.0-darwin-arm64") == "bbbb222"


def test_parse_sha256sums_handles_binary_mode_star_prefix():
    text = "cccc333 *bbprobe-v0.9.0-linux-386\n"
    assert _parse_sha256sums(text, "bbprobe-v0.9.0-linux-386") == "cccc333"


def test_parse_sha256sums_missing_entry_raises():
    with pytest.raises(AssertionError, match="No checksum entry"):
        _parse_sha256sums("aaaa111  other-file\n", "bbprobe-v0.9.0-linux-amd64")


def test_parse_sha256sums_ignores_blank_lines():
    text = "\n\naaaa111  bbprobe-v0.9.0-linux-amd64\n\n"
    assert _parse_sha256sums(text, "bbprobe-v0.9.0-linux-amd64") == "aaaa111"


# ── file hashing ──────────────────────────────────────────────────────────────


def test_sha256_of_matches_hashlib(tmp_path):
    f = tmp_path / "binary"
    f.write_bytes(b"pretend-bbprobe-binary-contents")
    assert _sha256_of(f) == hashlib.sha256(b"pretend-bbprobe-binary-contents").hexdigest()


# ── download + cache ──────────────────────────────────────────────────────────


def test_ensure_binary_cached_returns_existing_without_download(release, tmp_path, monkeypatch):
    cached = tmp_path / "v0.9.0" / "bbprobe-v0.9.0-linux-amd64"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"already-cached")

    def fail(*a, **k):
        raise AssertionError("should not hit the network on a cache hit")

    monkeypatch.setattr("nsxt_robot.bbprobe_release.urllib.request.urlopen", fail)
    monkeypatch.setattr("nsxt_robot.bbprobe_release.urllib.request.urlretrieve", fail)

    result = release.ensure_binary_is_cached(
        "v0.9.0", "bbprobe-v0.9.0-linux-amd64", str(tmp_path)
    )
    assert result == str(cached)


def test_ensure_binary_cached_downloads_and_verifies(release, tmp_path, monkeypatch):
    content = b"the-real-binary-bytes"
    digest = hashlib.sha256(content).hexdigest()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return f"{digest}  bbprobe-v0.9.0-linux-amd64\n".encode()

    def fake_urlopen(url, timeout=30):
        assert url.endswith("/SHA256SUMS")
        return FakeResponse()

    def fake_urlretrieve(url, dest):
        assert url.endswith("bbprobe-v0.9.0-linux-amd64")
        with open(dest, "wb") as f:
            f.write(content)

    monkeypatch.setattr("nsxt_robot.bbprobe_release.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("nsxt_robot.bbprobe_release.urllib.request.urlretrieve", fake_urlretrieve)

    result = release.ensure_binary_is_cached(
        "v0.9.0", "bbprobe-v0.9.0-linux-amd64", str(tmp_path)
    )
    assert result == str(tmp_path / "v0.9.0" / "bbprobe-v0.9.0-linux-amd64")
    assert open(result, "rb").read() == content


def test_ensure_binary_cached_checksum_mismatch_raises_and_no_stale_file(release, tmp_path, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"deadbeef  bbprobe-v0.9.0-linux-amd64\n"

    def fake_urlopen(url, timeout=30):
        return FakeResponse()

    def fake_urlretrieve(url, dest):
        with open(dest, "wb") as f:
            f.write(b"corrupted-or-tampered-bytes")

    monkeypatch.setattr("nsxt_robot.bbprobe_release.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("nsxt_robot.bbprobe_release.urllib.request.urlretrieve", fake_urlretrieve)

    with pytest.raises(AssertionError, match="Checksum mismatch"):
        release.ensure_binary_is_cached("v0.9.0", "bbprobe-v0.9.0-linux-amd64", str(tmp_path))

    cache_path = tmp_path / "v0.9.0" / "bbprobe-v0.9.0-linux-amd64"
    assert not cache_path.exists()
    assert not cache_path.with_name(cache_path.name + ".part").exists()
