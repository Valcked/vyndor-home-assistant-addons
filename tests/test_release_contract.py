"""M-001 release contract regression tests."""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOCK = ROOT / "releases/release-lock.json"

VALIDATOR = ROOT / "tools/verify_release_contract.py"

WORKFLOW = (
    ROOT / ".github/workflows/verify-release-contract.yml"
)

DIGEST_RE = re.compile(
    r"sha256:[0-9a-f]{64}\Z"
)

ADDONS = (
    "vyndor_agent",
    "vyndor_home",
)

KNOWN_RELEASES = {
    ("vyndor_agent", "0.1.5"): (
        "sha256:"
        "43a08458161b3a7317155335af1ed35426388418cd7dc74307f7682a5bd91cda"
    ),
    ("vyndor_home", "0.1.2"): (
        "sha256:"
        "3d5b26d39127ec203283e2d9ca403ba39d927daf119e78d5b83bd7b7589e99f3"
    ),
}


def catalog_value(addon, key):
    path = ROOT / addon / "config.yaml"

    content = path.read_text(encoding="utf-8")

    for line in content.splitlines():
        if line.startswith(f"{key}:"):
            return (
                line.partition(":")[2]
                .strip()
                .strip("\"'")
            )

    raise AssertionError(
        f"Missing {key} in {path}"
    )


def release_lock():
    if not LOCK.is_file():
        raise AssertionError(
            "M-001 release-lock.json ontbreekt"
        )

    return json.loads(
        LOCK.read_text(encoding="utf-8")
    )


class ReleaseContractTests(unittest.TestCase):

    def test_release_lock_exists(self):
        self.assertTrue(
            LOCK.is_file(),
            "Release register ontbreekt",
        )

    def test_current_catalog_versions_are_registered(self):
        data = release_lock()

        self.assertEqual(
            data.get("schemaVersion"),
            1,
        )

        releases = data.get("releases")

        self.assertIsInstance(releases, dict)

        for addon in ADDONS:
            with self.subTest(addon=addon):

                version = catalog_value(
                    addon,
                    "version",
                )

                image = catalog_value(
                    addon,
                    "image",
                )

                entry = releases[addon][version]

                self.assertEqual(
                    entry["image"],
                    image,
                )

                self.assertRegex(
                    entry["digest"],
                    DIGEST_RE,
                )

    def test_existing_release_digests_are_preserved(self):
        data = release_lock()

        for key, expected in KNOWN_RELEASES.items():
            addon, version = key

            with self.subTest(
                addon=addon,
                version=version,
            ):
                actual = (
                    data["releases"]
                    [addon]
                    [version]
                    ["digest"]
                )

                self.assertEqual(
                    actual,
                    expected,
                )

    def test_release_validator_and_ci_exist(self):
        self.assertTrue(
            VALIDATOR.is_file(),
            "Release validator ontbreekt",
        )

        self.assertTrue(
            WORKFLOW.is_file(),
            "Release CI-workflow ontbreekt",
        )

        workflow = WORKFLOW.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "tools/verify_release_contract.py",
            workflow,
        )

        self.assertRegex(
            workflow,
            r"(?m)^[ \t]+pull_request:",
        )

        self.assertRegex(
            workflow,
            r"(?m)^[ \t]+schedule:",
        )


if __name__ == "__main__":
    unittest.main()
