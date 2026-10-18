#!/bin/sh
# 对焦堆栈。
# 配置必须放 SD：focus_stack 的默认 settings_file 是 /root/focus_stack.cfg，
# 而 /root 在 p10 上以 ro 挂载 -> save_settings() 的 fopen("w") 必然失败，
# 表现为「Conf.」里设的张数/间隔存不住（每次回默认 10 张 / 6 s）。
# focus_stack 支持 argv[1] 传配置绝对路径（源码：argv[1][0]=='/' 即接管），
# 所以这里显式指定 SD 上的 cfg，并做目录/文件兜底（幂等）。
CFG=/mnt/mmc/scripts/focus_stack.cfg
mkdir -p /mnt/mmc/scripts 2>/dev/null
[ -f "$CFG" ] || printf '10\n6\n' > "$CFG" 2>/dev/null
renice -n +10 -p $(pgrep di-camera-app)
nice -n -10 /opt/usr/nx-ks/focus_stack "$CFG" &
