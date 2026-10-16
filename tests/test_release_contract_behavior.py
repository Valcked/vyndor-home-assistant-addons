"""Offline tests for Vyndor release contract security."""

import copy
import unittest

from unittest.mock import patch
from urllib.error import HTTPError

from tools import verify_release_contract as verifier


class ContractBehaviorTests(unittest.TestCase):

    def setUp(self):
        self.lock = verifier.parse_lock(
            verifier.LOCK.read_text(encoding="utf-8")
        )

        self.releases = self.lock["releases"]

    def test_current_catalog_matches_lock(self):
        verifier.validate_local(self.lock)

    def test_unregistered_catalog_version_fails(self):
        self.releases["vyndor_home"].pop("0.1.2")

        with self.assertRaisesRegex(
            ValueError,
            "no releases",
        ):
            verifier.validate_local(self.lock)

    def test_invalid_digest_fails(self):
        self.releases["vyndor_agent"]["0.1.5"][
            "digest"
        ] = "invalid"

        with self.assertRaisesRegex(
            ValueError,
            "invalid digest",
        ):
            verifier.validate_local(self.lock)

    def test_attestation_is_allowed(self):
        index = {
            "schemaVersion": 2,
            "manifests": [
                {
                    "platform": {
                        "os": "unknown",
                        "architecture": "unknown",
                    },
                },
                {
                    "platform": {
                        "os": "linux",
                        "architecture": "amd64",
                    },
                    "digest": "sha256:" + "a" * 64,
                },
            ],
        }

        self.assertEqual(
            verifier.manifest_platforms(index),
            {
                "linux/amd64": "sha256:" + "a" * 64,
            },
        )

    def test_duplicate_platform_is_rejected(self):
        descriptor = {
            "platform": {
                "os": "linux",
                "architecture": "amd64",
            },
            "digest": "sha256:" + "a" * 64,
        }

        with self.assertRaisesRegex(
            ValueError,
            "Duplicate Linux platform",
        ):
            verifier.manifest_platforms({
                "schemaVersion": 2,
                "manifests": [
                    descriptor,
                    descriptor,
                ],
            })

    def test_changed_registry_digest_fails(self):
        with patch.object(
            verifier,
            "fetch_manifest",
            return_value=(
                "sha256:" + "f" * 64,
                {},
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "TAG CHANGED",
            ):
                verifier.verify_registry(self.releases)

    def test_missing_registry_tag_fails(self):
        with patch.object(
            verifier,
            "fetch_manifest",
            side_effect=HTTPError(
                "registry",
                404,
                "missing",
                {},
                None,
            ),
        ):
            with self.assertRaises(HTTPError):
                verifier.verify_registry(self.releases)

    def test_existing_release_cannot_be_rewritten(self):
        proposed = copy.deepcopy(self.releases)

        proposed["vyndor_home"]["0.1.2"][
            "digest"
        ] = "sha256:" + "f" * 64

        with self.assertRaisesRegex(
            ValueError,
            "Existing locked release",
        ):
            verifier.require_append_only(
                self.releases,
                proposed,
            )

    def test_new_version_is_append_only(self):
        proposed = copy.deepcopy(self.releases)

        proposed["vyndor_home"]["0.1.3"] = (
            copy.deepcopy(
                proposed["vyndor_home"]["0.1.2"]
            )
        )

        verifier.require_append_only(
            self.releases,
            proposed,
        )


if __name__ == "__main__":
    unittest.main()
