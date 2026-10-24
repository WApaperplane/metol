#!/bin/bash
# push-github.sh —— 用 PAT 把当前 HEAD 推到 GitHub 的 nxwa 分支
#
# 用法:
#   GITHUB_TOKEN=ghp_xxx bash tools/push-github.sh     # 令牌走环境变量，不进历史
#   bash tools/push-github.sh ghp_xxx                  # 也可以当参数传（会进 shell 历史）
#
# 为什么这么写（2026-10 实测）:
#   - GCM（credential.helper=manager）凭据已失效，且会弹窗把进程挂死 ⇒ 必须 -c credential.helper= 清空
#   - 令牌内嵌 URL 会被写进 .git/config 或日志 ⇒ 改用 http.extraheader 传 Authorization
#   - 本机 hosts 把 github.com 指到 127.0.0.1，靠本地加速器在 443 上应答；**不要**再加 v2ray 代理参数
set -uo pipefail
T=${GITHUB_TOKEN:-${1:-}}
REPO=${REPO:-https://github.com/WApaperplane/metol.git}
BRANCH=${BRANCH:-nxwa}

if [ -z "$T" ]; then
	echo "用法: GITHUB_TOKEN=<token> bash $0   （或 bash $0 <token>）" >&2
	exit 2
fi

cd "$(dirname "$0")/.." || exit 1

AUTH=$(printf 'x-access-token:%s' "$T" | base64 | tr -d '\n')
GIT_TERMINAL_PROMPT=0 git -c credential.helper= \
	-c http.extraheader="Authorization: Basic $AUTH" \
	push "$REPO" "HEAD:$BRANCH"
rc=$?
echo "push rc=$rc"
exit $rc
