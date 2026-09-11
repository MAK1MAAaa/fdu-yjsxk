#!/bin/zsh
# 开抢前先跑这个做自检：检查 Cookie 是否有效、课程代码是否正确
# 不会提交任何选课请求，可以放心反复运行
cd "${0:A:h}/.." || exit 1

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

"$UV" run --locked python grab.py --dry-run

echo ""
echo "按回车键关闭窗口..."
read
