"""Run after a full Linux BluePilot build, separately from portable checks."""
import unittest

from jetlink.openpilot import STATES
from jetlink.openpilot.testing import check_adapter
from openpilot.sunnypilot import jetlink_adapter
from openpilot.common.prefix import OpenpilotPrefix


class TestNativeAdapter(unittest.TestCase):
  def setUp(self):
    self.enterContext(OpenpilotPrefix())

  def test_real_interface(self):
    self.assertEqual(check_adapter(jetlink_adapter, heavy=(
      'numpy', 'capnp', 'zmq', 'openpilot.cereal', 'openpilot.common.params', 'openpilot.common.swaglog',
    )), [])

  def test_compiled_schema_and_parameter_library(self):
    from openpilot.cereal import custom
    from openpilot.common.params import Params
    params = Params()
    for name in jetlink_adapter.KEYS:
      self.assertIsNotNone(params.get_type(name))
    message = custom.ModelDataV2SP.new_message()
    for state in STATES:
      message.jetlinkState = state
      self.assertEqual(message.jetlinkState, state)
    self.assertIsNotNone(custom.OnroadEventSP.EventName.jetlinkReady)

  def test_real_camera_model_and_storage_interfaces(self):
    from pathlib import Path
    from openpilot.cereal import log
    import numpy as np
    op = jetlink_adapter.adapter()
    self.assertEqual(len(op.camera()), 4)
    self.assertIsInstance(op.chestnut_present(), bool)
    self.assertIsInstance(op.model_root(), Path)
    face = op.model_face()
    self.assertTrue(callable(face.parser().parse_outputs))
    action = face.get_action_from_model({'action': np.zeros((1, 2))}, log.ModelDataV2.Action(), .2, .3, 10.)
    self.assertEqual(action.desiredAcceleration, 0.)
    self.assertEqual(action.desiredCurvature, 0.)

  def test_built_warps_accept_both_camera_sizes(self):
    from jetlink.openpilot.warp import Warps, Warp
    from openpilot.system.camerad.cameras.nv12_info import get_nv12_info
    import numpy as np
    warps = Warps(jetlink_adapter.adapter())
    for width, height in ((1344, 760), (1928, 1208)):
      size = get_nv12_info(width, height)[3]
      warp = Warp(warps.load(width, height, 512, 256), size)
      blank = np.zeros(size, dtype=np.uint8)
      transform = np.eye(3, dtype=np.float32)
      warp.start(blank.ctypes.data, blank.ctypes.data, transform, transform)
      warp.wait()
      self.assertEqual(len(warp.output), 2 * 6 * 128 * 256)
      self.assertFalse(any(warp.output))

  def test_loss_drives_real_cruise_and_mads_state_machines(self):
    from types import SimpleNamespace
    from openpilot.cereal import log, custom
    from openpilot.selfdrive.selfdrived.events import Events, ET
    from openpilot.selfdrive.selfdrived.state import StateMachine
    from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP
    from openpilot.sunnypilot.mads.state import StateMachine as MadsStateMachine
    events, events_sp = Events(), EventsSP()
    cruise = StateMachine()
    sd = SimpleNamespace(events=events, events_sp=events_sp, state_machine=cruise, enabled=True)
    mads = MadsStateMachine(SimpleNamespace(selfdrive=sd))
    cruise.state = log.SelfdriveState.OpenpilotState.enabled
    mads.state = custom.ModularAssistiveDrivingSystem.ModularAssistiveDrivingSystemState.enabled
    events.add(log.OnroadEvent.EventName.bigModelFailed)
    self.assertTrue(events.contains(ET.NO_ENTRY))
    for _ in range(305):
      sd.enabled, _ = cruise.update(events)
      lateral_enabled, _ = mads.update()
    self.assertFalse(sd.enabled)
    self.assertFalse(lateral_enabled)


if __name__ == '__main__':
  unittest.main()
