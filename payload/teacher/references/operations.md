# Operations

All commands run from this Skill's directory. `python3` may be `python` on
Windows.

## Setup

```sh
python3 scripts/teacher.py setup --base-url <OPENAI_COMPATIBLE_ROOT> --model <MODEL> \
  [--guard-model <MODEL>] [--read-root <NOTES_OR_PAPERS_DIR> ...] [--network on|off] [--model-guard on|off]
python3 scripts/teacher.py setup --api-key-stdin     # optional; otherwise export TH_API_KEY
python3 scripts/teacher.py setup --show
```

Configuration and the store live in the platform user directory (macOS
`~/Library/Application Support/teacher/`, Linux `~/.config/teacher/` and
`~/.local/state/teacher/`, Windows `%APPDATA%\teacher\` and
`%LOCALAPPDATA%\teacher\`). `TEACHER_CONFIG_DIR` and `TEACHER_STATE_DIR` override
them. The key is never written into the configuration file.

## Index the material the harness may read

```sh
python3 scripts/teacher.py index <DIR>                         # dry run: counts and plan_sha256
python3 scripts/teacher.py index <DIR> --apply <PLAN_SHA256>   # index exactly that plan
```

Markdown, text, notebooks, code and PDFs (`pdftotext` is used when present) are
split into sections. The index only locates; reading always re-opens the
current file. Re-run after large changes; a changed or missing section is
reported as such.

## Standalone use

```sh
python3 scripts/teacher.py chat          # interactive
python3 scripts/teacher.py ask "问题"     # one turn
python3 scripts/teacher.py serve         # local page; prints a URL with a one-time token
```

Chat commands: `/more N`, `/ask N`, `/switch N`, `/archive`, `/project`,
`/set`, `/confirm`, `/coach 题目`, `/index DIR`, `/status`, `/help`, `/quit`.
Practice: plain text, `/idea`, `/conclude`, `/route`, `/hint`, `/incubate`,
`/done [lenient]`, `/exit`.

## Attached use

The host agent frames the request, investigates with its own tools, then:

```sh
python3 scripts/teacher.py frame-check --brief "<原话>" --draft frame.json
python3 scripts/teacher.py check-answer --brief "<原话>" --kind <KIND> \
  --answer answer.json --evidence evidence.json [--steps N]
```

`frame.json` and `answer.json` use exactly the shapes in
[need-discovery.md](need-discovery.md) and [evidence-model.md](evidence-model.md).
`evidence.json` is a list of `{"id": "E1", "kind": "retrieved_source" |
"executed_check", "locator": "<relative path under a read root, or URL>",
"text": "<the excerpt>", "returncode": <int, for checks>}`. `check-answer` exits
0 and prints the text the agent must deliver, or exits 3 with closed risk codes.

## Assets

```sh
python3 scripts/teacher.py archive                                    # proposal + plan_sha256
python3 scripts/teacher.py archive --choice verified_only --plan <SHA> # or all / none
python3 scripts/teacher.py cognition                                  # what the model receives
python3 scripts/teacher.py status
```

## Research state (objectives, claims, reviews, gates)

```sh
python3 scripts/teacher.py engine -- status --json
python3 scripts/teacher.py engine -- submit-claim claim.json
python3 scripts/teacher.py engine -- review-claim <RC-id> --independent
python3 scripts/teacher.py engine -- review-claim <RC-id> --decision accepted --reviewer-kind human
python3 scripts/teacher.py engine -- promote <RC-id>
python3 scripts/teacher.py engine -- assess --record-id <RC-id> [--consult]
python3 scripts/teacher.py engine -- confirm <AS-id>
python3 scripts/teacher.py engine -- maintenance
python3 scripts/teacher.py engine -- chain --json
```

`--json` belongs before the subcommand when calling `python3 -m th.cli`
directly; through `engine --` pass it as shown.

## Diagnose

| Symptom | Check |
| --- | --- |
| every answer ends in the fixed failure sentence | `setup --show`: endpoint, model and key file; the backend fails closed when any is missing |
| “没有配置模型后端” at start | run `setup` with `--base-url` and `--model`, and provide the key |
| an answer never cites your notes | `status` → `retrieval.roots`; run `index DIR` and `--apply` |
| a cited note shows `changed_since_index` or `stale` | re-index that directory |
| `fetch_url` is always refused | network is off, or the host is not in `network.allow_domains` |
| a write is refused | read the closed code; nothing was written and both heads are unchanged |
| a claim shows `needs_review` | a dependency moved; run `engine -- maintenance` |
| an assessment is refused | it is stale; take a new assessment |
| hashes disagree | `engine -- chain --json`, and the package's `tools/checksums.py` |

## Recovery

- A refused operation writes nothing. There is no partial state to roll back.
- A failed answer stores only a closed failure receipt.
- An archive proposal binds the list it showed; if new candidates arrived, show it again.
- An assessment binds the two revisions it was taken against; any later work invalidates it.
