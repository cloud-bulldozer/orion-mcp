# Fullsend

Fullsend automates repository development through GitHub Actions. It does not
change the Orion-MCP server or the models used by MCP clients.

## Configuration

[`.fullsend/config.yaml`](../.fullsend/config.yaml) follows the
[Fullsend configuration at `2d7ecf976`](https://github.com/fullsend-ai/fullsend/blob/2d7ecf976aad7f62bdca61e68b202c92bd8bf35b/.fullsend/config.yaml),
including its QualityFlow registration. Both managed workflow callers use that
Fullsend revision. The repository-specific differences are:

- GPT review uses `openai/gpt-6.1-sol` directly, authenticated through
  `FULLSEND_OPENAI_API_KEY`, rather than Fullsend's inference gateway.
- The GitHub tracker permits issue creation in the current repository, without
  Fullsend's organization-wide cross-repository allowlist.
- Infrastructure identifiers and credentials are supplied separately through
  Actions settings, not copied from Fullsend's deployment.

The code agent starts only when an authorized human comments `/fs-code` on an
issue. [The triage overlay](../.fullsend/triage.yaml) sets `TRIAGE_AUTO_CODE: "off"`
on both runner and sandbox, so triage does not promote issues to `ready-to-code`.
The dispatch caller also skips `ready-to-code` issue-label events, so adding
that label manually or through another bot cannot start the code agent. Keep
both gates when refreshing upstream workflow templates; the local regression
tests protect this policy.

This controls initial code-agent dispatch, not the separate review/fix behavior
or explicitly requested QualityFlow runs. Normal branch protections and human
merge approval remain unchanged. Prioritize remains enabled through the upstream
defaults, using Pi and `google-vertex/gemini-3.8-flash`.

## Who can invoke commands

Fullsend checks the commenter's effective GitHub permission on this repository:

| Commands | Minimum repository access |
| --- | --- |
| `/fs-triage`, `/fs-review` | Triage, Write, Maintain, or Admin |
| `/fs-code`, `/fs-fix`, `/fs-retro`, `/fs-prioritize` | Write, Maintain, or Admin |
| `/fs-plan-tests` | Write, Maintain, or Admin; eligible non-fork PR required |

Team and inherited repository permissions count. Organization membership,
contributor status, or authoring the issue/PR alone does not grant command
access. An outside collaborator with the required repository permission can
also invoke commands. No additional OWNERS-file authorization is configured.
For example, an organization member with only Read access cannot start coding;
a member of a team granting Write access can. Post `/fs-code` at the start of
an issue comment, not on a PR.

`/fs-fix-stop` is a stop-only exception: a PR author can stop fixing on their
own PR even without Write access. This does not grant permission to start code
or other write-capable agents.

## QualityFlow

The pinned external harness adds a separate quality-engineering agent for test
planning, design review/refinement, and test generation. It does not replace
triage. Its `/fs-plan-tests` trigger requires a non-fork PR, and its instructions
include pushing generated tests to the PR branch. Jira mode requires separate
Jira configuration; this registration uses the upstream GitHub entry point.

## Setup

Keep the onboarding PR in draft until all configured GitHub Apps are approved
for the target repository, including triage and prioritize. An installation
request is not an active installation. Also confirm organization Actions policy,
approved model access, billing, and repository-data use before merging.

Required Actions secrets:

- `FULLSEND_GCP_PROJECT_ID`
- `FULLSEND_GCP_WIF_PROVIDER`
- `FULLSEND_OPENAI_API_KEY`

The Vertex WIF provider must trust the exact target repository. A personal
fork's provider and GitHub secrets are not inherited by upstream.

Configure variables `FULLSEND_MINT_URL`, `FULLSEND_GCP_REGION`,
`FULLSEND_PER_REPO_INSTALL`, and `FULLSEND_APP_SET`. The actual
`FULLSEND_REVIEW_CLIENT_ID` is recommended for prior-review provenance.
For API-key authentication, leave `inference.openai` and the
`FULLSEND_OPENAI_AUDIENCE`, `FULLSEND_OPENAI_IDENTITY_PROVIDER_ID`, and
`FULLSEND_OPENAI_SERVICE_ACCOUNT_ID` variables unconfigured, including inherited
organization values. OpenAI WIF takes precedence over a static key when set.

Discover current App identities and harness defaults from the selected
`fullsend-ai/agents` checkout:

```sh
git --no-pager ls-tree -r --name-only HEAD harness
git --no-pager grep -n -E '^(model|role|slug):' HEAD -- harness
```

Prioritize needs organization Projects read/write permission. To update a
Projects V2 board, set `FULLSEND_PROJECT_NUMBER` and provide numeric fields
`RICE Reach`, `RICE Impact`, `RICE Confidence`, `RICE Effort`, and `RICE Score`.
Without a board number, on-demand `/fs-prioritize` can post a RICE comment
without updating a board. No scheduled scoring workflow is added here.

## Verification and stop

After the approved files reach the target default branch, confirm triage and a
`ready-to-code` label do not start coding, then use `/fs-code` from a write-level
human account. Test review and prioritize on small issues/PRs. Test
`/fs-plan-tests` only on a non-fork PR where generated commits are acceptable. Check actual models,
structured output, costs, generated changes, and existing Python CI.

Disable the workflow and cancel active jobs for an immediate stop.
`kill_switch: true` stops future dispatches but does not cancel active runs.
See the [Fullsend operations guide](https://fullsend.sh/docs/guides/getting-started/operations)
for updates and teardown.
