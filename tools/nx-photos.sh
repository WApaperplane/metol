#!/bin/bash
# nx-photos.sh —— 相机照片：列清单 / 增量取回 / 生成本地相册
#
# 用法:
#   ./nx-photos.sh list                    列出机内照片
#   ./nx-photos.sh sync [本地目录]          增量取回（默认 ./photos，已有同名同大小则跳过）
#   ./nx-photos.sh album [本地目录]         生成本地 HTML 相册并打开
#   ./nx-photos.sh get <文件名> [本地目录]   取单张
#
# 环境变量: NXHOST(192.168.0.106) NX_SSH_PORT(22) NX_SSH_KEY
#           NX_PHOTO_DIR(机内照片目录，默认 /opt/storage/sdcard/DCIM/100PHOTO)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
KEY=${NX_SSH_KEY:-$ROOT/test_server/dropbear/ssh/nx500_ed25519}
HOST=${NXHOST:-192.168.0.106}
PORT=${NX_SSH_PORT:-22}
RDIR=${NX_PHOTO_DIR:-/opt/storage/sdcard/DCIM/100PHOTO}

SSH=(ssh -p "$PORT" -i "$KEY" -o IdentitiesOnly=yes
     -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
     -o ConnectTimeout=10 -o LogLevel=ERROR "root@$HOST")
SFTP=(sftp -P "$PORT" -i "$KEY" -o IdentitiesOnly=yes
      -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
DEST="root@$HOST"

cmd=${1:-list}

case "$cmd" in
list)
    "${SSH[@]}" "cd '${RDIR}' 2>/dev/null && ls -lh *.JPG *.jpg 2>/dev/null"
    "${SSH[@]}" "cd '${RDIR}' 2>/dev/null && printf '共 %s 张 / %s\n' \
\$(ls *.JPG *.jpg 2>/dev/null | wc -l) \$(du -sh . 2>/dev/null | cut -f1)"
    ;;

sync)
    LDIR=${2:-./photos}
    # 防 MSYS 把 /opt/... 改写成 Windows 路径
    export MSYS_NO_PATHCONV=1
    mkdir -p "$LDIR"
    echo "[list] 取机内清单…"
    remote=$("${SSH[@]}" "cd '${RDIR}' && ls -1 *.JPG *.jpg 2>/dev/null")
    if [ -z "$remote" ]; then echo "机内无照片或路径不对: $RDIR"; exit 1; fi
    batch=$(mktemp)
    n=0
    for f in $remote; do
        if [ -f "$LDIR/$f" ]; then
            rs=$("${SSH[@]}" "stat -c %s '${RDIR}/$f'" 2>/dev/null)
            ls_size=$(wc -c < "$LDIR/$f" | tr -d ' ')
            [ "$rs" = "$ls_size" ] && continue
        fi
        echo "get ${RDIR}/$f $LDIR/$f" >> "$batch"
        n=$((n+1))
    done
    if [ "$n" -eq 0 ]; then
        echo "[sync] 已是最新（$(echo "$remote" | wc -w) 张）"
    else
        echo "[sync] 需下载 $n 张…"
        "${SFTP[@]}" -b "$batch" "$DEST"
    fi
    rm -f "$batch"
    echo "[ok] 本地 $LDIR  共 $(ls -1 "$LDIR"/*.JPG "$LDIR"/*.jpg 2>/dev/null | wc -l) 张"
    ;;

get)
    f=${2:?需要文件名}
    LDIR=${3:-./photos}
    mkdir -p "$LDIR"
    scp -P "$PORT" -i "$KEY" -o IdentitiesOnly=yes \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
        "root@$HOST:${RDIR}/$f" "$LDIR/$f" && ls -lh "$LDIR/$f"
    ;;

album)
    LDIR=${2:-./photos}
    [ -d "$LDIR" ] || { echo "目录不存在: $LDIR"; exit 1; }
    OUT="$(cd "$LDIR" && pwd)/_album.html"
    {
        echo '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        echo '<title>NX500 相册</title><style>'
        echo 'body{margin:0;background:#1b1b1b;color:#ddd;font:14px/1.5 system-ui,sans-serif}'
        echo 'header{padding:14px 20px;border-bottom:1px solid #333;position:sticky;top:0;background:#1b1b1b}'
        echo 'h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.5px}'
        echo '.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;padding:14px}'
        echo 'figure{margin:0;background:#252525;border-radius:6px;overflow:hidden}'
        echo 'figure img{width:100%;display:block;aspect-ratio:3/2;object-fit:cover;cursor:zoom-in}'
        echo 'figcaption{padding:6px 8px;font-size:12px;color:#999;display:flex;justify-content:space-between}'
        echo 'a{color:#7ab}'
        echo '</style></head><body><header><h1>NX500 相册 · <span id=c></span></h1></header><div class=g>'
        cnt=0
        for f in $(cd "$LDIR" && ls -1 *.JPG *.jpg 2>/dev/null); do
            sz=$(du -h "$LDIR/$f" | cut -f1)
            echo "<figure><a href=\"$f\" target=_blank><img loading=lazy src=\"$f\" alt=\"$f\"></a>"
            echo "<figcaption><span>$f</span><span>$sz</span></figcaption></figure>"
            cnt=$((cnt+1))
        done
        echo "</div><script>document.getElementById('c').textContent='${cnt} 张'</script></body></html>"
    } > "$OUT"
    echo "[ok] $OUT  (${cnt} 张)"
    case "$(uname -s)" in
        MINGW*|MSYS*) start "" "$(cygpath -w "$OUT")" 2>/dev/null || explorer.exe "$(cygpath -w "$OUT")" ;;
        Darwin) open "$OUT" ;;
        *) xdg-open "$OUT" 2>/dev/null ;;
    esac
    ;;

*)
    sed -n '2,15p' "$0"
    exit 2
    ;;
esac
