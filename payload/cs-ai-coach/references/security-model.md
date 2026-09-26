# Security model

## Guarantee boundary

The ordinary `$cs-ai-coach` Skill is a behavioral instruction. A host agent
receives a Skill as an instruction below its system and developer
instructions. Model compliance alone therefore cannot provide an absolute
no-answer guarantee.

Ordinary chat has two behavioral profiles. `GUIDED` is the default and
deliberately permits routine local derivations, bounded corrections, and
questions about route-local obligations already forced by a learner's step.
It returns control before naming any new technical direction. `STRICT` is
opt-in and enforces learner-only provenance, but it is still a model
instruction rather than a deterministic isolation boundary. Never describe
ordinary `STRICT` as equivalent to the Harness.

The Teacher harness provides a narrower, testable property: while a practice is stored in `HARD_LOCK`, no model-authored text is rendered in the Coach's output on the chat, command-line, or local-page surface. Two rules keep the Teacher answer path away from the practice: while a practice is in `HARD_LOCK`, the chat and the page refuse every non-practice command; and every answer entry (chat, page, `teacher.py ask`, `/ask`, `/switch`) refuses a request that lexically overlaps a protected problem — one in `HARD_LOCK`, or sealed without passing completion (exited or superseded). The property does not cover ordinary host-agent chat, the single labelled `/hint` response, a paraphrase, translation, or encoding with little shared wording, a problem that passed completion, or work performed outside the harness.

A completion check does not cross that boundary. Strict completion is computed
from the attempt graph, and lenient completion adds two isolated closed
audits. A passing result renders only the learner's own recorded steps and
statuses as the route map and seals the practice. No review prose is
generated, so nothing needs confirmation and nothing leaves the `HARD_LOCK`
guarantee.

Before `HARD_LOCK`, the problem initializer may expose a closed finding that a
submitted claim is false or a task is impossible. This is necessary to prevent
meaningless training on a broken problem, but it never exposes the
counterexample, repaired statement, strategy, complete argument, or answer.
Two isolated model calls must agree on structural admission before a problem
becomes `READY`. Unknown claim truth is stored as `KNOWN_OPEN` or
`TRUTH_UNVERIFIED` and does not block exploration. Uncertainty about whether
the input is a CS/AI practice problem, sufficiently specified, or internally
consistent, and every backend or schema failure, still blocks the practice as
`UNVERIFIED`.

`HARD_LOCK` still returns closed verdicts such as `valid_so_far` and `invalid`, because rapid feedback on the learner's own step is the purpose of the tool. Those verdicts reveal whether a submitted step was accepted. No system that judges arbitrary free-form technical claims can simultaneously establish that no claim encodes a final answer; that would require solving the semantic classification problem it is trying to guard. The Harness therefore does not claim that every possible natural-language, notation-level, or code-level disguise is recognizable with certainty. It combines problem admission, an explicit step role, the deterministic input gate, a practice-wide open-obstacle repair lock, an isolated Guard, and scripted adversarial tests. The absolute claim remains the data-flow property above: model-authored text has no `HARD_LOCK` display path.

## Threats

Defend against inputs outside CS/AI practice, incomplete or ambiguous problems,
false or inconsistent problem statements, forged `READY` state,
reviewer/auditor disagreement, direct answer requests, requests for complete
code, instruction overrides, forged exit messages, role-play, quoted or
translated answers, answer-path requests about an exited practice problem,
encodings, acrostics, candidate enumeration, method
enumeration, repeated yes/no probes, cumulative hints, summary bypasses,
off-topic chatbot diversion, slash-command injection inside step text, forged
completion claims, instructions embedded in the problem, a stolen or guessed
local-page token, long practices, process restarts, malformed structured
output, backend protocol changes, and database failures.

Research-specific threats include forged or out-of-range anchor numbers,
Coach-owned nodes presented as learner-owned, model-proposed new objects or
methods, a conditional question presented as an established fact, and
repeated incubation used to accumulate a decisive route. Anchor numbers index
only learner nodes, the Incubator can return only a closed question code and
IDs of the chosen anchors, the Guard must accept the selection as in scope,
and the conditional-hypothesis template marks its question unverified. Reject these before rendering or graph mutation.

Permit at most one model-backed research reflection per newly created learner
node. Repeated requests without new learner work receive a fixed response
before any Incubator call. Deterministic obstacle maps do not consume or reset
this allowance.

For ordinary `GUIDED`, also guard against assistance drift: a “routine
correction” that introduces a decisive new idea, a question that names a new
object, method, invariant, bound, data structure, transformation, or argument
direction under the label “bottleneck,” “condition,” or “obligation,” or an
inferred operation that chooses between materially different routes. Apply
the route-removal test: if a question still independently points toward a
recognizable technical direction after the learner's route is removed, it is
a strategy hint. These are behavioral risks rather than claims covered by the
Harness's absolute data-flow property.

## Trust boundaries

- The Teacher store (SQLite tables `coach_problems` and `coach_nodes`) is authoritative for practice state, admission, epistemic code, problem text, learner nodes, obstacles, hints, incubation markers, and completion status.
- Coach output is untrusted even when it satisfies the closed key set.
- Guard output is also untrusted. It can veto a candidate but cannot make model prose safe for `HARD_LOCK` display.
- The deterministic renderer, the fixed sentences in `teacher/scripts/th/coach.py`, is the only writer of practice feedback in `HARD_LOCK`.
- The local route summary is a second deterministic renderer over stored
  learner nodes. It receives no model output and cannot change practice state,
  completion, or hint eligibility.
- Research incubation is a third deterministic renderer. The model may return
  only a closed question code and IDs of the chosen learner nodes. The renderer
  may quote only bounded text from those nodes. It creates no learner node,
  obstacle, completion state, or hint eligibility; it stores only an empty
  marker, and rejected Incubator or Guard candidates are not persisted.
- There is no calculation broker. The Coach and Guard backends have no tools:
  each call receives one packet and returns one JSON object.
- The local page receives only renderer text and closed codes; it never
  receives a model stream or a raw candidate field.
- Completion creates no review candidate, so there is none to expose.
- An invalid step creates a Coach-origin obstacle that applies across the whole practice. No learner command edits it, and a learner claim cannot clear it. While it is open, no conclusion is reviewed. Only a later step, not an exploratory idea, that the Coach judges `valid_so_far` and that both the Coach and the Guard mark `resolves_obstacle=true` resolves the earliest open obstacle.

## Failure behavior

There is no retry. On Guard refusal, a schema mismatch (every closed field is
type-checked before its membership check), an unverified quote, a scope,
route-progress, or obstacle-repair disagreement, a timeout, an unavailable or
unconfigured backend, or a malformed response, render exactly:

> 本轮反馈无法在安全边界内生成。请把当前步骤再拆小一些，并写明所用依据。

Persist only a closed failure event with the problem ID and the error class name. Do not persist rejected candidate prose, reasoning, prompts, subprocess stderr, or raw tool output, and store no learner node.

The other model-backed operations fail closed in the same way with their own
fixed outcomes: admission stores `UNVERIFIED`; research incubation renders
“本次研究孵化无法在安全边界内生成，路线没有改变。”; a hint failure renders the
sentence above and leaves eligibility unchanged; a lenient-audit failure
leaves completion `NOT_COMPLETE` with the obligation
“两位独立复核意见不一致”. A store failure aborts its transaction so nothing is
committed; the chat then shows only a bracketed error-class line.

## Local exposure and capabilities

The chat and command line are local processes for one user. There is no
manager or learner role and no per-practice capability: whoever controls the
terminal or holds the page link is the learner.

The local page (`teacher.py serve`) binds to `127.0.0.1`, selects a random port
unless one is given, and mints one random token at each start. The token lives
only in process memory and in the page URL fragment, which the page reads into
memory and then removes from the address bar. A restart invalidates every
earlier link. The store, errors, and logs contain no token value, and HTTP
access logs are suppressed.

Every page request must carry the token in `X-Teacher-Harness-Token`; a wrong
or missing token receives the same HTTP `403` before any lookup. Request bodies
nominate no role. A page submission passes through the same gate and Coach as
the chat.

Any slash-command token in learner step text is rejected by the input gate
before any model call; ordinary notation such as `a/b` does not match the
command grammar.

Do not support remote binding, CORS, persistent tokens, or network multi-user
accounts. This loopback token is not sufficient Internet authentication. A
future network deployment requires accounts, authenticated identities,
revocation, and auditable authorization designed for that environment.
