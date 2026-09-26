# Teacher

面向计算机科学与人工智能学习、研究的本地研究型老师：先弄清你真正想问什么，再查你的笔记、研究资料库、论文和网络，然后简短作答——每条都写明依据、证据强度、不能推出什么、还有什么不知道；值得保留的结论自动整理成候选，由你一次决定是否归档。

需要 Python 3.10+，不依赖任何第三方包。

## 两种用法

| 用法 | 怎么启动 | 适合 |
| --- | --- | --- |
| 独立使用：Teacher 驱动模型，流程与检查由程序决定 | `python3 payload/teacher/scripts/teacher.py chat`（macOS 可双击 `teacher.command`） | 日常提问、读论文、弄懂概念、练习 |
| 附着到 agent：技能装进 Codex / Claude Code 等 | `python3 install.py --agent codex --yes` 或 `--agent claude` | 需要 agent 上网、跑代码、改笔记的长时间研究 |

第一次独立使用前运行一次：

```sh
python3 payload/teacher/scripts/teacher.py setup --base-url <OpenAI 兼容地址> --model <模型名>
python3 payload/teacher/scripts/teacher.py setup --api-key-stdin    # 密钥只存在本机用户目录
```

- 入门：[START_HERE.md](START_HERE.md)
- 使用说明：[docs/USAGE.md](docs/USAGE.md)
- 维护手册：[docs/MAINTENANCE.md](docs/MAINTENANCE.md)
- 给 agent 的安装手册：[AGENT_INSTALL.md](AGENT_INSTALL.md)
