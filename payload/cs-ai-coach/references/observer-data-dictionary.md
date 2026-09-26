# cs-ai-coach Observer阶段字典

目录版本为`cs-ai-coach/v1`，指标契约为`timing/v1`。工作流阶段用于比较模型与工具往返中的实际步骤；脚本阶段只记录生产入口，不记录测试、一次性迁移脚本或纯工具库。

## 阶段

| 阶段 | 含义 |
| --- | --- |
| `workflow.startup` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `retrieve` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `verify_live` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `plan_change` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `mutate` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `validate` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `version_control` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `final_response` | 记录该标准工作流阶段的墙钟区间；只在实际进入时设置。 |
| `cs-ai-coach.script.run` | 记录一个正常生产脚本入口的完整子进程墙钟时间。 |

## 允许字段

| 字段 | 类型 | 边界 |
| --- | --- | --- |
| `mode` | `name` | 只记录不含业务内容的分类或非负计数。 |
| `operation` | `name` | 只记录不含业务内容的分类或非负计数。 |
| `write` | `boolean` | 只记录不含业务内容的分类或非负计数。 |
| `file_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |
| `candidate_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |
| `byte_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |
| `harness_call_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |
| `result_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |
| `change_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |
| `warning_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |
| `error_count` | `nonnegative_integer` | 只记录不含业务内容的分类或非负计数。 |

禁止记录`path`、`title`、`note_title`、`query`、`body`、`excerpt`、`heading`、`diff`、`command`、`exception_text`、`resource_id`、`raw_file_hash`和`tool_output`。包装器失败或超时时，不得改变原命令的标准输出、标准错误、退出码或文件行为。

## 生产入口叶阶段

本 Skill 没有捆绑的生产入口叶阶段：练习 harness 的入口 `teacher.py` 属于同级 `teacher` Skill，本 Skill 只捆绑校验器与包装器。经包装器运行本 Skill 的脚本时使用`cs-ai-coach.script.run`。这些阶段区分正常入口，不为测试、一次性迁移脚本或纯工具库创建记录。
