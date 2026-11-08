"""Run the real tc.sh against in-shell simulated memory, never /dev/mem."""
import os,pathlib,shlex,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
SH=pathlib.Path(os.environ.get('NXWA_TEST_SH',str(pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/usr/bin/sh.exe')))
MOCK=r'''
fake() {
 cmd=$1; shift
 case "$cmd" in
 pidof) echo 123 ;;
 ls) [ "$FAKE_RECORDING" -eq 0 ] || echo 'l-wx 40 -> /mnt/mmc/DCIM/100PHOTO/SAM_0001.MP4' ; return 0 ;;
 mkdir) mkdir "$@" ;;
 rmdir) /usr/bin/rmdir "$@" 2>/dev/null || true ;;
 grep) grep "$@" ;;
 devmem)
  addr=$(($1))
  if [ "$#" -eq 3 ]; then
   if [ "$addr" -eq "$((GAMMA+4))" ]; then
    desc=0xffffffff
    if [ "$FAKE_CONSUME" -eq 1 ]; then
     j=0
     while [ "$j" -lt 19 ]; do
      a=$((SRC+j*4)); eval "v=\${W_$a}"
      a=$((GAMMA+0xe8c+j*4));eval "W_$a=$v"
      j=$((j+1))
     done
     desc=0x0a00807f
    fi
    eval "W_$addr=$desc"
   else eval "W_$addr=$3"; fi
   return 0
  fi
  eval "v=\${W_$addr-0}"
  printf '0x%08x\n' "$v"
  ;;
 *) echo "UNEXPECTED_MOCK_COMMAND:$cmd" >&2; return 99 ;;
 esac
}
B=fake
P0=0x81200000
GAMMA=$((0x81200800))
eval "W_$((P0_PTR))=$((P0))"
eval "W_$((P0))=$((PARAM_SIG))"
eval "W_$((P0+GAMMA_OFF))=$GAMMA"
eval "W_$GAMMA=$((GAMMA_VTBL))"
eval "W_$((GAMMA+4))=$((0x0a00807f))"
eval "W_$((0x817dccb8))=1"
j=0
for v in $STOCK; do
 eval "W_$((SRC+j*4))=$v"
 eval "W_$((GAMMA+0xe8c+j*4))=$v"
 j=$((j+1))
done
'''

@unittest.skipUnless(SH.exists(),'set NXWA_TEST_SH to a POSIX shell for offline memory-model tests')
class ShellTests(unittest.TestCase):
 def run_model(self,recording,consume,locked=False):
  script=(ROOT/'scripts/tc.sh').read_text(encoding='utf-8')
  where=script.index('case "${1:-status}" in')
  with tempfile.TemporaryDirectory() as t:
   folder=pathlib.Path(t);lock=folder/'lock'
   if locked:lock.mkdir()
   shellbin=SH.parent.as_posix()
   if SH.drive:shellbin='/'+SH.drive[0].lower()+shellbin[2:]
   injection=f"export PATH={shlex.quote(shellbin)}:$PATH\nLOCK={shlex.quote(lock.as_posix())}\nFAKE_RECORDING={int(recording)}\nFAKE_CONSUME={int(consume)}\n"+MOCK
   f=folder/'model.sh';f.write_text(script[:where]+injection+script[where:],encoding='utf-8',newline='\n')
   return subprocess.run([str(SH),str(f),'off'],capture_output=True,text=True,timeout=15)
 def test_success(self):
  p=self.run_model(False,True);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('OK=1',p.stdout)
 def test_recording_refused(self):
  p=self.run_model(True,True);self.assertEqual(p.returncode,6,p.stdout+p.stderr);self.assertNotIn('OK=1',p.stdout)
 def test_stuck_dirty_not_reported_restored(self):
  p=self.run_model(False,False);self.assertEqual(p.returncode,4,p.stdout+p.stderr);self.assertIn('RESTORED=0',p.stdout)
 def test_concurrent_writer_refused(self):
  p=self.run_model(False,True,True);self.assertEqual(p.returncode,5,p.stdout+p.stderr)

if __name__=='__main__':unittest.main()
