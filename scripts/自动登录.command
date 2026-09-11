#!/bin/zsh
cd "${0:A:h}/.." || exit 1
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
uv run --locked --extra login python -m fdu_yjsxk.selenium_login --export-courses
code=$?
echo "登录入口结束（退出码 $code），按回车关闭。"
read
exit "$code"
