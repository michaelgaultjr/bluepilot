"""Host-side checks. These do not replace the Linux build or vehicle replay."""
import ast
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jetlink.openpilot.events import SwapEvents
from jetlink.openpilot.hooks import Hooks
from jetlink.openpilot.testing import check_fallback, check_seam
from openpilot.sunnypilot import jetlink_adapter as adapter
from openpilot.sunnypilot.jetlink_adapter.actions import with_blendful
from openpilot.sunnypilot.jetlink_adapter.failure import FailureLatch
from openpilot.sunnypilot.jetlink_adapter.display import status_text

ROOT = Path(__file__).resolve().parents[4]


class TestAdapter(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    env = patch.dict(os.environ, {'PARAMS_ROOT': self.tmp.name, 'OPENPILOT_PREFIX': 'test'})
    env.start()
    self.addCleanup(env.stop)
    self.params = Path(self.tmp.name) / 'test'
    self.params.mkdir()

  def test_missing_invalid_and_valid_modes(self):
    self.assertFalse(adapter.link_on())
    for value, expected in [('0', False), ('1', True), ('2', True), ('3', False), ('-1', False), ('bad', False)]:
      (self.params / 'JetlinkLink').write_text(value)
      self.assertEqual(adapter.link_on(), expected)

  def test_fallback_answers_all_used_hooks(self):
    for enabled in (False, True):
      with patch.object(adapter, 'link_on', return_value=enabled):
        self.assertEqual(check_fallback(adapter._Off('unavailable'), adapter.HOOK_NAMES, link_on=adapter.link_on), [])

  def test_disabled_hooks_do_not_bind_adapter(self):
    def fail():
      raise AssertionError('disabled model runner bound Jetlink')
    hooks = Hooks(adapter.API, fail, link_on=lambda: False)
    original = object()
    self.assertFalse(hooks.prepare(False))
    self.assertIs(hooks.attach(original, original, 1928, 1208), original)

  def test_chestnut_never_prepares_external_model(self):
    hooks = Hooks(adapter.API, lambda: self.fail('bound beside Chestnut'), link_on=lambda: True)
    self.assertFalse(hooks.prepare(True))

  def test_engagement_includes_paused_mads(self):
    op = adapter.adapter()
    for cruise, mads in ((False, False), (True, False), (False, True), (True, True)):
      sm = {'carControl': SimpleNamespace(enabled=cruise),
            'carControlSP': SimpleNamespace(mads=SimpleNamespace(enabled=mads))}
      self.assertEqual(op.engaged(sm), cruise or mads)

  def test_external_selection_does_not_rewrite_bp_catalogue(self):
    keys = adapter.adapter().keys
    self.assertFalse(keys.big_model)
    self.assertFalse(keys.catalog)

  def test_owner_configuration_is_lightweight(self):
    config = adapter.owner_config()
    self.assertEqual(config.params_dir, self.params)
    self.assertEqual(config.adapter, adapter.__name__)

  def test_modeld_contracts(self):
    for path in ('openpilot/selfdrive/modeld/modeld.py', 'openpilot/sunnypilot/modeld_v2/modeld.py'):
      self.assertEqual(check_seam(ROOT / path), [])

  def test_actions_preserve_base_result_and_apply_blendful(self):
    def base(*args):
      return SimpleNamespace(desiredCurvature=0.02, desiredAcceleration=0.3)
    action = with_blendful(base, 0.3)
    self.assertEqual(action(None, None, 0, 0, 10).desiredCurvature, 0.02)
    self.assertAlmostEqual(action(None, None, 0, 0, 10, lambda c: 0.01).desiredCurvature, 0.03)
    self.assertEqual(action(None, None, 0, 0, 0.1, lambda c: 0.01).desiredCurvature, 0.02)


class TestSelfdrivedIntegration(unittest.TestCase):
  """Execute the actual added event block with upstream's real SwapEvents."""
  def setUp(self):
    source = (ROOT / 'openpilot/selfdrive/selfdrived/selfdrived.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SelfdriveD')
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'update_events')
    start = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'in_control')
    end = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'loading')
    self.code = compile(ast.Module(body=fn.body[start:end], type_ignores=[]), '<selfdrived Jetlink block>', 'exec')
    class Messages(dict):
      alive = {'modelV2': True, 'modelDataV2SP': True}
      valid = {'modelV2': True, 'modelDataV2SP': True}
    self.sm = Messages(modelV2=SimpleNamespace(big=False), modelDataV2SP=SimpleNamespace(jetlinkState='none'))
    self.sd = SimpleNamespace(enabled=False, mads=SimpleNamespace(enabled=False), sm=self.sm,
                              jetlink_swaps=SwapEvents(.01), jetlink_failure=FailureLatch(), events=set(), events_sp=set())
    names = SimpleNamespace(bigModelLoading='loading', bigModelFailed='failed')
    custom = SimpleNamespace(OnroadEventSP=SimpleNamespace(EventName=SimpleNamespace(jetlinkReady='offer', bigModelReady='ready')))
    self.scope = {'self': self.sd, 'EventName': names, 'custom': custom}

  def tick(self, state, big=False):
    self.sd.events.clear()
    self.sd.events_sp.clear()
    self.sm['modelV2'].big = big
    self.sm['modelDataV2SP'].jetlinkState = state
    exec(self.code, self.scope)

  def test_off_adds_no_events(self):
    self.tick('none')
    self.assertEqual(self.sd.events | self.sd.events_sp, set())

  def test_missing_package_adds_no_events(self):
    self.sd.jetlink_swaps = None
    self.tick('none')
    self.assertEqual(self.sd.events | self.sd.events_sp, set())

  def test_ready_while_mads_paused_offers_switch(self):
    self.sd.mads.enabled = True
    self.tick('ready')
    self.assertIn('offer', self.sd.events_sp)

  def test_promotion_blocks_engagement_then_chimes(self):
    self.tick('running', True)
    self.assertIn('loading', self.sd.events)
    self.assertTrue(self.sd.jetlink_settling)
    for _ in range(100):
      self.tick('running', True)
    self.assertNotIn('loading', self.sd.events)
    self.assertIn('ready', self.sd.events_sp)

  def test_loss_soft_disables_until_both_modes_disengage(self):
    self.sd.enabled = True
    self.tick('running', True)
    self.tick('joining')
    self.assertIn('failed', self.sd.events)
    self.assertFalse(self.sd.jetlink_settling)
    for _ in range(600):
      self.tick('joining')
    self.assertIn('failed', self.sd.events)
    self.sd.enabled = False
    self.sd.mads.enabled = True
    self.tick('joining')
    self.assertIn('failed', self.sd.events)
    self.sd.mads.enabled = False
    self.tick('joining')
    self.assertNotIn('failed', self.sd.events)

  def test_offroad_loss_does_not_latch(self):
    self.tick('running', True)
    self.tick('joining')
    self.assertNotIn('failed', self.sd.events)

  def test_stale_state_does_not_offer_a_switch(self):
    self.sd.mads.enabled = True
    self.sm.valid = {'modelV2': True, 'modelDataV2SP': False}
    self.tick('ready')
    self.assertNotIn('offer', self.sd.events_sp)


class TestSharedControlReader(unittest.TestCase):
  def setUp(self):
    self.enterContext(patch.object(adapter, '_modeld_sm', None))
    self.op = adapter.adapter()
    self.op.__dict__['log'] = SimpleNamespace(exception=lambda *args: None)

  def snapshot(self, cruise=False, mads=False):
    class Snapshot(dict):
      def all_alive(self, services):
        return all(self.alive[s] for s in services)

      def all_valid(self, services):
        return all(self.valid[s] for s in services)

      def update(self, *_):
        raise AssertionError("Jetlink must not poll modeld's reader")

    sm = Snapshot(carState=object(), carControl=SimpleNamespace(enabled=cruise),
                  carControlSP=SimpleNamespace(mads=SimpleNamespace(enabled=mads)))
    sm.alive = dict.fromkeys(self.op.IN_CONTROL_SERVICES, True)
    sm.valid = dict.fromkeys(self.op.IN_CONTROL_SERVICES, True)
    return sm

  def test_unbound_reader_blocks_promotion_without_subscribing(self):
    self.assertTrue(self.op.in_control())
    self.assertIsNone(self.op._sm)

  def test_shared_reader_preserves_cruise_and_paused_mads_gate(self):
    for cruise, mads in ((False, False), (True, False), (False, True), (True, True)):
      sm = self.snapshot(cruise, mads)
      adapter.use_modeld_submaster(sm)
      for _ in range(3):
        self.assertEqual(self.op.in_control(), cruise or mads)
      self.assertIsNone(self.op._sm)

  def test_missing_stale_invalid_or_broken_input_blocks_promotion(self):
    for service in self.op.IN_CONTROL_SERVICES:
      for invalid in ('alive', 'valid'):
        sm = self.snapshot()
        getattr(sm, invalid)[service] = False
        adapter.use_modeld_submaster(sm)
        self.assertTrue(self.op.in_control())
      sm = self.snapshot()
      del sm.valid[service]
      adapter.use_modeld_submaster(sm)
      self.assertTrue(self.op.in_control())
    adapter.use_modeld_submaster(object())
    self.assertTrue(self.op.in_control())

  def test_both_model_runners_bind_their_existing_reader(self):
    for path in ('openpilot/selfdrive/modeld/modeld.py', 'openpilot/sunnypilot/modeld_v2/modeld.py'):
      tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
      main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
      binding = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Expr) and
                     isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'jetlink_adapter.use_modeld_submaster')
      setup = main.body[binding - 1:binding + 1]
      constructed = []
      def make_reader(services, constructed=constructed):
        self.assertTrue(set(self.op.IN_CONTROL_SERVICES) <= set(services))
        sm = self.snapshot()
        constructed.append(sm)
        return sm
      exec(compile(ast.Module(body=setup, type_ignores=[]), path, 'exec'),
           {'SubMaster': make_reader, 'jetlink_adapter': adapter})
      self.assertEqual(len(constructed), 1)
      self.assertIs(adapter._modeld_sm, constructed[0])
      self.assertFalse(self.op.in_control())


class TestStatusDisplay(unittest.TestCase):
  def snapshot(self, **changes):
    from jetlink.openpilot.status import Status
    data = {'enabled': True, 'mode': 'usb', 'transport': 'USB', 'present': False, 'port': 'empty',
            'ready': False, 'reason': None, 'progress': {'stage': 'build', 'frac': .5, 'msg': 'about 2 min left'},
            'model': 'external', 'default_model': 'external'}
    return Status(**(data | changes))

  def test_unplug_overrides_cached_build_and_ready_records(self):
    for ready in (False, True):
      status = self.snapshot(ready=ready)
      self.assertEqual(status.phase, 'preparing')  # reproduces the misleading raw phase
      text = status_text(status)
      self.assertEqual(text.label, 'disconnected')
      self.assertNotIn('build', text.detail)

  def test_cable_without_host_is_not_preparation(self):
    for port in ('host', None):
      self.assertEqual(status_text(self.snapshot(port=port)).label, 'waiting for host')

  def test_connected_progress_is_identified_as_last_report(self):
    text = status_text(self.snapshot(present=True, port='host'))
    self.assertEqual(text.label, 'preparing')
    self.assertEqual(text.detail, 'Last update: build 50%: about 2 min left')

  def test_connected_without_progress_does_not_claim_a_build(self):
    self.assertEqual(status_text(self.snapshot(present=True, port='host', progress=None)).label, 'connected')

  def test_off_errors_and_malformed_progress(self):
    self.assertEqual(status_text(self.snapshot(enabled=False)).label, 'off')
    self.assertEqual(status_text(self.snapshot(reason='service stopped')).detail, 'service stopped')
    for fraction in (None, 'bad', float('nan'), float('inf')):
      text = status_text(self.snapshot(present=True, progress={'stage': 'build', 'frac': fraction}))
      self.assertEqual(text.detail, 'Last update: build')


class TestPackaging(unittest.TestCase):
  def test_params_and_offroad_alert_are_registered(self):
    keys = (ROOT / 'openpilot/common/params_keys.h').read_text()
    for key in adapter.KEYS:
      self.assertIn('"' + key + '"', keys)
    alerts = json.loads((ROOT / 'openpilot/selfdrive/selfdrived/alerts_offroad.json').read_text())
    self.assertIn('Offroad_JetlinkUnavailable', alerts)


if __name__ == '__main__':
  unittest.main()
