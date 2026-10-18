#!/bin/sh
# 对焦按钮（focus_buttons）启动包装。
# focus_buttons 的 af_positions_file 是编译期 strncpy 硬编码的
# /mnt/mmc/scripts/af_positions.txt，二进制里改不了。
# 该目录不存在时 fopen("w") 静默失败 -> 长按保存位置、点击恢复位置全部失效，
# 按钮只能跳到内存默认值 1000。
# 因此这里先保证目录存在再拉起（幂等，不创建文件本身：位置表应由用户首次长按生成）。
mkdir -p /mnt/mmc/scripts 2>/dev/null
exec /opt/usr/nx-ks/focus_buttons
