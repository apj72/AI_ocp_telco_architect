from __future__ import annotations

import httpx

# Known OCP GA dates and EOL (maintenance support end = 18 months after GA)
# Source: https://access.redhat.com/support/policy/updates/openshift
# EUS = even-numbered minor releases (4.12, 4.14, 4.16, ...)
_LIFECYCLE = {
    "4.12": {"ga": "2023-01-17", "eol": "2024-07-17"},
    "4.13": {"ga": "2023-05-17", "eol": "2024-11-17"},
    "4.14": {"ga": "2023-10-31", "eol": "2025-04-30"},
    "4.15": {"ga": "2024-02-27", "eol": "2025-08-27"},
    "4.16": {"ga": "2024-06-27", "eol": "2025-12-27"},
    "4.17": {"ga": "2024-10-02", "eol": "2026-04-02"},
    "4.18": {"ga": "2025-02-12", "eol": "2026-08-12"},
    "4.19": {"ga": "2025-06-25", "eol": "2026-12-25"},
    "4.20": {"ga": "2025-10-21", "eol": "2027-04-21"},
    "4.21": {"ga": "2026-02-03", "eol": "2027-08-03"},
    "4.22": {"ga": "2026-06-09", "eol": "2027-12-09"},
}

_GRAPH_URL = "https://api.openshift.com/api/upgrades_info/v1/graph"


def _is_eus(minor: str) -> bool:
    try:
        return int(minor.split(".")[1]) % 2 == 0
    except (IndexError, ValueError):
        return False


def _doc_url(minor: str) -> str:
    return f"https://docs.redhat.com/en/documentation/openshift_container_platform/{minor}"


def _discover_channels() -> list[str]:
    """Probe the Cincinnati API to find all active stable channels."""
    channels = []
    minor = 14
    misses = 0
    while misses < 2:
        ver = f"4.{minor}"
        try:
            resp = httpx.get(
                _GRAPH_URL,
                params={"channel": f"stable-{ver}", "arch": "amd64"},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json().get("nodes"):
                channels.append(ver)
                misses = 0
            else:
                misses += 1
        except Exception:
            misses += 1
        minor += 1
    return channels


def fetch_ocp_releases(channels: list[str] | None = None) -> list[dict]:
    if not channels:
        channels = _discover_channels()

    results = []
    for minor in channels:
        try:
            resp = httpx.get(
                _GRAPH_URL,
                params={"channel": f"stable-{minor}", "arch": "amd64"},
                timeout=15,
            )
            resp.raise_for_status()
            nodes = resp.json().get("nodes", [])
        except Exception:
            nodes = []

        own_versions = [
            n for n in nodes
            if n["version"].startswith(f"{minor}.")
        ]
        if not own_versions:
            continue

        own_versions.sort(
            key=lambda n: [int(x) for x in n["version"].split(".")],
            reverse=True,
        )
        latest = own_versions[0]
        lifecycle = _LIFECYCLE.get(minor, {})

        results.append({
            "minor": minor,
            "latest_z": latest["version"],
            "z_count": len(own_versions),
            "ga_date": lifecycle.get("ga", ""),
            "eol_date": lifecycle.get("eol", ""),
            "eus": _is_eus(minor),
            "doc_url": _doc_url(minor),
            "errata_url": latest.get("metadata", {}).get("url", ""),
        })

    return results
