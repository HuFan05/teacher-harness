# cs-ai-coach canonical terminology

These definitions are normative for this Skill. Files and JSON fields are storage carriers, not the semantic objects themselves.

## `coaching_profile`

### 简要定义

The frozen disclosure and assistance policy for one CS/AI Coach interaction.

### 规范定义

It distinguishes guided acceleration from strict no-leak coaching and fixes what routine derivation, hints, validation, and answer disclosure are permitted.

### 构成字段

`profile_id`, `disclosure_policy`, `allowed_assistance`, `stop_conditions`.

### 权威等级

A Skill-owned canonical concept. Its validated registry entry and source-bound artifacts are authoritative for workflow decisions; summaries and UI labels are derived.

### 生命周期规则

It is created only at its documented workflow boundary, changes through the owning validated transition, and retains enough prior identity and evidence for recovery and audit.

### 允许的变化

Status, evidence pointers, derived views, and implementation carriers may change through the owning workflow while identity, scope, authority, and recorded history remain explicit.

### 禁止的变化

Do not silently rename it, broaden its scope or authority, erase history, lower its evidence/completion rule, or reuse a deprecated label for a different concept.

### 不得混淆

It is not claim truth status. Matching prose or filenames do not make two concepts identical.

### 完成关系

The object reaches its local completed state only when every constitutive field and owning validator succeeds. That local completion does not by itself complete the user's larger project.

### 机器绑定

Global identity `personal:cs-ai-coach#coaching_profile`, the terminology asset hash, owning source tree hash, and workflow-specific IDs/hashes.

## `attempt_graph`

### 简要定义

The persistent graph of user-proposed technical states, checks, corrections, and dependencies.

### 规范定义

It preserves the user's route, distinguishes routine repairs from new ideas, and supports recovery without treating a model suggestion as the learner's attempt.

### 构成字段

`nodes`, `edges`, `origins`, `verdicts`, `recovery_head`.

### 权威等级

A Skill-owned canonical concept. Its validated registry entry and source-bound artifacts are authoritative for workflow decisions; summaries and UI labels are derived.

### 生命周期规则

It is created only at its documented workflow boundary, changes through the owning validated transition, and retains enough prior identity and evidence for recovery and audit.

### 允许的变化

Status, evidence pointers, derived views, and implementation carriers may change through the owning workflow while identity, scope, authority, and recorded history remain explicit.

### 禁止的变化

Do not silently rename it, broaden its scope or authority, erase history, lower its evidence/completion rule, or reuse a deprecated label for a different concept.

### 不得混淆

It is not a complete correctness argument of a solved problem. Matching prose or filenames do not make two concepts identical.

### 完成关系

The object reaches its local completed state only when every constitutive field and owning validator succeeds. That local completion does not by itself complete the user's larger project.

### 机器绑定

Global identity `personal:cs-ai-coach#attempt_graph`, the terminology asset hash, owning source tree hash, and workflow-specific IDs/hashes. In the Teacher harness its carriers are the `coach_nodes` rows (nodes, origins, verdicts), the exploratory-idea `connects` link and the obstacle `blocks` and `resolved_by` links (edges), and the store's execution-head revision (recovery head).
