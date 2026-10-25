import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from native_codec import (GRID,TABLE,NATIVE,LEGACY,compile_rgb,slotwrap,
    sample_rgb,record_native,space_for,rgb_grid_view,compile_uniform_rgb)
import gen_luts
from preview_photos import load_lut,apply_lut
from color_def import Lut
from migrate_rgb_library import migrate


def mono_design():
    data=bytearray()
    for b in GRID:
        for g in GRID:
            for r in GRID:
                y=round(.299*r+.587*g+.114*b)
                data.extend((y,y,y,0))
    return slotwrap(data)


class NativeCodecTests(unittest.TestCase):
    def test_constants_match_camera_accepted_encoding(self):
        for colour,expected in (((255,0,0),(255,85,76)),((0,0,255),(107,255,29)),
                                ((128,128,128),(128,128,128))):
            raw=slotwrap(bytes((*colour,0))*4913)
            actual=compile_rgb(raw)
            self.assertEqual(actual[:TABLE],bytes((*expected,0))*4913)
            self.assertEqual(actual[TABLE:],actual[TABLE-4:TABLE]*3+bytes(48))

    def test_mono_neutral_at_every_native_node(self):
        data=compile_rgb(mono_design())
        self.assertEqual(data[:TABLE:4],bytes([128])*4913)
        self.assertEqual(data[1:TABLE:4],bytes([128])*4913)

    def test_boundary_extension_preserves_identity_everywhere(self):
        raw=bytearray()
        for z in GRID:
            for y in GRID:
                for x in GRID:raw.extend((x,y,z,0))
        expected=slotwrap(raw)
        self.assertEqual(compile_rgb(expected),expected)
        nodes=[(r*255/4,g*255/4,b*255/4) for b in range(5) for g in range(5) for r in range(5)]
        self.assertEqual(compile_uniform_rgb(nodes,5),expected)
        self.assertNotEqual(compile_rgb(expected,boundary='clamp'),expected)

    def test_uniform_affine_mono_keeps_all_native_chroma_neutral(self):
        nodes=[]
        for b in range(3):
            for g in range(3):
                for r in range(3):
                    y=(.299*r+.587*g+.114*b)*255/2
                    nodes.append((y,y,y))
        raw=compile_uniform_rgb(nodes,3)
        self.assertEqual(raw[:TABLE:4],bytes([128])*4913)
        self.assertEqual(raw[1:TABLE:4],bytes([128])*4913)

    def test_constant_uniform_cube_matches_native_colour(self):
        raw=compile_uniform_rgb([(255,0,0)]*27,3)
        self.assertEqual(raw[:TABLE],bytes([255,85,76,0])*4913)

    def test_generator_native_and_rgb_design_are_distinct(self):
        p={'sat_env':0,'warm_guard':0,'cool_guard':0}
        design=gen_luts.build_rgb(p)
        result=gen_luts.build(p)
        self.assertEqual(result,compile_rgb(design))
        self.assertNotEqual(design,result)
        for y in GRID:
            self.assertEqual(result[((GRID.index(y)*17+8)*17+8)*4:][:3],bytes([128,128,y]))

    def test_cube_uses_uniform_positions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'identity.cube'
            gen_luts.write_cube({'sat_env':0,'warm_guard':0,'cool_guard':0},p)
            nodes=[line for line in p.read_text().splitlines() if line and line[0].isdigit()]
            self.assertAlmostEqual(float(nodes[15].split()[0]),15/16,delta=.5/255+1e-6)
            self.assertLess(float(nodes[15].split()[0]),240/255)

    def test_manifest_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mono.bin';raw=compile_rgb(mono_design());p.write_bytes(raw)
            record_native(p,raw)
            self.assertEqual(space_for(p),NATIVE)
            p.write_bytes(bytes([raw[0]^1])+raw[1:])
            with self.assertRaises(ValueError):space_for(p)

    def test_preview_and_lab_probes_decode_native(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mono.bin';raw=compile_rgb(mono_design());p.write_bytes(raw);record_native(p,raw)
            inputs=np.array([[(20,50,160),(230,180,100),(200,80,30),(247,242,250)]],dtype=np.float32)
            out=apply_lut(inputs,load_lut(p))
            self.assertTrue(np.all(out.max(2)==out.min(2)))
            for i,colour in enumerate(inputs[0]):
                expected=np.round(sample_rgb(raw,NATIVE,colour))
                self.assertLessEqual(np.max(np.abs(out[0,i]-expected)),1)
                probe=Lut(p).at(*colour)
                self.assertLess(max(probe)-min(probe),1e-5)
            grid=rgb_grid_view(p)
            self.assertTrue(all(grid[i]==grid[i+1]==grid[i+2] for i in range(0,TABLE,4)))

    def test_migration_is_repeatable_without_touching_source(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source';dest=Path(d)/'native';source.mkdir()
            raw=mono_design();(source/'mono.bin').write_bytes(raw)
            first=migrate(source,dest);again=migrate(source,dest)
            self.assertEqual(first,again)
            self.assertEqual((source/'mono.bin').read_bytes(),raw)
            self.assertEqual((dest/'mono.bin').read_bytes(),compile_rgb(raw))

    def test_factory_table_is_not_reencoded(self):
        p=Path(__file__).resolve().parents[2]/'looks/samsung_a00.bin'
        if not p.exists():self.skipTest('factory fixture unavailable')
        raw=p.read_bytes()
        self.assertEqual(space_for(p,raw),NATIVE)
        with self.assertRaises(ValueError):compile_rgb(raw)


if __name__=='__main__':unittest.main(verbosity=2)
