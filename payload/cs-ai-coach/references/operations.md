# Operations

## Deployment scope

This Skill supplies the coaching policy for ordinary conversation and the
documentation of the hardened practice mode. The practice mode itself is
implemented by the sibling `teacher` Skill (`teacher/scripts/th/coach.py`) and
runs inside the Teacher standalone harness. This Skill bundles only its
terminology validator, its observer wrapper, and their tests. Install it next
to `teacher/` in the same skills root.

## Launch

Requirements are Windows, Linux, or macOS; Python 3 with the standard library;
a model endpoint configured for Teacher; and, for the page, a browser. No
Python or JavaScript packages are required.

Configure the backend once, then start the chat:

```sh
python3 <skills-root>/teacher/scripts/teacher.py setup --base-url <URL> --model <MODEL> [--guard-model <MODEL>] [--timeout <SECONDS>]
python3 <skills-root>/teacher/scripts/teacher.py setup --api-key-stdin
python3 <skills-root>/teacher/scripts/teacher.py chat
```

Inside the chat, submit `/coach <problem>`. After admission, write steps as
plain text and use `/idea N <text>`, `/conclude`, `/route`, `/hint`,
`/incubate`, `/done [lenient]`, and `/exit`; `/help` lists them. While the
practice is in `HARD_LOCK`, other Teacher commands are refused until `/exit`;
`/quit` leaves the chat and keeps the practice open for the next chat. The
same operations are available one per invocation as `teacher.py coach-start`,
`coach-step [--role ...] [--connects N]`, `coach-route`, `coach-hint`,
`coach-incubate`, `coach-done`, and `coach-exit`.

`teacher.py serve [--port N] [--no-browser]` starts the local page. The console
prints the store path and an entry URL whose fragment contains the page token.
The page accepts `/coach <problem>`, plain-text steps, and the same practice
commands, and refuses other commands during a practice. Closing the process
invalidates the token; stored practices remain in the store.

The server binds only to `127.0.0.1`. Do not put the token in a query string,
the store, a log, an error, or an event. A future network deployment must
replace this local token with real identity, authentication, revocation, and
audit.

## Database

The default store is `teacher.sqlite3` under
`~/Library/Application Support/teacher/` on macOS,
`${XDG_STATE_HOME:-~/.local/state}/teacher/` on Linux, and
`%LOCALAPPDATA%\teacher\` on Windows. To test without touching normal data,
pass `teacher.py --store <path>` or set `TEACHER_STATE_DIR`. Practice rows live
in `coach_problems` and `coach_nodes`; every write is a compare-and-swap
transaction on the execution head, so a failed write commits nothing. The
latest submitted problem is the current practice; a new `/coach` seals the
previous one first. A sealed practice is kept for `/route` and inspection and
is never reopened.

## Backend failures

Check `teacher.py setup --show`: it prints the configuration path, the backend
command, endpoint and model names, and whether a key file exists, never the
key. If the backend command is empty, the chat prints
“没有配置模型后端：先运行 teacher.py setup。”. If the endpoint, model, or key is
missing or wrong, every backend call fails; every admission is then stored
`UNVERIFIED` and no practice opens.

The Harness never prints raw subprocess stderr or model output. An
authentication failure, missing executable, nonzero exit, empty or malformed
JSON, missing result, or timeout produces the same fixed user-visible
failure sentence for a step and a closed failure event. The API key is read
from `TH_API_KEY` or from the owner-only key file written by
`setup --api-key-stdin`; it is never written into the configuration.

The backend child has no tools. Its role is fixed by the method it is asked
to answer, and the Guard child runs with `TH_ROLE=guard` so it uses the
configured guard model.

Problem initialization uses the same isolated backend calls before a practice
exists. Unknown claim truth becomes `READY + KNOWN_OPEN` or
`READY + TRUTH_UNVERIFIED`; the initializer does not try to solve the claim.
Reviewer or auditor failure, disagreement about structural admission, or a
schema error stores `UNVERIFIED` and leaves the practice closed. It never
falls back to a single-review `READY` decision.

Lenient completion likewise uses two isolated closed audits and returns only
the closed completion status. Any audit refusal, disagreement, schema error, or
backend failure leaves the practice in `HARD_LOCK` with `NOT_COMPLETE` and the
deterministic route summary.

## Calculation routing

In ordinary host-agent chat, after the learner has named the exact
learner-owned expression, program, or experiment and the mechanical operation,
delegate only that bounded computation to `$cs-ai-computation`. Preserve the
expression, operation, assumptions, and domain verbatim; do not ask the
computation Skill to choose a route, configuration, or next step.

In the default `GUIDED` profile, the Coach may itself perform a uniquely
implied routine local operation without forcing the learner to transcribe it.
Delegation still follows `$cs-ai-computation`'s own input gate; if the
expression or operation is not explicit enough for that Skill, either perform
the bounded reasoning directly or ask for the missing specification. `STRICT`
requires the exact learner-owned expression and exact operation before any
delegation.

That ordinary-chat delegation does not expand the Harness attack surface. The
Harness does not load `$cs-ai-computation`, has no calculator or computation
adapter in the coach path, and exposes no shell, subprocess, or MCP
capability to the Coach or Guard. Adding one would require a positive input
grammar, an explicit operation allowlist, resource ceilings, output
sanitation, audit records, failed-closed tests, and the full testing gate
before it could be described as available.

## Validation

Run:

```sh
python3 -m unittest discover -s <skills-root>/teacher/scripts/tests -p "test_*.py"
python3 -B <skills-root>/cs-ai-coach/scripts/validate_terminology.py --skill-root <skills-root>/cs-ai-coach --json
python3 -B -m unittest discover -s <skills-root>/cs-ai-coach/scripts/tests -p "test_*.py"
```

The teacher suite covers the practice mode: admission needs two agreeing
reviews; a step is judged with closed values only; a fabricated quote or a
disagreeing Guard fails closed; answer requests never reach a model; strict
completion is computed and its review is the learner's own route; a valid step
resolves an obstacle only when both calls agree, and an unrelated valid step
does not; a malformed value fails closed instead of crashing; lenient
completion reaches `ROUTE_READY` without a conclusion; exploratory ideas must
name what they connect to; off-topic input gets one reminder, then a fixed
refusal; a new problem seals the current one; an exited problem does not
become an answer; a hint needs an obstacle and a new attempt and is labelled;
an overlong hint fails closed; incubation renders a fixed template from
learner text; foreign anchors are rejected before any model call; and no
channel carries model text to the surface. In the distribution tree the suite also checks the package
inventory, which must be regenerated after any payload change.

This Skill's tests run the terminology validator, check that the version
coupling manifest lists exactly the shipped files, check the observer
catalog, confirm that the observer wrapper preserves the child's output and
exit code when the observer is unreachable, and compare every closed
vocabulary and fixed sentence these documents quote with
`teacher/scripts/th/coach.py` and `th/constants.py`.

Ordinary-chat behavior is not covered by the deterministic suites. Check it
with regression cases for default profile selection, uniquely implied routine
work, bounded local correction, the loop-invariant, telescoping-sum, and
expectation-gradient fast-forward pattern, ambiguous operations, decisive-idea
refusal, strict provenance, one-way tightening, and unchanged Harness
`HARD_LOCK`.

Deterministic tests do not establish pedagogical improvement. Do not describe
a profile change as experimentally verified without a controlled comparison
under a fixed model and configuration. Generated caches and bytecode must not
be shipped.
