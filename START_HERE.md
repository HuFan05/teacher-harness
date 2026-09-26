# Teacher 1.0.0

Teacher 是面向计算机科学与人工智能学习、研究的本地研究型老师。你不必先把问题想清楚：它先弄清你真正想问什么（必要时只问你一个选择题），再查你自己的笔记、研究资料库、论文和网络，然后给出简短的回答，每一条都写明依据什么、证据有多强、不能推出什么、还有什么不知道；值得保留的结论和来源会自动整理成候选，你只需决定一次要不要归档。

需要 Python 3.10 或更新版本，不需要安装任何第三方包。

有两种用法，承诺不同，不要混为一谈：

- **独立使用（推荐先用这个）**：Teacher 自己驱动模型，流程、检查、要不要反问、能不能显示都由程序规则决定，模型只回答封闭的问题。第一次运行：

  ```sh
  cd payload/teacher/scripts
  python3 teacher.py setup --base-url <你的 OpenAI 兼容地址，例如 https://host/v1> --model <模型名> --read-root <笔记或论文目录>
  export TH_API_KEY=<你的密钥>          # 或者：python3 teacher.py setup --api-key-stdin
  python3 teacher.py index <笔记或论文目录>   # 按提示再带 --apply 执行一次
  python3 teacher.py chat
  ```

  macOS 上也可以双击 `teacher.command`。本地网页界面：`python3 teacher.py serve`。

- **附着到已有 agent**：把七个技能装进 Codex、Claude Code 或其他支持 Skill 的 agent。agent 用自己的工具调研，但框定问题和最终答案都要经过同一套程序检查。这是行为约束，不是边界。macOS/Linux 在本目录运行 `sh install.sh`，Windows 双击 `INSTALL_WINDOWS.cmd`；也可以直接：

  ```sh
  python3 install.py --agent claude --yes      # Claude Code
  python3 install.py --agent codex --yes       # Codex
  ```

  其他 agent 请把 `AGENT_INSTALL.md` 交给它。目标目录已有同名技能时安装会停下（退出码 21），确认后再加 `--replace`，旧版本会先备份。

安装不需要联网，也不会自动索引你的资料。检查安装：`python3 install.py --doctor --agent claude`；卸载：`python3 install.py --uninstall --agent claude --yes`（默认保留配置、备份和研究库）。

配置、密钥文件和研究库都放在用户目录，不在本包里：macOS 为 `~/Library/Application Support/teacher/`，Linux 为 `~/.config/teacher/` 与 `~/.local/state/teacher/`，Windows 为 `%APPDATA%\teacher\` 与 `%LOCALAPPDATA%\teacher\`。密钥不会写进配置文件。

日常用法见 `docs/USAGE.md`；资产维护、诊断和更新见 `docs/MAINTENANCE.md`。
