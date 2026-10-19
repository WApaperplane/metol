#!/bin/sh
set -e
BB=/opt/usr/nx-ks/busybox
OUT=${0%/*}
ST=/mnt/mmc/lut/state
/bin/sh /opt/usr/nx-ks/lut.sh off
$BB mkdir "$ST/.lock"
trap '$BB rmdir "$ST/.lock"' EXIT
trap 'exit 1' HUP INT TERM
$BB mkdir -p "$OUT/old_tables" "$OUT/old_tools"
set -- $($BB md5sum "$OUT/cube2lut.arm")
[ "$1" = 2d94e76f4e917ce73d9ffad960a48c64 ]
set -- $($BB md5sum /opt/usr/nx-ks/lut.sh)
[ "$1" = b11a614971cb96abe561b4690be30aab ]
set -- $($BB md5sum /mnt/mmc/looks/ektachrome100.bin)
[ "$1" = 4730aaf5afda2af60b429f7dc3bffbb5 ]
set -- $($BB md5sum "$OUT/new_tables/ektachrome100.bin")
[ "$1" = ea57e3b3961390e6b5099760c471c9ad ]
set -- $($BB md5sum /mnt/mmc/looks/ektar100.bin)
[ "$1" = 0b0c0172dc832b65c891922c01410116 ]
set -- $($BB md5sum "$OUT/new_tables/ektar100.bin")
[ "$1" = 4c2127664a7d42ed5be317bbd60a3a94 ]
set -- $($BB md5sum /mnt/mmc/looks/fp100c.bin)
[ "$1" = 17b73bb92b0e861e05e086c5fa62cdd8 ]
set -- $($BB md5sum "$OUT/new_tables/fp100c.bin")
[ "$1" = ea5e9e1b1b0732edaed92dae71b3edf6 ]
set -- $($BB md5sum /mnt/mmc/looks/fuji400h.bin)
[ "$1" = 4983b0c68790c9d09f926425449e791c ]
set -- $($BB md5sum "$OUT/new_tables/fuji400h.bin")
[ "$1" = 8a54c26d43ae67d22e9ac20637a49d44 ]
set -- $($BB md5sum /mnt/mmc/looks/hp5.bin)
[ "$1" = 117bfbb9857c272388a7d05bc5bf83ef ]
set -- $($BB md5sum "$OUT/new_tables/hp5.bin")
[ "$1" = 104c04b3cda837cfdbbcb38afed48987 ]
set -- $($BB md5sum /mnt/mmc/looks/kodachrome64.bin)
[ "$1" = 9717395e68bc4bd0d3e69e8f703fa70a ]
set -- $($BB md5sum "$OUT/new_tables/kodachrome64.bin")
[ "$1" = 1f9070e6c77f402bf791c4ae5ac8ab75 ]
set -- $($BB md5sum /mnt/mmc/looks/portra160vc.bin)
[ "$1" = dd29c1dd210e0eb886f0ae9b1c4a10bb ]
set -- $($BB md5sum "$OUT/new_tables/portra160vc.bin")
[ "$1" = 2fb8b281d8dd78e9c09f94299c6e7565 ]
set -- $($BB md5sum /mnt/mmc/looks/portra400.bin)
[ "$1" = 07110473046f41708351f47ad6972c9f ]
set -- $($BB md5sum "$OUT/new_tables/portra400.bin")
[ "$1" = a9f3a63adb383cb57dbedb0f223d306a ]
set -- $($BB md5sum /mnt/mmc/looks/portra400nc.bin)
[ "$1" = ec9fad9a448d2b782a74a241e858858d ]
set -- $($BB md5sum "$OUT/new_tables/portra400nc.bin")
[ "$1" = 863066f95108e7538be47263c28d24c2 ]
set -- $($BB md5sum /mnt/mmc/looks/portra800.bin)
[ "$1" = 18fca6aaa8773ce030ce45ccad978fa9 ]
set -- $($BB md5sum "$OUT/new_tables/portra800.bin")
[ "$1" = ee0674e5fe10cb9c9ebe8893ac555dec ]
set -- $($BB md5sum /mnt/mmc/looks/print2383.bin)
[ "$1" = 04958ad1cc846566505ddda67ff86c5d ]
set -- $($BB md5sum "$OUT/new_tables/print2383.bin")
[ "$1" = 1ea9014566a73b5e2284bba456195a5b ]
set -- $($BB md5sum /mnt/mmc/looks/print3510.bin)
[ "$1" = 1cb1370cf3e77ab474947fdc9fc66634 ]
set -- $($BB md5sum "$OUT/new_tables/print3510.bin")
[ "$1" = 0bbdf25f51dd5915f2fc1b447fce32df ]
set -- $($BB md5sum /mnt/mmc/looks/tmax3200.bin)
[ "$1" = b16eb63543cdd469f369484bb95678ba ]
set -- $($BB md5sum "$OUT/new_tables/tmax3200.bin")
[ "$1" = f2e530df438eee30aeea835ae1cd3fcb ]
set -- $($BB md5sum /mnt/mmc/looks/trix400.bin)
[ "$1" = e3d3125cbee97826a3ddea7115fd91ae ]
set -- $($BB md5sum "$OUT/new_tables/trix400.bin")
[ "$1" = f0d25e00b6b73dd07273b8ca1ae52d3e ]
set -- $($BB md5sum /mnt/mmc/looks/velvia50.bin)
[ "$1" = 221ca6055c66d68e924f6bb9b693c61e ]
set -- $($BB md5sum "$OUT/new_tables/velvia50.bin")
[ "$1" = 59fc6ba4d29139da23d2e0570bc028e8 ]
set -- $($BB md5sum /mnt/mmc/looks/xt3proneg.bin)
[ "$1" = f5bf445a8a2e761a68212db6d6c4be2d ]
set -- $($BB md5sum "$OUT/new_tables/xt3proneg.bin")
[ "$1" = b48294d7e4352a705148b64e21c1c329 ]
set -- $($BB md5sum /mnt/mmc/looks/xt3velvia.bin)
[ "$1" = b4cb0556323d0a1cf5c5628ad514e530 ]
set -- $($BB md5sum "$OUT/new_tables/xt3velvia.bin")
[ "$1" = cd9850b1257b5b89fc0e5b721104ed81 ]
set -- $($BB md5sum /mnt/mmc/looks/bw_acros100.bin)
[ "$1" = 18f0e34bb5b13219863ee134ed1c6231 ]
set -- $($BB md5sum "$OUT/new_tables/bw_acros100.bin")
[ "$1" = 10fe9dbd3b4502fd157f2da5a148a4ee ]
set -- $($BB md5sum /mnt/mmc/looks/bw_delta3200.bin)
[ "$1" = 330f348682efa2cdc8e4e68a476fdef6 ]
set -- $($BB md5sum "$OUT/new_tables/bw_delta3200.bin")
[ "$1" = 1260791d47584ecd256d1eaf80a68165 ]
set -- $($BB md5sum /mnt/mmc/looks/bw_retro80s.bin)
[ "$1" = 3cfa011afccbfe737917cf8df85f3169 ]
set -- $($BB md5sum "$OUT/new_tables/bw_retro80s.bin")
[ "$1" = 7decb1b90be10fa3b5b3e61839e01ef3 ]
set -- $($BB md5sum /mnt/mmc/looks/elitecolor400.bin)
[ "$1" = 482273b29ade0f8af4c24474c84054ef ]
set -- $($BB md5sum "$OUT/new_tables/elitecolor400.bin")
[ "$1" = 634cf813db1599067c34eb2bf05f5f2a ]
set -- $($BB md5sum /mnt/mmc/looks/fp3000b.bin)
[ "$1" = ed0147df04db614e5d1a2beb1f449c84 ]
set -- $($BB md5sum "$OUT/new_tables/fp3000b.bin")
[ "$1" = 26817ab09f718efc3ab11584e9f3abaf ]
set -- $($BB md5sum /mnt/mmc/looks/fuji800z.bin)
[ "$1" = 960b326317ab1452476951603a882eb3 ]
set -- $($BB md5sum "$OUT/new_tables/fuji800z.bin")
[ "$1" = 56e3f3f1e8cff02ce6f5691ffb24eb45 ]
set -- $($BB md5sum /mnt/mmc/looks/polaroid665.bin)
[ "$1" = 314374b3cb553a85e05050c040c76860 ]
set -- $($BB md5sum "$OUT/new_tables/polaroid665.bin")
[ "$1" = 1c6b102abddc9f0439a56dbfc33e0dae ]
set -- $($BB md5sum /mnt/mmc/looks/portra160.bin)
[ "$1" = a41070fdd763f0877a0d791358622e93 ]
set -- $($BB md5sum "$OUT/new_tables/portra160.bin")
[ "$1" = 7d3688a11db5a6e1d25892fa7ec84950 ]
set -- $($BB md5sum /mnt/mmc/looks/portra400uc.bin)
[ "$1" = efeef21ff78379b6f2dde7ed9f5f3691 ]
set -- $($BB md5sum "$OUT/new_tables/portra400uc.bin")
[ "$1" = ed26458ccf6fc468decd89aab961e89a ]
set -- $($BB md5sum /mnt/mmc/looks/print2393.bin)
[ "$1" = 2d4f39d0ee6ae1c96afacacd4b0bd7b2 ]
set -- $($BB md5sum "$OUT/new_tables/print2393.bin")
[ "$1" = 1bfe1946567836b3cdd36363ea2937c4 ]
set -- $($BB md5sum /mnt/mmc/looks/print3513.bin)
[ "$1" = b044eb0ff20fd5b270fb2e10a8672da4 ]
set -- $($BB md5sum "$OUT/new_tables/print3513.bin")
[ "$1" = a0d14677709cfb52b02f845dadaeb09b ]
set -- $($BB md5sum /mnt/mmc/looks/slide_astia100f.bin)
[ "$1" = 922c10b02ae246527267da4f2675ed0b ]
set -- $($BB md5sum "$OUT/new_tables/slide_astia100f.bin")
[ "$1" = bc359cedb893b06fcc0ebd5338d7bcf6 ]
set -- $($BB md5sum /mnt/mmc/looks/slide_kodachrome25.bin)
[ "$1" = bba7ed12a7e0655cea6b504883e3f4e7 ]
set -- $($BB md5sum "$OUT/new_tables/slide_kodachrome25.bin")
[ "$1" = 3ac40766db7f4ae1fcaffaa77ed90403 ]
set -- $($BB md5sum /mnt/mmc/looks/slide_precisa100.bin)
[ "$1" = ca026397cb37e2b26e4f206afb01e758 ]
set -- $($BB md5sum "$OUT/new_tables/slide_precisa100.bin")
[ "$1" = 5280ca6ef5a347e19198a66b1b09c314 ]
set -- $($BB md5sum /mnt/mmc/looks/slide_provia100f.bin)
[ "$1" = bb6b1408e706b36a813c2f94bca5b6e2 ]
set -- $($BB md5sum "$OUT/new_tables/slide_provia100f.bin")
[ "$1" = 13d4fea76038e0c5102262bb63eb89de ]
set -- $($BB md5sum /mnt/mmc/looks/superia200.bin)
[ "$1" = 0b5cbb63e24af6b2929b84d291ed8080 ]
set -- $($BB md5sum "$OUT/new_tables/superia200.bin")
[ "$1" = 129faae942c8b762b2fc217569da0564 ]
set -- $($BB md5sum /mnt/mmc/looks/superia400.bin)
[ "$1" = ee411d7f9f325b61a9aa26bf7f766e58 ]
set -- $($BB md5sum "$OUT/new_tables/superia400.bin")
[ "$1" = 60a2215c7489fce98ccd130b3fb45e88 ]
set -- $($BB md5sum /mnt/mmc/looks/xt3classic.bin)
[ "$1" = 5c96cb325ebf85c291afda6ac99bcaa8 ]
set -- $($BB md5sum "$OUT/new_tables/xt3classic.bin")
[ "$1" = f1649ef5081157420ef5a1b6b334927e ]
set -- $($BB md5sum /mnt/mmc/looks/xt3provia.bin)
[ "$1" = 60245ee4afe2430230172c2169c87169 ]
set -- $($BB md5sum "$OUT/new_tables/xt3provia.bin")
[ "$1" = 18b83ff6a84c6ab3f0c2a00456a42bb1 ]
set -- $($BB md5sum /opt/usr/nx-ks/lut/cube2lut.arm)
[ "$1" = 582b12f0cc9f04ca765a8989d664b580 ]
$BB cp /opt/usr/nx-ks/lut/cube2lut.arm "$OUT/old_tools/runtime.arm"
set -- $($BB md5sum /mnt/mmc/lut/cube2lut.arm)
[ "$1" = 582b12f0cc9f04ca765a8989d664b580 ]
$BB cp /mnt/mmc/lut/cube2lut.arm "$OUT/old_tools/sd.arm"
set -- $($BB md5sum /mnt/mmc/scripts/lut/cube2lut.arm)
[ "$1" = 582b12f0cc9f04ca765a8989d664b580 ]
$BB cp /mnt/mmc/scripts/lut/cube2lut.arm "$OUT/old_tools/mother.arm"
$BB cp /mnt/mmc/looks/ektachrome100.bin "$OUT/old_tables/ektachrome100.bin"
$BB cp /mnt/mmc/looks/ektar100.bin "$OUT/old_tables/ektar100.bin"
$BB cp /mnt/mmc/looks/fp100c.bin "$OUT/old_tables/fp100c.bin"
$BB cp /mnt/mmc/looks/fuji400h.bin "$OUT/old_tables/fuji400h.bin"
$BB cp /mnt/mmc/looks/hp5.bin "$OUT/old_tables/hp5.bin"
$BB cp /mnt/mmc/looks/kodachrome64.bin "$OUT/old_tables/kodachrome64.bin"
$BB cp /mnt/mmc/looks/portra160vc.bin "$OUT/old_tables/portra160vc.bin"
$BB cp /mnt/mmc/looks/portra400.bin "$OUT/old_tables/portra400.bin"
$BB cp /mnt/mmc/looks/portra400nc.bin "$OUT/old_tables/portra400nc.bin"
$BB cp /mnt/mmc/looks/portra800.bin "$OUT/old_tables/portra800.bin"
$BB cp /mnt/mmc/looks/print2383.bin "$OUT/old_tables/print2383.bin"
$BB cp /mnt/mmc/looks/print3510.bin "$OUT/old_tables/print3510.bin"
$BB cp /mnt/mmc/looks/tmax3200.bin "$OUT/old_tables/tmax3200.bin"
$BB cp /mnt/mmc/looks/trix400.bin "$OUT/old_tables/trix400.bin"
$BB cp /mnt/mmc/looks/velvia50.bin "$OUT/old_tables/velvia50.bin"
$BB cp /mnt/mmc/looks/xt3proneg.bin "$OUT/old_tables/xt3proneg.bin"
$BB cp /mnt/mmc/looks/xt3velvia.bin "$OUT/old_tables/xt3velvia.bin"
$BB cp /mnt/mmc/looks/bw_acros100.bin "$OUT/old_tables/bw_acros100.bin"
$BB cp /mnt/mmc/looks/bw_delta3200.bin "$OUT/old_tables/bw_delta3200.bin"
$BB cp /mnt/mmc/looks/bw_retro80s.bin "$OUT/old_tables/bw_retro80s.bin"
$BB cp /mnt/mmc/looks/elitecolor400.bin "$OUT/old_tables/elitecolor400.bin"
$BB cp /mnt/mmc/looks/fp3000b.bin "$OUT/old_tables/fp3000b.bin"
$BB cp /mnt/mmc/looks/fuji800z.bin "$OUT/old_tables/fuji800z.bin"
$BB cp /mnt/mmc/looks/polaroid665.bin "$OUT/old_tables/polaroid665.bin"
$BB cp /mnt/mmc/looks/portra160.bin "$OUT/old_tables/portra160.bin"
$BB cp /mnt/mmc/looks/portra400uc.bin "$OUT/old_tables/portra400uc.bin"
$BB cp /mnt/mmc/looks/print2393.bin "$OUT/old_tables/print2393.bin"
$BB cp /mnt/mmc/looks/print3513.bin "$OUT/old_tables/print3513.bin"
$BB cp /mnt/mmc/looks/slide_astia100f.bin "$OUT/old_tables/slide_astia100f.bin"
$BB cp /mnt/mmc/looks/slide_kodachrome25.bin "$OUT/old_tables/slide_kodachrome25.bin"
$BB cp /mnt/mmc/looks/slide_precisa100.bin "$OUT/old_tables/slide_precisa100.bin"
$BB cp /mnt/mmc/looks/slide_provia100f.bin "$OUT/old_tables/slide_provia100f.bin"
$BB cp /mnt/mmc/looks/superia200.bin "$OUT/old_tables/superia200.bin"
$BB cp /mnt/mmc/looks/superia400.bin "$OUT/old_tables/superia400.bin"
$BB cp /mnt/mmc/looks/xt3classic.bin "$OUT/old_tables/xt3classic.bin"
$BB cp /mnt/mmc/looks/xt3provia.bin "$OUT/old_tables/xt3provia.bin"
$BB sync
echo BACKUPS_COMPLETE
$BB cp "$OUT/cube2lut.arm" /opt/usr/nx-ks/lut/cube2lut.arm.new
$BB chmod 755 /opt/usr/nx-ks/lut/cube2lut.arm.new
$BB mv /opt/usr/nx-ks/lut/cube2lut.arm.new /opt/usr/nx-ks/lut/cube2lut.arm
$BB md5sum /opt/usr/nx-ks/lut/cube2lut.arm
$BB cp "$OUT/cube2lut.arm" /mnt/mmc/lut/cube2lut.arm.new
$BB chmod 755 /mnt/mmc/lut/cube2lut.arm.new
$BB mv /mnt/mmc/lut/cube2lut.arm.new /mnt/mmc/lut/cube2lut.arm
$BB md5sum /mnt/mmc/lut/cube2lut.arm
$BB cp "$OUT/cube2lut.arm" /mnt/mmc/scripts/lut/cube2lut.arm.new
$BB chmod 755 /mnt/mmc/scripts/lut/cube2lut.arm.new
$BB mv /mnt/mmc/scripts/lut/cube2lut.arm.new /mnt/mmc/scripts/lut/cube2lut.arm
$BB md5sum /mnt/mmc/scripts/lut/cube2lut.arm
$BB cp "$OUT/new_tables/ektachrome100.bin" /mnt/mmc/looks/ektachrome100.bin.new
$BB mv /mnt/mmc/looks/ektachrome100.bin.new /mnt/mmc/looks/ektachrome100.bin
$BB md5sum /mnt/mmc/looks/ektachrome100.bin
$BB cp "$OUT/new_tables/ektar100.bin" /mnt/mmc/looks/ektar100.bin.new
$BB mv /mnt/mmc/looks/ektar100.bin.new /mnt/mmc/looks/ektar100.bin
$BB md5sum /mnt/mmc/looks/ektar100.bin
$BB cp "$OUT/new_tables/fp100c.bin" /mnt/mmc/looks/fp100c.bin.new
$BB mv /mnt/mmc/looks/fp100c.bin.new /mnt/mmc/looks/fp100c.bin
$BB md5sum /mnt/mmc/looks/fp100c.bin
$BB cp "$OUT/new_tables/fuji400h.bin" /mnt/mmc/looks/fuji400h.bin.new
$BB mv /mnt/mmc/looks/fuji400h.bin.new /mnt/mmc/looks/fuji400h.bin
$BB md5sum /mnt/mmc/looks/fuji400h.bin
$BB cp "$OUT/new_tables/hp5.bin" /mnt/mmc/looks/hp5.bin.new
$BB mv /mnt/mmc/looks/hp5.bin.new /mnt/mmc/looks/hp5.bin
$BB md5sum /mnt/mmc/looks/hp5.bin
$BB cp "$OUT/new_tables/kodachrome64.bin" /mnt/mmc/looks/kodachrome64.bin.new
$BB mv /mnt/mmc/looks/kodachrome64.bin.new /mnt/mmc/looks/kodachrome64.bin
$BB md5sum /mnt/mmc/looks/kodachrome64.bin
$BB cp "$OUT/new_tables/portra160vc.bin" /mnt/mmc/looks/portra160vc.bin.new
$BB mv /mnt/mmc/looks/portra160vc.bin.new /mnt/mmc/looks/portra160vc.bin
$BB md5sum /mnt/mmc/looks/portra160vc.bin
$BB cp "$OUT/new_tables/portra400.bin" /mnt/mmc/looks/portra400.bin.new
$BB mv /mnt/mmc/looks/portra400.bin.new /mnt/mmc/looks/portra400.bin
$BB md5sum /mnt/mmc/looks/portra400.bin
$BB cp "$OUT/new_tables/portra400nc.bin" /mnt/mmc/looks/portra400nc.bin.new
$BB mv /mnt/mmc/looks/portra400nc.bin.new /mnt/mmc/looks/portra400nc.bin
$BB md5sum /mnt/mmc/looks/portra400nc.bin
$BB cp "$OUT/new_tables/portra800.bin" /mnt/mmc/looks/portra800.bin.new
$BB mv /mnt/mmc/looks/portra800.bin.new /mnt/mmc/looks/portra800.bin
$BB md5sum /mnt/mmc/looks/portra800.bin
$BB cp "$OUT/new_tables/print2383.bin" /mnt/mmc/looks/print2383.bin.new
$BB mv /mnt/mmc/looks/print2383.bin.new /mnt/mmc/looks/print2383.bin
$BB md5sum /mnt/mmc/looks/print2383.bin
$BB cp "$OUT/new_tables/print3510.bin" /mnt/mmc/looks/print3510.bin.new
$BB mv /mnt/mmc/looks/print3510.bin.new /mnt/mmc/looks/print3510.bin
$BB md5sum /mnt/mmc/looks/print3510.bin
$BB cp "$OUT/new_tables/tmax3200.bin" /mnt/mmc/looks/tmax3200.bin.new
$BB mv /mnt/mmc/looks/tmax3200.bin.new /mnt/mmc/looks/tmax3200.bin
$BB md5sum /mnt/mmc/looks/tmax3200.bin
$BB cp "$OUT/new_tables/trix400.bin" /mnt/mmc/looks/trix400.bin.new
$BB mv /mnt/mmc/looks/trix400.bin.new /mnt/mmc/looks/trix400.bin
$BB md5sum /mnt/mmc/looks/trix400.bin
$BB cp "$OUT/new_tables/velvia50.bin" /mnt/mmc/looks/velvia50.bin.new
$BB mv /mnt/mmc/looks/velvia50.bin.new /mnt/mmc/looks/velvia50.bin
$BB md5sum /mnt/mmc/looks/velvia50.bin
$BB cp "$OUT/new_tables/xt3proneg.bin" /mnt/mmc/looks/xt3proneg.bin.new
$BB mv /mnt/mmc/looks/xt3proneg.bin.new /mnt/mmc/looks/xt3proneg.bin
$BB md5sum /mnt/mmc/looks/xt3proneg.bin
$BB cp "$OUT/new_tables/xt3velvia.bin" /mnt/mmc/looks/xt3velvia.bin.new
$BB mv /mnt/mmc/looks/xt3velvia.bin.new /mnt/mmc/looks/xt3velvia.bin
$BB md5sum /mnt/mmc/looks/xt3velvia.bin
$BB cp "$OUT/new_tables/bw_acros100.bin" /mnt/mmc/looks/bw_acros100.bin.new
$BB mv /mnt/mmc/looks/bw_acros100.bin.new /mnt/mmc/looks/bw_acros100.bin
$BB md5sum /mnt/mmc/looks/bw_acros100.bin
$BB cp "$OUT/new_tables/bw_delta3200.bin" /mnt/mmc/looks/bw_delta3200.bin.new
$BB mv /mnt/mmc/looks/bw_delta3200.bin.new /mnt/mmc/looks/bw_delta3200.bin
$BB md5sum /mnt/mmc/looks/bw_delta3200.bin
$BB cp "$OUT/new_tables/bw_retro80s.bin" /mnt/mmc/looks/bw_retro80s.bin.new
$BB mv /mnt/mmc/looks/bw_retro80s.bin.new /mnt/mmc/looks/bw_retro80s.bin
$BB md5sum /mnt/mmc/looks/bw_retro80s.bin
$BB cp "$OUT/new_tables/elitecolor400.bin" /mnt/mmc/looks/elitecolor400.bin.new
$BB mv /mnt/mmc/looks/elitecolor400.bin.new /mnt/mmc/looks/elitecolor400.bin
$BB md5sum /mnt/mmc/looks/elitecolor400.bin
$BB cp "$OUT/new_tables/fp3000b.bin" /mnt/mmc/looks/fp3000b.bin.new
$BB mv /mnt/mmc/looks/fp3000b.bin.new /mnt/mmc/looks/fp3000b.bin
$BB md5sum /mnt/mmc/looks/fp3000b.bin
$BB cp "$OUT/new_tables/fuji800z.bin" /mnt/mmc/looks/fuji800z.bin.new
$BB mv /mnt/mmc/looks/fuji800z.bin.new /mnt/mmc/looks/fuji800z.bin
$BB md5sum /mnt/mmc/looks/fuji800z.bin
$BB cp "$OUT/new_tables/polaroid665.bin" /mnt/mmc/looks/polaroid665.bin.new
$BB mv /mnt/mmc/looks/polaroid665.bin.new /mnt/mmc/looks/polaroid665.bin
$BB md5sum /mnt/mmc/looks/polaroid665.bin
$BB cp "$OUT/new_tables/portra160.bin" /mnt/mmc/looks/portra160.bin.new
$BB mv /mnt/mmc/looks/portra160.bin.new /mnt/mmc/looks/portra160.bin
$BB md5sum /mnt/mmc/looks/portra160.bin
$BB cp "$OUT/new_tables/portra400uc.bin" /mnt/mmc/looks/portra400uc.bin.new
$BB mv /mnt/mmc/looks/portra400uc.bin.new /mnt/mmc/looks/portra400uc.bin
$BB md5sum /mnt/mmc/looks/portra400uc.bin
$BB cp "$OUT/new_tables/print2393.bin" /mnt/mmc/looks/print2393.bin.new
$BB mv /mnt/mmc/looks/print2393.bin.new /mnt/mmc/looks/print2393.bin
$BB md5sum /mnt/mmc/looks/print2393.bin
$BB cp "$OUT/new_tables/print3513.bin" /mnt/mmc/looks/print3513.bin.new
$BB mv /mnt/mmc/looks/print3513.bin.new /mnt/mmc/looks/print3513.bin
$BB md5sum /mnt/mmc/looks/print3513.bin
$BB cp "$OUT/new_tables/slide_astia100f.bin" /mnt/mmc/looks/slide_astia100f.bin.new
$BB mv /mnt/mmc/looks/slide_astia100f.bin.new /mnt/mmc/looks/slide_astia100f.bin
$BB md5sum /mnt/mmc/looks/slide_astia100f.bin
$BB cp "$OUT/new_tables/slide_kodachrome25.bin" /mnt/mmc/looks/slide_kodachrome25.bin.new
$BB mv /mnt/mmc/looks/slide_kodachrome25.bin.new /mnt/mmc/looks/slide_kodachrome25.bin
$BB md5sum /mnt/mmc/looks/slide_kodachrome25.bin
$BB cp "$OUT/new_tables/slide_precisa100.bin" /mnt/mmc/looks/slide_precisa100.bin.new
$BB mv /mnt/mmc/looks/slide_precisa100.bin.new /mnt/mmc/looks/slide_precisa100.bin
$BB md5sum /mnt/mmc/looks/slide_precisa100.bin
$BB cp "$OUT/new_tables/slide_provia100f.bin" /mnt/mmc/looks/slide_provia100f.bin.new
$BB mv /mnt/mmc/looks/slide_provia100f.bin.new /mnt/mmc/looks/slide_provia100f.bin
$BB md5sum /mnt/mmc/looks/slide_provia100f.bin
$BB cp "$OUT/new_tables/superia200.bin" /mnt/mmc/looks/superia200.bin.new
$BB mv /mnt/mmc/looks/superia200.bin.new /mnt/mmc/looks/superia200.bin
$BB md5sum /mnt/mmc/looks/superia200.bin
$BB cp "$OUT/new_tables/superia400.bin" /mnt/mmc/looks/superia400.bin.new
$BB mv /mnt/mmc/looks/superia400.bin.new /mnt/mmc/looks/superia400.bin
$BB md5sum /mnt/mmc/looks/superia400.bin
$BB cp "$OUT/new_tables/xt3classic.bin" /mnt/mmc/looks/xt3classic.bin.new
$BB mv /mnt/mmc/looks/xt3classic.bin.new /mnt/mmc/looks/xt3classic.bin
$BB md5sum /mnt/mmc/looks/xt3classic.bin
$BB cp "$OUT/new_tables/xt3provia.bin" /mnt/mmc/looks/xt3provia.bin.new
$BB mv /mnt/mmc/looks/xt3provia.bin.new /mnt/mmc/looks/xt3provia.bin
$BB md5sum /mnt/mmc/looks/xt3provia.bin
$BB sync
echo COLOURSPACE_DEPLOY_DONE_36_TABLES
