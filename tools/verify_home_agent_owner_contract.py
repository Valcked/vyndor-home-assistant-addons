#!/usr/bin/env python3

"""Verify the real Home and Agent OWNER approval
protocol builders against each other."""

import base64
import json
import os
import subprocess
import sys
import tempfile

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import (
    load_pem_public_key,
)


def b64url(value: bytes) -> str:
    return (
        base64.urlsafe_b64encode(value)
        .decode("ascii")
        .rstrip("=")
    )


def timestamp(value: datetime) -> str:
    return (
        value.isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python verify_home_agent_owner_contract.py "
            "<home_repo> <agent_repo> <tsx_path>"
        )

    home_repo = Path(sys.argv[1]).resolve()
    agent_repo = Path(sys.argv[2]).resolve()
    tsx = Path(sys.argv[3]).resolve()

    protocol = (
        home_repo
        / "bridge/src/home-agent-owner-approval-protocol.ts"
    )

    agent_module_dir = (
        agent_repo / "vyndor_agent/app"
    )

    for path in (protocol, agent_module_dir, tsx):
        if not path.exists():
            raise RuntimeError(
                f"Required path missing: {path}"
            )

    sys.path.insert(
        0,
        str(agent_module_dir),
    )

    from home_owner_approval import (
        HomeOwnerApprovalError,
        build_home_owner_approval_start_payload,
        build_home_owner_approval_payload,
    )

    now = datetime.now(
        timezone.utc,
    ).replace(microsecond=0)

    common = {
        "protocolVersion": 1,
        "installationId":
            "11111111-1111-4111-8111-111111111111",
        "gatewayId":
            "22222222-2222-4222-8222-222222222222",
        "claimId":
            "33333333-3333-4333-8333-333333333333",
        "homeAccountId":
            "44444444-4444-4444-8444-444444444444",
        "gatewayFingerprint":
            b64url(bytes(range(32))),
    }

    start = {
        **common,
        "requestNonce":
            b64url(bytes(range(32, 64))),
        "issuedAt": timestamp(now),
        "expiresAt": timestamp(
            now + timedelta(seconds=30),
        ),
    }

    challenge = {
        **common,
        "challengeId":
            "55555555-5555-4555-8555-555555555555",
        "nonce":
            b64url(bytes(range(64, 96))),
        "issuedAt": timestamp(now),
        "expiresAt": timestamp(
            now + timedelta(seconds=90),
        ),
    }

    node_script = """
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { generateKeyPairSync, sign } from 'node:crypto'

async function main() {
  const protocol = await import(
    pathToFileURL(process.argv[2]).href
  )

  const fixture = JSON.parse(
    readFileSync(process.argv[3], 'utf8')
  )

  const start =
    protocol.buildHomeAgentOwnerApprovalStartPayload(
      fixture.start
    )

  const challenge =
    protocol.buildHomeAgentOwnerApprovalPayload(
      fixture.challenge
    )

  let invalidNonceRejected = false

  try {
    protocol.buildHomeAgentOwnerApprovalPayload({
      ...fixture.challenge,
      nonce: '***',
    })
  } catch {
    invalidNonceRejected = true
  }

  const { publicKey, privateKey } =
    generateKeyPairSync('ed25519')

  const signature = sign(
    null,
    Buffer.from(challenge, 'utf8'),
    privateKey
  ).toString('base64url')

  console.log(JSON.stringify({
    start,
    challenge,
    invalidNonceRejected,
    signature,
    publicKeyPem: publicKey.export({
      type: 'spki',
      format: 'pem',
    }),
  }))
}

main().catch(error => {
  console.error(error)
  process.exitCode = 1
})
"""

    with tempfile.TemporaryDirectory(
        prefix="vyndor-owner-contract-"
    ) as temp:
        directory = Path(temp)

        script = directory / "home-contract.ts"
        fixture = directory / "fixture.json"

        script.write_text(node_script)

        fixture.write_text(
            json.dumps({
                "start": start,
                "challenge": challenge,
            })
        )

        environment = os.environ.copy()
        environment.pop("NODE_OPTIONS", None)

        result = subprocess.run(
            [
                str(tsx),
                str(script),
                str(protocol),
                str(fixture),
            ],
            cwd=home_repo,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

        home = json.loads(result.stdout)

    def agent_challenge(fields):
        return SimpleNamespace(
            protocol_version=fields["protocolVersion"],
            challenge_id=fields["challengeId"],
            installation_id=fields["installationId"],
            gateway_id=fields["gatewayId"],
            gateway_fingerprint=fields["gatewayFingerprint"],
            claim_id=fields["claimId"],
            home_account_id=fields["homeAccountId"],
            nonce=fields["nonce"],
            issued_at=fields["issuedAt"],
            expires_at=fields["expiresAt"],
        )

    agent_start = (
        build_home_owner_approval_start_payload(
            start
        )
    )

    agent_payload = (
        build_home_owner_approval_payload(
            agent_challenge(challenge)
        )
    )

    assert home["start"] == agent_start
    print("PASS — START payload identiek")

    assert home["challenge"] == agent_payload
    print("PASS — CHALLENGE payload identiek")

    assert home["invalidNonceRejected"]

    try:
        build_home_owner_approval_payload(
            agent_challenge({
                **challenge,
                "nonce": "***",
            })
        )
    except HomeOwnerApprovalError:
        pass
    else:
        raise AssertionError(
            "Agent accepts invalid nonce"
        )

    print("PASS — Ongeldige nonce geweigerd")

    public_key = load_pem_public_key(
        home["publicKeyPem"].encode()
    )

    signature = base64.urlsafe_b64decode(
        home["signature"] +
        "=" * (-len(home["signature"]) % 4)
    )

    public_key.verify(
        signature,
        agent_payload.encode("utf8"),
    )

    print("PASS — Ed25519-verificatie geslaagd")

    modified = {
        **challenge,
        "claimId":
            "66666666-6666-4666-8666-666666666666",
    }

    modified_payload = (
        build_home_owner_approval_payload(
            agent_challenge(modified)
        )
    )

    try:
        public_key.verify(
            signature,
            modified_payload.encode("utf8"),
        )
    except InvalidSignature:
        print("PASS — Gewijzigde claim geweigerd")
    else:
        raise AssertionError(
            "Modified claim accepted"
        )

    print()
    print("M-003 OWNER CONTRACT: PASSED")


if __name__ == "__main__":
    main()
