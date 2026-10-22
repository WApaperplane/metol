# baseline

`dropbear-O0` —— 2026-10-23 切换到 -O2 之前的产物（glibc 2.13 sysroot，-O0，336,732 B）。

**用途**：紧急回滚，不需要 WSL 环境重编。

```bash
cp test_server/dropbear/baseline/dropbear-O0 scripts/dropbear/dropbear
python tools/nx-put.py -d scripts/dropbear scripts/dropbear/dropbear
# 机端：
#   cp /opt/storage/sdcard/scripts/dropbear/dropbear /opt/usr/nx-ks/dropbear/dropbear
#   chmod +x /opt/usr/nx-ks/dropbear/dropbear
#   sh /opt/usr/nx-ks/dropbear/restart.sh
```

重编同一份也可复现：`build_dropbear.sh`（不带参数即 -O0）。
