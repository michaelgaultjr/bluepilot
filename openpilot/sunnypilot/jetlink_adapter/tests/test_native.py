"""Run after a full Linux BluePilot build, separately from portable checks."""
import unittest

from jetlink.openpilot import STATES
from jetlink.openpilot.testing import check_adapter
from openpilot.sunnypilot import jetlink_adapter
from openpilot.common.test import OpenpilotTestCase


class TestNativeAdapter(OpenpilotTestCase):
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


if __name__ == '__main__':
  unittest.main()
