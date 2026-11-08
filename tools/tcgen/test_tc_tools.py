"""Offline regressions. Remote functions are mocked; shell memory is simulated."""
import contextlib,hashlib,io,json,os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
import numpy as np
import tc_write as writer
import tc_record as recorder
from tcgen import X_STOCK,Y_STOCK,build
from tc_restore import restore,cube
from factory_luts import extract,TABLE,SLOT
ROOT=pathlib.Path(__file__).resolve().parents[2]

class Transactions(unittest.TestCase):
 def call(self,module,fn,response,args):
  with patch.object(module,fn,return_value=response),patch.object(sys,'argv',['test']+args),contextlib.redirect_stdout(io.StringIO()):return module.main()
 def test_failure_and_success_protocols(self):
  args=['--curve',str(pathlib.Path(__file__).parent/'curves/flat.json')]
  good='AFTER_CACHE_OK=1\nAFTER_DIRTY=0x0A00807F\nSRC_EQ_TARGET=1\n'
  for rc,out,tail,keep,want in ((255,good,'',False,False),(0,good,'FINAL_RESTORED=0\nCOMPLETE=1\n',False,False),
   (0,'AFTER_CACHE_OK=1\nSRC_EQ_TARGET=1\n','FINAL_KEPT=1\nCOMPLETE=1\n',True,False),
   (0,good,'FINAL_RESTORED=1\nCOMPLETE=1\n',False,True),(0,good,'FINAL_KEPT=1\nCOMPLETE=1\n',True,True)):
   with self.subTest(rc=rc,tail=tail,keep=keep):self.assertEqual(self.call(writer,'run_remote',(rc,out+tail,''),args+(['--keep'] if keep else []))==0,want)
  for rc,out,want in ((255,'',False),(255,'STARTED\n',False),(0,'STARTED\n',False),(0,'STARTED\nSTOPPED\n',True)):
   with self.subTest(rc=rc,out=out):self.assertEqual(self.call(recorder,'run',(rc,out,''),[])==0,want)

class Restoration(unittest.TestCase):
 def test_stock_identity_and_direction(self):
  x=np.linspace(0,1,65536)
  np.testing.assert_allclose(restore(x,'stock'),x,atol=1e-12)
  for c in ('flat','log'):
   self.assertTrue(np.all(np.diff(restore(x,c))>=0))
   np.testing.assert_allclose(restore(np.array(build(c))/1023,c),np.array(Y_STOCK)/1023,atol=1e-12)
  self.assertLess(restore(.25,'flat'),.25)
 def test_cube_geometry(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'a.cube';cube('flat',p,17)
   values=np.array([[float(v) for v in l.split()] for l in p.read_text().splitlines() if l and l[0] in '0123456789.-']).reshape(17,17,17,3)
   ramp=restore(np.linspace(0,1,17),'flat')
   for k in range(17):np.testing.assert_allclose(values[0,0,k],[ramp[k],0,0],atol=1e-8)
 def test_factory_exact_bytes(self):
  image=ROOT.parent/'fw/v1.12/p7_wrapped.elf';raw=image.read_bytes()[0x1000:]
  with tempfile.TemporaryDirectory() as t:
   rows=extract(image,t);self.assertEqual(len(rows),42)
   for n,row in rows.items():
    data=(pathlib.Path(t)/n).read_bytes();off=int(row['offset'],16)
    self.assertEqual(data,raw[off:off+SLOT]);self.assertEqual(len(data),SLOT)
   self.assertEqual(rows['samsung_a17.bin']['neutral_axis'],[[128,128,min(k*16,255)] for k in range(17)])
   bad=pathlib.Path(t)/'bad.bin';bad.write_bytes(b'wrong firmware')
   with self.assertRaises(ValueError):extract(bad,pathlib.Path(t)/'bad_out')

if __name__=='__main__':unittest.main()
