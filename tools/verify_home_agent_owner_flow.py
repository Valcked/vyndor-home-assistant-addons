#!/usr/bin/env python3

"""Cross-repository Home/Agent OWNER coordinator test."""

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization


if len(sys.argv) != 4:
    raise SystemExit(
        "Usage: verify_home_agent_owner_flow.py "
        "<home_repo> <agent_repo> <tsx>"
    )

home_repo = Path(sys.argv[1]).resolve()
agent_repo = Path(sys.argv[2]).resolve()
tsx = Path(sys.argv[3]).resolve()

protocol = (
    home_repo
    / "bridge/src/home-agent-owner-approval-protocol.ts"
)

assert protocol.is_file()
assert tsx.is_file()

sys.path.insert(
    0,
    str(agent_repo / "tests"),
)

from test_home_owner_approval import (
    HomeOwnerApprovalTests,
    iso,
)
from home_owner_approval import (
    HomeOwnerApprovalError,
)


NODE_SCRIPT = """
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { createPrivateKey, sign } from 'node:crypto'

async function main() {
  const mode = process.argv[2]
  const protocolPath = process.argv[3]
  const keyPath = process.argv[4]
  const inputPath = process.argv[5]

  const protocol = await import(
    pathToFileURL(protocolPath).href
  )

  const fields = JSON.parse(
    readFileSync(inputPath, 'utf8')
  )

  const key = createPrivateKey(
    readFileSync(keyPath, 'utf8')
  )

  let payload

  if (mode === 'start') {
    payload =
      protocol.buildHomeAgentOwnerApprovalStartPayload(
        fields
      )
  } else if (mode === 'finish') {
    payload =
      protocol.buildHomeAgentOwnerApprovalPayload(
        fields
      )
  } else {
    throw new Error('Invalid signing mode')
  }

  const signature = sign(
    null,
    Buffer.from(payload, 'utf8'),
    key
  ).toString('base64url')

  const result =
    mode === 'start'
      ? { ...fields, signature }
      : {
          protocolVersion: fields.protocolVersion,
          challengeId: fields.challengeId,
          signature,
        }

  console.log(JSON.stringify(result))
}

main().catch(error => {
  console.error(error)
  process.exitCode = 1
})
"""


def sign_with_home(
    mode,
    fields,
    directory,
    script,
    private_key,
):
    input_path = directory / "request.json"

    input_path.write_text(
        json.dumps(fields)
    )

    env = os.environ.copy()
    env.pop("NODE_OPTIONS", None)

    result = subprocess.run(
        [
            str(tsx),
            str(script),
            mode,
            str(protocol),
            str(private_key),
            str(input_path),
        ],
        cwd=home_repo,
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode:
        raise RuntimeError(
            "Home signing failed:\n"
            + result.stderr[-3000:]
        )

    return json.loads(result.stdout)


def corrupt_signature(signature):
    padding = "=" * (
        -len(signature) % 4
    )

    raw = bytearray(
        base64.urlsafe_b64decode(
            signature + padding
        )
    )

    raw[0] ^= 1

    return (
        base64.urlsafe_b64encode(bytes(raw))
        .decode("ascii")
        .rstrip("=")
    )


async def verify_flow(
    fixture,
    directory,
    script,
    key_path,
):
    unsigned_start = (
        fixture.make_start_request()
    )

    unsigned_start.pop("signature")

    start = sign_with_home(
        "start",
        unsigned_start,
        directory,
        script,
        key_path,
    )

    invalid_start = {
        **start,
        "claimId":
            "77777777-7777-4777-8777-777777777777",
    }

    try:
        await fixture.service.start(
            invalid_start
        )
    except HomeOwnerApprovalError:
        print("PASS — Vervalst START geweigerd")
    else:
        raise AssertionError(
            "Forged START accepted"
        )

    challenge = (
        await fixture.service.start(start)
    )

    print("PASS — Agent accepteert Home START")

    try:
        await fixture.service.start(start)
    except HomeOwnerApprovalError:
        print("PASS — START replay geweigerd")
    else:
        raise AssertionError(
            "START replay accepted"
        )

    finish = sign_with_home(
        "finish",
        challenge,
        directory,
        script,
        key_path,
    )

    invalid_finish = {
        **finish,
        "signature": corrupt_signature(
            finish["signature"]
        ),
    }

    try:
        await fixture.service.finish(
            invalid_finish
        )
    except HomeOwnerApprovalError:
        print("PASS — Ongeldige FINISH geweigerd")
    else:
        raise AssertionError(
            "Forged FINISH accepted"
        )

    assert not fixture.security.confirm_calls

    response = await fixture.service.finish(
        finish
    )

    assert response["status"] == "CONFIRMED"

    assert fixture.security.confirm_calls == [
        (
            "33333333-3333-4333-8333-333333333333",
            "44444444-4444-4444-8444-444444444444",
        )
    ]

    print("PASS — Geldige OWNER-claim bevestigd")

    try:
        await fixture.service.finish(finish)
    except HomeOwnerApprovalError:
        print("PASS — FINISH replay geweigerd")
    else:
        raise AssertionError(
            "FINISH replay accepted"
        )

    assert len(
        fixture.security.confirm_calls
    ) == 1


def main():
    fixture = HomeOwnerApprovalTests(
        "test_valid_finish_confirms_exact_OWNER_claim_once"
    )

    fixture.setUp()

    # Gebruik een actuele tijd voor de cross-repo test.
    now = datetime.now(
        timezone.utc
    ).replace(microsecond=0)

    fixture.clock.value = now

    fixture.identity_response["identity"][
        "registeredAt"
    ] = iso(now - timedelta(minutes=10))

    fixture.identity_response["identity"][
        "verifiedAt"
    ] = iso(now - timedelta(minutes=9))

    with tempfile.TemporaryDirectory(
        prefix="vyndor-owner-flow-"
    ) as temp:
        directory = Path(temp)

        script = directory / "home-sign.ts"
        key_path = directory / "identity.pem"

        script.write_text(NODE_SCRIPT)

        private_key_bytes = (
            fixture.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=(
                    serialization.NoEncryption()
                ),
            )
        )

        key_path.write_bytes(private_key_bytes)
        key_path.chmod(0o600)

        asyncio.run(
            verify_flow(
                fixture,
                directory,
                script,
                key_path,
            )
        )

    print()
    print("M-003 OWNER COORDINATOR: PASSED")


if __name__ == "__main__":
    main()
