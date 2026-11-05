# Approver signing procedure (v1.12 W9)

A Policy takes effect only when an approver signs its version (WORK_AGENT.md, sections 9 and 14).
The agent verifies signatures and never signs, so the approver's private key stays with the
approver. This procedure is how that happens. It is decision S1 and OPEN_DECISIONS item 3.

## What the key is for

The approver signs a Policy's version, not a message. The signed bytes are the domain prefix
`organism.work.policy.v1`, a newline, and the version. `organism work adopt` checks them against the
approvers in the trust file. Before you sign, read the Policy: its rules and instruction texts are
what the agent will act on. Signing approves exactly the rules and texts in that version.

## Where the key lives

- The seed (the private key) is a 32-byte value, kept as hex in a file **outside the repository**,
  on the approver's own machine. Back it up offline.
- It is never in the repository, on the agent's machine, in the agent's environment, in the jail, or
  in any CI secret. `approve_policy.py` refuses a seed path inside the repository, and it never
  overwrites a seed.
- The agent never generates, stores or reads it. The tests use test keys only.

## One-time setup (approver's machine)

1. Install the Organism SDK at the version the operator runs. The script imports `organism_sdk`.
2. Make the key pair. Choose a path outside the repository:

   ```bash
   python docs/v1.12/approver/approve_policy.py keygen ~/organism-approver/seed.hex
   ```

   It prints the public key, a 64-character hex string. The public key is safe to share.
3. Give the operator a trust file that holds only public keys:

   ```json
   {"authors": [], "approvers": ["<public key from step 2>"]}
   ```

   The operator names this file in `organism work adopt --trust`.

## Signing a Policy

1. The operator gives you the Policy as JSON, and the version it expects. Read the rules and
   instructions in it.
2. Sign it:

   ```bash
   python docs/v1.12/approver/approve_policy.py sign policy.json ~/organism-approver/seed.hex signature.hex
   ```

   It prints the Policy's version. Check that it is the version the operator quoted. A different
   version means a different Policy, and the signature is for that one only.
3. Send `signature.hex` back to the operator. It holds no secret.

The operator adopts it with:

```bash
organism work adopt policy.json --signature signature.hex --trust trust.json
```

`adopt` refuses a signature that is not an approver's, and it stores nothing when it refuses. A
signature over a different version is refused too. A graduated Policy, from `graduate`, is a new
version and is signed the same way.

## Rotation and revocation

- **New key.** Add its public key to the `approvers` list. Policies signed by the old key that were
  already adopted stay in force.
- **Revoke a key.** Remove its public key from `approvers`. From then on `adopt` refuses any Policy
  signed with it. Adoption checks the signature once, when the Policy is adopted, so a Policy already
  in force stays in force until a new one replaces it.
- **Lost seed.** Treat it as compromised: revoke its public key and make a new key pair.

## What the script does not do

It signs the Policy file it is given, and nothing else. It does not judge the Policy's content, so
reading the rules and instructions before you sign is your job. It does not contact the network. It
reads the Policy file and the seed file, and writes the signature file. The procedure is offline on
purpose: a seed that never reaches a networked machine cannot be read from one.
