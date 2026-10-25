"""Export invariants without requiring a particular film dataset appearance."""
import unittest
from unittest.mock import patch
import numpy as np
import film_physics as fp
from native_codec import GRID,TABLE,slotwrap


class PhysicalExportTests(unittest.TestCase):
    def test_identity_reference_stays_identity_after_balancing_and_export(self):
        with patch.object(fp,'render',side_effect=lambda values,*args,**kw:np.asarray(values).copy()):
            raw,actual,meta=fp.build('identity reference',None,cube_size=17)
        expected=bytearray()
        for y in GRID:
            for cb in GRID:
                for cr in GRID:expected.extend((cr,cb,y,0))
        self.assertEqual(raw,slotwrap(expected))
        self.assertEqual(meta['boundary_extension'],'linear RGB cube boundary cells')

    def test_monochrome_reference_keeps_native_colour_axes_constant(self):
        def mono(values,*args,**kw):
            L=np.asarray(values)@np.array([.299,.587,.114])
            return np.repeat(L[...,None],3,axis=-1)
        with patch.object(fp,'render',side_effect=mono):
            raw,actual,meta=fp.build('mono reference',None,cube_size=17)
        self.assertEqual(raw[:TABLE:4],bytes([128])*4913)
        self.assertEqual(raw[1:TABLE:4],bytes([128])*4913)


if __name__=='__main__':unittest.main(verbosity=2)
