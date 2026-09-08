#!/bin/zsh
# 一键抢课 —— 双击即可运行
cd "${0:A:h}" || exit 1

UV="$(command -v uv 2>/dev/null)"
if [ -z "$UV" ]; then
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then
      UV="$candidate"
      break
    fi
  done
fi

if [ -z "$UV" ]; then
  echo "找不到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/"
  echo ""
  echo "按回车键关闭..."; read
  exit 1
fi

echo "先执行登录态自检，不会提交选课请求..."
"$UV" run --locked python grab.py --dry-run
check_code=$?

if [ "$check_code" -ne 0 ]; then
  echo ""
  echo "=================================="
  echo " 自检失败，未启动选课进程"
  echo " 请确认："
  echo " 1. Edge 已登录 yjsxk.fudan.sh.cn"
  echo " 2. 终端已获完全磁盘访问权限"
  echo " 3. 开启权限后已彻底退出并重开终端"
  echo "=================================="
  echo "按回车键关闭窗口..."
  read
  exit "$check_code"
fi

echo ""
echo "自检通过，按 config.json 中的 start_time 开始、end_time 停止。"
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -dimsu "$UV" run --locked python grab.py
else
  "$UV" run --locked python grab.py
fi
code=$?

echo ""
echo "=================================="
echo " 脚本结束（退出码 $code）"
echo " 退出码 0 = 全部拿下；1 = 有课没抢到"
echo "=================================="
echo "按回车键关闭窗口..."
read
