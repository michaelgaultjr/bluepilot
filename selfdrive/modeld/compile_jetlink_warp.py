#!/usr/bin/env python3
"""Build Jetlink's two-camera warp using BP 7's own NV12 conversion kernels."""
import argparse
import pickle

import numpy as np
from tinygrad.tensor import Tensor
from tinygrad.engine.jit import TinyJit
from openpilot.system.camerad.cameras.nv12_info import get_nv12_info
from openpilot.selfdrive.modeld.compile_modeld import NV12Frame, make_frame_prepare, _parse_size


def compile_warp(cam_w, cam_h, model_w, model_h, output):
  nv12 = NV12Frame(cam_w, cam_h, *get_nv12_info(cam_w, cam_h))
  prepare = make_frame_prepare(nv12, model_w, model_h)

  @TinyJit
  def run(input_frame, M_inv):
    return Tensor.stack(prepare(input_frame[0], M_inv[0]), prepare(input_frame[1], M_inv[1])).realize()

  specs = {'input_frame': ((2, nv12.size), np.uint8, 'NPY'), 'M_inv': ((2, 3, 3), np.float32, 'NPY')}
  inputs = {key: Tensor(np.zeros(shape, dtype=dtype), device=device).realize() for key, (shape, dtype, device) in specs.items()}
  inputs['M_inv'].assign(Tensor(np.tile(np.eye(3, dtype=np.float32), (2, 1, 1)), device='NPY')).realize()
  for _ in range(3):
    run(**inputs)
  with open(output, 'wb') as f:
    pickle.dump({'run': run, 'input_specs': specs}, f)


if __name__ == '__main__':
  p = argparse.ArgumentParser()
  p.add_argument('--camera-resolution', type=_parse_size, required=True)
  p.add_argument('--warp-to', type=_parse_size, required=True)
  p.add_argument('--output', required=True)
  args = p.parse_args()
  compile_warp(*args.camera_resolution, *args.warp_to, args.output)
