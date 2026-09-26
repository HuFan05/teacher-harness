#!/bin/bash
# 双击开始对话。密钥只在本次会话里使用，不写入任何文件。
cd "$(dirname "$0")/payload/teacher/scripts" || exit 1
if [ -z "$TH_API_KEY" ] && [ ! -f "$HOME/Library/Application Support/teacher/api_key" ]; then
  echo "没有找到密钥。可以把 export TH_API_KEY=... 写进 ~/.zshrc，或运行 python3 teacher.py setup --api-key-stdin。"
  read -r -s -p "现在直接粘贴密钥（不回显，只用于本次）：" TH_API_KEY
  echo
  export TH_API_KEY
fi
exec python3 -B teacher.py chat
