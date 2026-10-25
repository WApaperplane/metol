"""Design contracts independent of profile parameter values and implementation."""
import colorsys
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import colour

from style_collection import load_profiles,build_profile,grade,rgb_lab
from native_codec import sample_rgb,NATIVE,TABLE,space_for


class StyleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.data=load_profiles();cls.tables={}
        for name in cls.data['selection']:
            raw,_=build_profile(name,cls.data['profiles'][name],cls.root)
            cls.tables[name]=raw
        cls.pp=np.array([np.array(colorsys.hsv_to_rgb(h/360,s,v))*255
            for h in range(0,360,30) for s in (.35,.65) for v in (.3,.55,.85)])

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def out(self,name,points):
        return np.array([sample_rgb(self.tables[name],NATIVE,p) for p in points])

    def test_extreme_yellow_does_not_turn_magenta_or_white(self):
        result=self.out('kodak_gold200',[(255,255,119.53125)])[0]
        self.assertGreater(min(result[:2]),220)
        self.assertLess(result[2],150)

    def test_dense_valid_cube_native_approximation(self):
        from scipy.interpolate import RegularGridInterpolator
        axis=np.linspace(0,255,33)
        pp=np.stack(np.meshgrid(axis,axis,axis,indexing='ij'),-1).reshape(-1,3)
        r,g,b=pp.T
        cr=np.clip(128+.5*r-.418688*g-.081312*b,0,255)
        cb=np.clip(128-.168736*r-.331264*g+.5*b,0,255)
        y=.299*r+.587*g+.114*b
        from native_codec import GRID,ycc_to_rgb
        for name,raw in self.tables.items():
            nodes=np.frombuffer(raw[:TABLE],np.uint8).reshape(17,17,17,4)[...,:3]
            out=RegularGridInterpolator((GRID,GRID,GRID),nodes)(np.stack((y,cb,cr),1))
            actual=np.stack((out[:,2]+1.402*(out[:,0]-128),out[:,2]-.714136*(out[:,0]-128)-.344136*(out[:,1]-128),out[:,2]+1.772*(out[:,1]-128)),1)
            actual=np.clip(actual,0,255)
            direct=grade(pp,self.data['profiles'][name])
            error=colour.delta_E(rgb_lab(actual),rgb_lab(direct),method='CIE 2000')
            self.assertLess(float(np.max(error)),5,name)
            self.assertLess(float(np.percentile(error,99)),2.5,name)

    def test_gold_brands_have_different_tonal_colour_directions(self):
        pp=[(32,32,32),(128,128,128),(224,224,224)]
        pentax=rgb_lab(self.out('pentax_gold',pp))
        kodak=rgb_lab(self.out('kodak_gold200',pp))
        self.assertLess(pentax[0,2],-5)
        self.assertGreater(pentax[2,2],7)
        self.assertLess(abs(pentax[1,2]),2)
        self.assertGreater(kodak[0,2],1)
        self.assertGreater(kodak[1,2],3)

    def test_satobi_fades_red_and_moves_blue_toward_cyan(self):
        pp=[(180,60,60),(60,90,200)]
        satobi=self.out('pentax_satobi',pp)
        dense=self.out('fuji_velvia50',pp)
        self.assertLess(np.linalg.norm(rgb_lab(satobi)[0,1:]),.70*np.linalg.norm(rgb_lab(dense)[0,1:]))
        h_in=colorsys.rgb_to_hsv(*(np.array(pp[1])/255))[0]*360
        h_out=colorsys.rgb_to_hsv(*(satobi[1]/255))[0]*360
        self.assertLess(h_out,h_in-5)

    def test_bleach_is_low_colour_without_becoming_a_colour_cast(self):
        out=rgb_lab(self.out('ricoh_bleach',self.pp))
        raw=rgb_lab(self.pp)
        ratio=np.linalg.norm(out[:,1:],axis=1)/np.maximum(1,np.linalg.norm(raw[:,1:],axis=1))
        self.assertLess(np.median(ratio),.55)
        white=rgb_lab(self.out('ricoh_bleach',[(240,240,240)]))[0]
        self.assertLess(np.linalg.norm(white[1:]),2)

    def test_hp5_is_neutral_at_every_native_node(self):
        raw=self.tables['ilford_hp5']
        self.assertEqual(raw[:TABLE:4],bytes([128])*4913)
        self.assertEqual(raw[1:TABLE:4],bytes([128])*4913)

    def test_gray_tone_is_monotone_and_native_metadata_matches(self):
        pp=np.repeat(np.linspace(0,255,257)[:,None],3,axis=1)
        for name in self.tables:
            with self.subTest(name=name):
                L=rgb_lab(self.out(name,pp))[:,0]
                self.assertGreaterEqual(np.diff(L).min(),-.5)
                self.assertEqual(space_for(self.root/('v2_'+name+'.bin')),NATIVE)

    def test_native_approximation_matches_direct_design(self):
        for name in self.tables:
            with self.subTest(name=name):
                native=rgb_lab(self.out(name,self.pp))
                direct=rgb_lab(grade(self.pp,self.data['profiles'][name]))
                errors=colour.delta_E(native,direct,method='CIE 2000')
                self.assertLess(np.percentile(errors,95),2.5)

    def test_curated_set_does_not_include_near_duplicate_fillers(self):
        # Project-specific gate on a declared probe set, not a universal JND or
        # proof of manufacturer fidelity. Similar variants remain local options.
        names=list(self.tables)
        rendered={n:rgb_lab(self.out(n,self.pp)) for n in names}
        for i,a in enumerate(names):
            for b in names[:i]:
                with self.subTest(a=a,b=b):
                    self.assertGreater(np.median(colour.delta_E(rendered[a],rendered[b],method='CIE 2000')),3)


if __name__=='__main__':unittest.main(verbosity=2)
