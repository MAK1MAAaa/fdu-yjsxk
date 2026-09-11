#!/bin/zsh
cd "${0:A:h}/.." || exit 1

fdu_uv="$(command -v uv 2>/dev/null)"
if [ -z "$fdu_uv" ]; then
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then
      fdu_uv="$candidate"
      break
    fi
  done
fi

if [ -z "$fdu_uv" ]; then
  echo "找不到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/"
  echo "按回车键关闭..."
  read
  exit 1
fi

if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -dimsu "$fdu_uv" run --locked python grab.py --single
else
  "$fdu_uv" run --locked python grab.py --single
fi
fdu_exit=$?
echo ""
echo "单课程捡漏结束（退出码 $fdu_exit）"
echo "0 = 成功、已选或未开始就取消；1 = 未选上或发生错误；130 = 手动中止。"
echo "请到选课系统的已选课程页核对结果。按回车键关闭..."
read
exit "$fdu_exit"
