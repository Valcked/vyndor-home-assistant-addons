#!/usr/bin/env python3
"""Verify Vyndor's locked Home Assistant release artifacts."""

import argparse
import hashlib
import json
import re
import subprocess
import sys

from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "releases/release-lock.json"

IMAGES = {
    "vyndor_agent": "ghcr.io/valcked/vyndor-agent",
    "vyndor_home": "ghcr.io/valcked/vyndor-home",
}

ARCH = {
    "amd64": "linux/amd64",
    "aarch64": "linux/arm64",
}

DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")

ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def no_duplicate_keys(pairs):
    result = {}

    for key, value in pairs:
        require(
            key not in result,
            f"Duplicate release-lock key: {key}",
        )
        result[key] = value

    return result


def parse_lock(raw):
    return json.loads(
        raw,
        object_pairs_hook=no_duplicate_keys,
    )


def catalog_field(addon, field):
    lines = (
        ROOT / addon / "config.yaml"
    ).read_text(encoding="utf-8").splitlines()

    values = [
        line.partition(":")[2].strip().strip("\"'")
        for line in lines
        if line.startswith(f"{field}:")
    ]

    require(
        len(values) == 1,
        f"{addon}: missing or duplicate {field}",
    )

    return values[0]


def catalog_platforms(addon):
    source = (
        ROOT / addon / "config.yaml"
    ).read_text(encoding="utf-8")

    match = re.search(
        r"(?m)^arch:[ \t]*\n((?:[ \t]+[^\n]*\n)*)",
        source,
    )

    require(
        match is not None,
        f"{addon}: missing arch list",
    )

    names = re.findall(
        r"(?m)^[ \t]+-[ \t]+([a-z0-9_]+)[ \t]*$",
        match.group(1),
    )

    require(
        bool(names) and len(names) == len(set(names)),
        f"{addon}: duplicate or empty arch",
    )

    require(
        all(name in ARCH for name in names),
        f"{addon}: unsupported arch",
    )

    return {ARCH[name] for name in names}


def validate_local(lock):
    require(
        isinstance(lock, dict)
        and lock.get("schemaVersion") == 1,
        "Unsupported release-lock schema",
    )

    releases = lock.get("releases")

    require(
        isinstance(releases, dict)
        and set(releases) == set(IMAGES),
        "Release-lock must contain exactly the catalog addons",
    )

    for addon, expected_image in IMAGES.items():
        versions = releases[addon]

        require(
            isinstance(versions, dict) and bool(versions),
            f"{addon}: no releases",
        )

        for version, entry in versions.items():
            require(
                VERSION.fullmatch(version) is not None,
                f"Invalid version {version}",
            )

            require(
                isinstance(entry, dict)
                and entry.get("image") == expected_image,
                f"{addon}:{version}: image mismatch",
            )

            digest = entry.get("digest")

            require(
                isinstance(digest, str)
                and DIGEST.fullmatch(digest) is not None,
                f"{addon}:{version}: invalid digest",
            )

            platforms = entry.get("platforms")

            require(
                isinstance(platforms, dict)
                and bool(platforms)
                and set(platforms).issubset(set(ARCH.values())),
                f"{addon}:{version}: invalid platforms",
            )

            require(
                all(
                    isinstance(value, str)
                    and DIGEST.fullmatch(value)
                    for value in platforms.values()
                ),
                f"{addon}:{version}: invalid platform digest",
            )

        current_version = catalog_field(addon, "version")

        require(
            catalog_field(addon, "image") == expected_image,
            f"{addon}: catalog image mismatch",
        )

        require(
            current_version in versions,
            f"{addon}: unregistered catalog version "
            f"{current_version}",
        )

        require(
            set(versions[current_version]["platforms"])
            == catalog_platforms(addon),
            f"{addon}: catalog architecture mismatch",
        )

    return releases


def require_append_only(old_releases, new_releases):
    for addon, versions in old_releases.items():
        for version, entry in versions.items():
            require(
                new_releases.get(addon, {}).get(version) == entry,
                "Existing locked release modified or removed: "
                f"{addon}:{version}",
            )


def verify_append_only(releases, base_ref):
    require(
        re.fullmatch(r"[0-9a-f]{40}", base_ref) is not None,
        "Invalid base commit SHA",
    )

    check = subprocess.run(
        ["git", "cat-file", "-t", base_ref],
        capture_output=True,
        text=True,
    )

    require(
        check.returncode == 0
        and check.stdout.strip() == "commit",
        "Base commit is not available",
    )

    listed = subprocess.run(
        [
            "git", "ls-tree", "-r", "--name-only",
            base_ref, "--", "releases/release-lock.json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    if not listed.stdout.strip():
        print("BASE: first release-lock introduction")
        return

    old = subprocess.run(
        [
            "git", "show",
            f"{base_ref}:releases/release-lock.json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    previous = parse_lock(old.stdout)["releases"]

    require_append_only(previous, releases)


def manifest_platforms(manifest):
    require(
        isinstance(manifest, dict)
        and manifest.get("schemaVersion") == 2
        and isinstance(manifest.get("manifests"), list),
        "Expected OCI/Docker multi-arch index",
    )

    result = {}

    for item in manifest["manifests"]:
        require(
            isinstance(item, dict)
            and isinstance(item.get("platform"), dict),
            "Invalid platform descriptor",
        )

        platform = item["platform"]

        os_name = platform.get("os")
        arch = platform.get("architecture")

        if os_name == "unknown" and arch == "unknown":
            continue

        require(
            os_name == "linux"
            and isinstance(arch, str),
            f"Unexpected platform: {platform}",
        )

        name = f"linux/{arch}"

        require(
            name not in result,
            f"Duplicate Linux platform: {name}",
        )

        digest = item.get("digest")

        require(
            isinstance(digest, str)
            and DIGEST.fullmatch(digest),
            f"Invalid platform digest: {name}",
        )

        result[name] = digest

    return result


def fetch_manifest(image, version):
    repo = image.removeprefix("ghcr.io/")

    query = urlencode({
        "service": "ghcr.io",
        "scope": f"repository:{repo}:pull",
    })

    token_request = Request(
        f"https://ghcr.io/token?{query}"
    )

    with urlopen(token_request, timeout=20) as response:
        require(
            response.status == 200,
            "GHCR token request failed",
        )

        token = json.load(response).get("token")

    require(
        isinstance(token, str) and bool(token),
        "No GHCR pull token",
    )

    request = Request(
        f"https://ghcr.io/v2/{repo}/manifests/{version}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": ACCEPT,
        },
    )

    with urlopen(request, timeout=30) as response:
        require(
            response.status == 200,
            f"Missing or inaccessible image {image}:{version}",
        )

        raw = response.read()

        header_digest = response.headers.get(
            "Docker-Content-Digest"
        )

    digest = "sha256:" + hashlib.sha256(raw).hexdigest()

    require(
        not header_digest or header_digest == digest,
        "Registry digest header differs from manifest bytes",
    )

    return digest, json.loads(raw)


def verify_registry(releases):
    for addon, versions in releases.items():
        for version, entry in versions.items():
            actual, manifest = fetch_manifest(
                entry["image"],
                version,
            )

            require(
                actual == entry["digest"],
                f"TAG CHANGED: {addon}:{version} "
                f"({actual} != {entry['digest']})",
            )

            actual_platforms = manifest_platforms(manifest)

            require(
                actual_platforms == entry["platforms"],
                f"PLATFORM MISMATCH: {addon}:{version}",
            )

            print(
                f"PASS: {addon}:{version} {actual} "
                f"({', '.join(sorted(actual_platforms))})"
            )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--base-ref",
        help="PR/push base SHA for append-only history",
    )

    args = parser.parse_args()

    try:
        releases = validate_local(
            parse_lock(LOCK.read_text(encoding="utf-8"))
        )

        if args.base_ref:
            verify_append_only(releases, args.base_ref)

        verify_registry(releases)

    except Exception as error:
        print(
            f"FAIL: release contract: {error}",
            file=sys.stderr,
        )
        return 1

    print("VYNDOR RELEASE CONTRACT VERIFIED")

    return 0


if __name__ == "__main__":
    sys.exit(main())
