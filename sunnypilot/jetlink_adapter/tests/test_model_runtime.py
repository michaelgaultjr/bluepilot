"""Exercise real local inference and the exact reset used after a link loss."""
import unittest
from types import SimpleNamespace

import numpy as np
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.selfdrive.modeld.modeld import ModelState
from openpilot.system.camerad.cameras.nv12_info import get_nv12_info
from jetlink.openpilot.warp import prepare_reset


class TestModelRuntime(unittest.TestCase):
  def test_stock_history_reset_reproduces_first_frame(self):
    with OpenpilotPrefix():
      width, height = 1344, 760
      model = ModelState(width, height, False)
      reset = prepare_reset(model)
      frame = np.full(get_nv12_info(width, height)[3], 128, dtype=np.uint8)
      bufs = {name: SimpleNamespace(data=frame) for name in model.vision_input_names}
      transforms = {name: np.eye(3, dtype=np.float32) for name in bufs}

      def run():
        inputs = {'desire_pulse': np.zeros(8, dtype=np.float32),
                  'traffic_convention': np.array([1., 0.], dtype=np.float32),
                  'action_t': np.array([.25, .35], dtype=np.float32)}
        return {k: v.copy() for k, v in model.run(bufs, transforms, inputs, False).items()}

      initial = run()
      for _ in range(5):
        run()
      reset()
      restored = run()
      self.assertEqual(initial.keys(), restored.keys())
      for name in initial:
        self.assertTrue(np.isfinite(restored[name]).all(), name)
        np.testing.assert_allclose(restored[name], initial[name], rtol=1e-5, atol=1e-6, err_msg=name)


if __name__ == '__main__':
  unittest.main()
