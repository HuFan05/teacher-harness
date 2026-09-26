# Harness contract

The hardened practice mode is part of the Teacher standalone harness in the
sibling `teacher` Skill. Its code is `teacher/scripts/th/coach.py`; its closed
vocabularies are the `COACH_*` constants in `teacher/scripts/th/constants.py`;
its tables are defined in `teacher/scripts/th/store.py`. This Skill bundles no
harness code. The practice has no manager role, calculation broker, job lease,
or generated post-solution review.

## SQLite tables

Practice state lives in the Teacher store, `teacher.sqlite3` in the platform state directory: `~/Library/Application Support/teacher/` on macOS, `${XDG_STATE_HOME:-~/.local/state}/teacher/` on Linux, and `%LOCALAPPDATA%\teacher\` on Windows. `TEACHER_STATE_DIR` or `teacher.py --store <path>` selects another store. Two tables hold the practice:

- `coach_problems(problem_id, admission, epistemic, state, body, created_at, updated_at)`: one row per submitted problem; `body` holds the problem text and its SHA-256, the off-topic counter, the ordinal of the last route-summary offer, and, once sealed, the completion status, the exit mark and time, or the time it was superseded;
- `coach_nodes(node_id, problem_id, ordinal, origin, role, status, body, created_at)`: one row per learner node or Coach node of a problem, ordered by `ordinal`.

Every practice write goes through the store's compare-and-swap transaction on
the execution head: the problem row and the nodes of one step commit together
or not at all, and each commit advances the execution head and appends an
`execution_advanced` event whose action is `coach_superseded`,
`coach_admitted`, `coach_off_topic`, `coach_step`, `coach_hint`,
`coach_incubation`, `coach_completed`, or `coach_exited`. Node rows are
upserted by `node_id`; when an obstacle is resolved its row is rewritten with
the new status. A failed step review appends only a `coach_step_failed` event.

## Problem initialization

`/coach <problem>` in chat or on the local page, or `teacher.py coach-start
"<problem>"`, first seals a practice still in `HARD_LOCK` (state `SEALED`,
with the time it was superseded) and then runs two separate backend calls. The
reviewer `coach_admit` receives the problem, the closed admission and
epistemic vocabularies, and a fixed instruction not to solve, hint, repair, or
give a counterexample. The auditor `coach_audit` receives the same packet and
the reviewer's closed fields. The reviewer runs on the Coach backend and the
auditor on the Guard backend.

The reviewer output contains exactly `admission`, `epistemic`, and
`certainty`. The auditor returns exactly `allow`, `consistent`, and
`risk_codes`. The Harness type-checks both key sets and vocabularies before
saving anything and stores the reviewer's admission only when the auditor
returns `allow=true` and `consistent=true`; otherwise it stores `UNVERIFIED`.
The response and store contain no model prose, reasoning, prompt,
counterexample, or proposed correction.

Only a `READY` problem opens a practice in `HARD_LOCK`. Its epistemic code may
be `NONE`, `KNOWN_OPEN`, or `TRUTH_UNVERIFIED`. Every other admission is stored
`SEALED` with epistemic code `NONE`. The admission renders one fixed sentence:

| Stored result | Rendered sentence |
| --- | --- |
| `READY` + `NONE` | 初始化检查已通过。请写出你准备尝试的第一步，并说明这一步依据什么；在你提交尝试前，Coach 不提供解题内容。 |
| `READY` + `KNOWN_OPEN` or `TRUTH_UNVERIFIED` | 题目已准入探索，但它的真值没有得到认证；局部成功不能当作整个论断成立的证明。请写出你准备尝试的第一步，并说明依据。 |
| `NOT_CS_AI` | 这不是一个计算机科学或人工智能的练习问题，Coach 不会为它建立训练。 |
| `NEEDS_CLARIFICATION` | 题目还不能唯一理解：缺少目标、定义、输入约定、量词或关键条件。请补全题目后重新提交。 |
| `INCORRECT_AS_STATED` | 按现在的表述，题目的前提或要求不成立。请核对题目原文后重新提交。 |
| `UNVERIFIED` | 题目的结构检查没能可靠完成，训练暂不开始。请稍后重试，或把题目写得更完整。 |

An empty problem is refused with the `NEEDS_CLARIFICATION` sentence before any
model call and seals nothing. The latest submitted problem is the current
practice; at most one practice is in `HARD_LOCK` at a time.

## Commands and surfaces

`teacher.py chat` and the local page recognise a command only as the first
token of a line. The practice commands are listed below; plain text is a step
only while a practice is in `HARD_LOCK`.

| Chat and page | Command line | Behavior |
| --- | --- | --- |
| `/coach <problem>` | `coach-start "<problem>"` | Seal any practice in `HARD_LOCK`, then run fail-closed admission |
| plain text | `coach-step "<text>"` | Review one `local_step` |
| `/idea N <text>` | `coach-step "<text>" --role exploratory_idea --connects N` | Review one `exploratory_idea` connected to learner step `N` (`0` is the problem) |
| `/conclude <text>` | `coach-step "<text>" --role conclusion` | Review one `conclusion`; refused while an obstacle is open |
| `/route` | `coach-route` | Render the deterministic route summary without a model or state change |
| `/hint` | `coach-hint` | Request the single guarded hint |
| `/incubate <kind> [N ...]` | `coach-incubate <kind> [N ...]` | Anchored research incubation; `<kind>` is `targeted_question`, `obstacle_map`, or `conditional_hypothesis` |
| `/done` or `/done lenient` | `coach-done [--policy strict\|lenient]` | Run the completion gate (default strict) |
| `/exit` | `coach-exit` | Seal and mark the practice exited without a model call |

In chat, `/idea` without a numeric step prints
“用法：/idea 步骤编号 内容（0 表示题目本身）”. The global `--json` option
(`teacher.py --json coach-step ...`) prints the result fields, for example
status, admission, epistemic code, problem ID, decision, first error, and the
rendered text, instead of the text alone.

While a practice is in `HARD_LOCK`, the chat accepts only the practice commands
plus `/help`, `/status`, and `/quit`; any other command, including `/ask`,
`/switch`, `/more`, `/project`, `/archive`, and `/index`, receives
“练习进行中只能用：{commands}。要离开练习先 /exit。”. The page accepts only the
practice commands and refuses any other with
“练习进行中只能用练习命令；要离开练习先 /exit。”. With no practice in `HARD_LOCK`,
plain text is a Teacher question, chat `/exit` prints
“没有正在进行的练习。退出 Teacher 用 /quit。”, and `/quit` leaves the chat. A
practice still in `HARD_LOCK` when the chat ends stays open in the store.
Without a backend command the page runs read-only and accepts no submission.

The command-line `coach-*` operations are separate invocations. The
command-line `teacher.py ask` goes through the same protected-problem check as
chat and the page.

There is no role authorization: the harness has one local user. The page
requires its per-start loopback token on every request, as described in
[security-model.md](security-model.md). Each command runs synchronously in the
calling process; there is no job queue or lease.

## Step review

A step passes the deterministic input gate and the role checks in
[training-policy.md](training-policy.md#input-gate) before any model call. The
Coach review `coach_review` then receives the problem, the last 12 learner
nodes (ordinal, role, status, and text), the category of the first open
obstacle or null, the current step and role, for an exploratory idea the
connected step's text (at most 600 characters) or the marker `problem`, the
closed decision and first-error vocabularies, and a fixed instruction to judge
only this step against the learner's own record, copy the focus quote verbatim
from the step, set `resolves_obstacle` only when this step repairs the open
obstacle, and never propose a method, object, or next step.

The Harness accepts the review only when its keys are exactly `decision`,
`first_error`, `focus_quote`, `route_progress`, `scope`, and
`resolves_obstacle`; each closed value is a string of its vocabulary, or a
boolean for `resolves_obstacle`, checked by type before membership;
`first_error` is null or a first-error code and is present when the decision
is `invalid`; and `focus_quote` is null or a nonblank substring of the current
step of at most 200 characters. The Guard `coach_guard` then receives the same
packet and the Coach's closed fields and must return exactly `allow`,
`risk_codes`, `route_progress`, `scope`, and `resolves_obstacle`, with
`allow=true`, the same route progress and scope as the Coach, and, when an
obstacle is open, the same `resolves_obstacle`. The Guard is instructed to
judge these independently rather than copy the Coach; the Harness can only
require equality.

When both agree on `scope=off_topic`, the Harness increments the practice's
off-topic counter and renders the first-time reminder or, afterwards, the
fixed refusal, both in [training-policy.md](training-policy.md). For
`not_applicable`, it stores nothing and renders
“这条输入不属于步骤检查。” followed by “请提交一个具体步骤，并说明依据。”.
Otherwise it commits, in one transaction, one learner node with the step's
text, role, decision, first error, status (`verified` for `valid_so_far`,
`refuted` for `invalid`, `unresolved` otherwise), attempt flag (true for
`valid_so_far`, `invalid`, and `needs_justification`), and connection; for
`invalid`, one open Coach `obstacle` that blocks it; when the step is not an
exploratory idea, is judged `valid_so_far`, and both calls return
`resolves_obstacle=true`, the earliest open obstacle rewritten as `resolved`
with the resolving node and ordinal; and, when a route-summary offer is made,
the ordinal of the offer.

The renderer prints these lines in order. The second, third, and fourth appear
only when an error code, a quote, or a resolution is present; the sixth line is
the first form for `invalid`, `needs_justification`, or `unclear` and the
second form otherwise; the seventh appears only when the route-summary offer
condition holds:

```text
{decision sentence}
第一个能确定的问题：{category}。
对应你写的：“{quote}”
先前记录的那个错误已由这一步修复。
（{route-progress label}）
请修复或重新陈述这一步，并写明它依据的是哪些已经写出的内容。 | 请提交下一步，并说明依据。
你已经在同一处卡了几轮。需要看一下只含你自己步骤的路线整理吗？输入 /route。
（本段由确定性渲染器生成，不含模型撰写的文字。）
```

Any key-set, type, or vocabulary violation, unverified quote, Guard refusal,
disagreement, or backend failure renders
“本轮反馈无法在安全边界内生成。请把当前步骤再拆小一些，并写明所用依据。” and stores
no node.

## Completion

`/done` and `coach-done` implement the gate in
[training-policy.md](training-policy.md#hardened-harness-completion-review).
Strict completion is derived from the stored nodes: no open obstacle, at least
one `verified` `local_step`, and a `verified` `conclusion` recorded after every
obstacle, every obstacle resolution, and a verified `local_step`. Lenient
completion needs no open obstacle and at least one `verified` `local_step`,
then two isolated `coach_audit` calls, one through the Coach backend and one
through the Guard backend, each receiving the problem, `policy=lenient`, and
the learner route; both must return `allow=true` and `consistent=true`. A
learner's completion claim is never a store transition.

A passing result rewrites the problem row as `SEALED` with the completion
status and renders the fixed completion sentence and the learner's route map
under “试错路线图：”. A failing result changes nothing and appends the route
summary to the fixed sentence. There is no assessment record, confirmation
step, snapshot hash, generator, or post-solution Guard; the Harness never
produces review prose.

An invalid step creates a deterministic Coach-origin obstacle that blocks it.
The completion gate searches every obstacle of the practice. No learner
command removes an obstacle or supplies a resolution; only a guarded
resolution as described above clears one.

## Exited practices and the Teacher answer path

`/exit` marks the practice exited. The Teacher answer path, `Teacher.ask` and
`Teacher._answer` in `teacher/scripts/th/teach.py` (used by plain chat and page
questions, `/ask`, `/switch` and `teacher.py ask`), calls
`protected_problem_overlap` in `th/coach.py` before any model call. A problem is
protected while it is in `HARD_LOCK` and after it is sealed without passing
completion (exited, or superseded by a new `/coach`). The request is refused
when its lowercase ASCII words of at least two characters and CJK character
bigrams share at least half of the smaller term set with a protected problem,
with
“这道题属于练习模式（正在进行，或未通过完成检查就结束了）。回答模式不会直接解答它；可以换一道题，或用 /coach 回到练习。”
A problem sealed by a passed completion gate is not protected.

## Backend isolation

The harness talks to the configured backend command, by default the bundled
chat-completions adapter in `teacher/scripts/backends/`, over one JSON object
on stdin and one on stdout. Every call (`coach_admit`, `coach_audit`,
`coach_review`, `coach_guard`, `coach_hint`, `coach_incubate`) starts a fresh
child process, so no conversation state is shared between calls or between
the Coach and the Guard. The payload travels on stdin, not in the process
arguments. The Guard backend process runs with `TH_ROLE=guard`, which selects
the configured guard model.

The backend has no tools, shell, web, or MCP capability: it receives a packet
and returns JSON. The harness validates every result against the closed key
set; a nonzero exit, empty or malformed output, missing result, or timeout is
a backend failure and fails closed.

## Structured records

The Coach review contains only the closed decision and first-error values,
`scope`, `route_progress`, `resolves_obstacle`, and a learner-quote candidate.
The renderer accepts the quote only after confirming it is a substring of the
current learner input. The Guard returns only `allow`, closed `risk_codes`,
`scope`, `route_progress`, and `resolves_obstacle`.

The hint call returns exactly `{"hint": "..."}`. The Harness collapses
whitespace and accepts one line of at most 120 characters with at most two `$`
signs, then asks the Guard (with `mode=hint`, the obstacle category, the last
eight learner nodes, and every earlier hint) for `allow=true` and
`scope=current_problem`. The accepted text is stored as a Coach `hint` node and
rendered as “提示（一次）：{hint}” followed by
“（本提示不属于 HARD_LOCK 的绝对输出保证。）”. Refusal:
“现在没有可用的提示：需要先有一个已记录的障碍，并且在上次提示之后提交过新的尝试。”

Research incubation uses a separate record. Before any call, the Harness
checks the kind, maps the learner's step numbers to learner nodes, and rejects
out-of-range, duplicate, or wrongly counted anchors. The Incubator receives the
kind, the chosen nodes (ID and at most 600 characters of text each), and the
allowed question codes, and returns exactly `question_code`,
`primary_node_id`, `secondary_node_id`, and `certainty`, each type-checked. The
Guard, with `mode=incubation`, must return `allow=true` and
`scope=current_problem`. `obstacle_map` invokes no model and reuses the
deterministic route summary.

The research renderer copies at most 120 characters from each selected learner
node into the fixed templates listed in
[training-policy.md](training-policy.md#anchored-research-incubation) and adds
“（本段由固定模板与你的原话生成，不含模型撰写的文字。）”. It never renders Incubator
prose, creates a learner node or obstacle, updates completion state, or grants
hint eligibility. A conditional hypothesis is visibly marked unverified and is
not stored; the learner must confirm and resubmit it as a step. Other
refusals are “孵化类型只能是 targeted_question、obstacle_map 或 conditional_hypothesis。”,
“先提交至少一个你自己的步骤，再请求孵化。”, “锚点必须是你路线里的步骤编号。”,
“请给一个或两个不同的步骤编号。”, and “条件性假设需要恰好两个步骤编号。”.

The Harness stores only an empty `incubation` marker for a successful
model-backed incubation. A second model-backed incubation is refused with
“上一次孵化之后你还没有提交新的步骤；先推进一步再来。” until a later learner step is
stored. Deterministic obstacle maps do not call the Incubator and remain
available without resetting that gate.

The route summary has no model classifier. `/route` reads the stored learner
nodes directly and can emit only recorded learner text, stored statuses, the
first open obstacle's category, fixed labels, and the three fixed choices.

The lenient completion audits return only `allow`, `consistent`, and
`risk_codes`. No completion call returns text.

## Calculations

The coach path has no calculator, calculation broker, computation adapter,
shell, or MCP capability, and the Coach and Guard cannot invoke one. Ordinary
host-agent `GUIDED` chat may reason through a uniquely implied routine
operation itself. It may delegate to `$cs-ai-computation` only when the
expression, program, or experiment and the operation satisfy that Skill's
gate; `STRICT` requires the learner to state both exactly. The Harness does
not load that Skill. A learner who needs a computation during a Harness
practice runs it outside the practice and submits the result as a step with
its basis.

## Turn deadline

There is no single shared turn deadline. Each backend call runs under the
backend timeout (default 240 seconds, set with `teacher.py setup --timeout`). A
step review makes at most two calls, the Coach and then the Guard, so a slow
backend can take up to twice that timeout before the fixed failure sentence. A
timeout aborts the child process and fails closed; the practice stays in
`HARD_LOCK`.
