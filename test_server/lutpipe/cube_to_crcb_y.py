#!/usr/bin/env python3
"""Offline RGB .cube -> Cr,Cb,Y slot reference, no camera IO.

The channel layout has live neutral/colour probe evidence. BT.601 full-range
coefficients are an explicit working matrix, not a calibrated camera profile.
Use original .cube inputs; never reinterpret factory slot bytes as RGB.
"""
import argparse
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cube_rgb_reference", Path(__file__).resolve().parents[1] / "isp" / "nx3dlut.py")
rgb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rgb)


def clamp(v):
    return max(0.0, min(1.0, v))


def input_rgb(cr, cb, y):
    cr, cb = cr - 128, cb - 128
    return tuple(clamp(v / 255.0) for v in (
        y + 1.402 * cr, y - 0.714136 * cr - 0.344136 * cb, y + 1.772 * cb))


def output_crcb_y(values):
    r, g, b = (clamp(v) * 255 for v in values)
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return bytes(max(0, min(255, int(v + 0.5))) for v in (cr, cb, y)) + b"\0"


def convert(cube):
    if cube.kind != "3D" or cube.dmin != [0.0] * 3 or cube.dmax != [1.0] * 3:
        raise ValueError("requires a 3D cube with DOMAIN 0..1")
    nodes = rgb.norm_nodes(cube)
    out = bytearray()
    for y in rgb.hw_grid_u8():
        for cb in rgb.hw_grid_u8():
            for cr in rgb.hw_grid_u8():
                value = rgb.sample_trilinear(nodes, cube.n, input_rgb(cr, cb, y))
                out.extend(output_crcb_y(value))
    out.extend(out[-4:] * 3 + bytes(48))
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    a = ap.parse_args()
    data = convert(rgb.parse_cube(a.source, order="rgb"))
    a.output.write_bytes(data)
    print(f"{a.source.name}: {len(data)} B, Cr/Cb/Y, BT.601 full-range reference")


if __name__ == "__main__":
    main()
