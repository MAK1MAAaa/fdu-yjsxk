#!/bin/zsh
cd "${0:A:h}/.." || exit 1
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
uv run --locked python -m fdu_yjsxk.catalog_server
