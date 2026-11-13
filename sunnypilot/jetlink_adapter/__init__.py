"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of zoompilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

jetlink on this fork: the adapter jetlink runs over, and the hooks manager,
modeld, hardwared, selfdrived, the model manager and the UI call.

jetlink (the jetlink_repo submodule) runs the large driving model on an
attached Jetson, Mac or iPhone. Its stock adapter (jetlink.openpilot.stock)
knows stock openpilot's paths; Adapter below is that with this fork's param
names, its modeld_v2 and MADS. The hooks (jetlink.openpilot.hooks) never raise
and answer as if the link were off when jetlink is not checked out, or speaks
another API.

comma's chestnut board is not jetlink's business: modeld, hardwared and the
UI handle it natively, and jetlink keeps the link off while one is fitted.

manager imports this module to build the process list, and runs it as
jetlinkd, the resident gadget owner, which stays at about 10 MB for the whole
drive. So the top level is the standard library only; everything else is
imported where it is used. tests/test_adapter.py holds the line.
"""
from __future__ import annotations

import functools
import os
import threading
from collections import namedtuple
from pathlib import Path

# the version of jetlink.openpilot's API this adapter is written to; any other
# is treated as jetlink being absent, with the reason as the offroad alert
API = 3

# the gadget owner, as manager names the process and selfdrived lists it
OWNER = 'jetlinkd'

# the Jetlink setting, stored as an index: jetlink.openpilot.MODES,
# written out so the panels build the setting without a jetlink checkout
MODES = ('off', 'usb', 'ios')

# External model selection belongs to the Jetlink app; BP Chestnut selection stays independent.
_Keys = namedtuple('_Keys', 'link offroad progress spec charge_phone')
KEYS = _Keys(link='JetlinkLink', offroad='IsOffroad', progress='JetlinkProgress',
             spec='JetlinkSpec', charge_phone='JetlinkChargePhone')

_AGNOS = os.path.isfile('/AGNOS')

# modeld already reads these messages. A second carState subscription exceeds
# BP 7's msgq reader limit and evicts calibration/localization readers.
_modeld_sm = None


def use_modeld_submaster(sm) -> None:
  """Borrow modeld's frame snapshot; never open or poll another subscriber."""
  global _modeld_sm
  _modeld_sm = sm


def _params_dir() -> Path:
  """The params store's directory, by params.cc and hw.h's rule: PARAMS_ROOT,
  else /data/params on a device and $HOME/.comma<OPENPILOT_PREFIX>/params
  elsewhere, then /<OPENPILOT_PREFIX, or d>. Stock.params_dir() without
  jetlink. Per call, so it follows a prefix as Params does; the environment
  only, so it never raises."""
  prefix = os.environ.get('OPENPILOT_PREFIX', '')
  root = os.environ.get('PARAMS_ROOT')
  if root is None:
    root = '/data/params' if _AGNOS else os.environ.get('HOME', '') + '/.comma' + prefix + '/params'
  return Path(root) / os.environ.get('OPENPILOT_PREFIX', 'd')


def link_on() -> bool:
  """Is the Jetlink setting on? As jetlink reads it, a file, so that a jetlink
  this build cannot use tells only someone who turned the link on."""
  try:
    return 0 < int((_params_dir() / KEYS.link).read_bytes()) < len(MODES)
  except (OSError, ValueError):
    return False


@functools.cache
def _adapter_class():
  from jetlink.openpilot.interface import Keys
  from jetlink.openpilot.stock import Stock

  class Adapter(Stock):
    """jetlink.openpilot.interface.Openpilot over this fork: stock openpilot
    but for what follows."""
    KEYS = Keys(**KEYS._asdict())
    WARP_DIR = 'selfdrive/modeld/models'

    def camera(self):
      from openpilot.system.hardware import HARDWARE
      from openpilot.common.transformations.camera import _ar_ox_fisheye, _os_fisheye
      from openpilot.common.transformations.model import MEDMODEL_INPUT_SIZE
      camera = _os_fisheye if HARDWARE.get_device_type() == 'mici' else _ar_ox_fisheye
      return camera.width, camera.height, *MEDMODEL_INPUT_SIZE

    def model_root(self):
      from openpilot.system.hardware.hw import Paths
      return Path(Paths.model_root())

    def in_control(self) -> bool:
      # Called on modeld's frame thread, after its sm.update(0). Do not update
      # that reader again: doing so would consume its per-frame update flags.
      sm = _modeld_sm
      if sm is None:
        return True  # no frame snapshot yet: never allow promotion
      try:
        services = self.IN_CONTROL_SERVICES
        result = not (sm.all_alive(services) and sm.all_valid(services)) or self.engaged(sm)
      except Exception as e:
        if self._in_control_error != (text := f"{type(e).__name__}: {e}"):
          self._in_control_error = text
          try:
            self.log.exception("jetlink: in_control() failed: %s", text)
          except Exception:
            pass
        return True
      self._in_control_error = None
      return bool(result)

    # MADS's state rides on carControlSP
    IN_CONTROL_SERVICES = ('carState', 'carControl', 'carControlSP')

    def chestnut_present(self) -> bool:
      # modeld's own test, the one it runs the big model on: a chestnut whose
      # firmware names itself. The owner's port walk is wider (CHESTNUT_IDS,
      # running or in its ROM), so it never holds a chestnut as a host
      from openpilot.selfdrive.modeld.helpers import usbgpu_present
      return usbgpu_present()

    def model_constants(self):
      # modeld_tinygrad reads modeld_v2's off the model
      from openpilot.sunnypilot.modeld_v2.constants import ModelConstants
      return ModelConstants

    def action_function(self):
      # modeld_v2 passes Blendful's correction as a callback on the raw curvature, as stock modeld now does
      from openpilot.selfdrive.modeld.modeld import MIN_LAT_CONTROL_SPEED, get_action_from_model
      from openpilot.sunnypilot.jetlink_adapter.actions import with_blendful
      return with_blendful(get_action_from_model, MIN_LAT_CONTROL_SPEED)

    def engaged(self, sm) -> bool:
      # selfdrived's enabled or mads.enabled, as controlsd republishes them.
      # MADS counts with its lateral paused (a stop, a blinker, the brake): it
      # steers again on its own
      return bool(sm['carControl'].enabled or sm['carControlSP'].mads.enabled)

  return Adapter


def adapter():
  """The adapter, for jetlink's entry points that run as their own process:
  the provisioning run."""
  return _adapter_class()()


def owner_config():
  """What jetlinkd needs: data only, so the owner imports nothing heavy."""
  return _adapter_class().owner_config()


def main() -> None:
  """jetlinkd: hold the USB gadget until manager stops this process."""
  _adapter_class().main()


# -- the hooks ----------------------------------------------------------------

# this process's hooks, made on first use and kept, the link off included:
# Python does not cache a failed import. One per process, so that prepare()
# and attach() reach the same jetlink
_hooks = None
_making = threading.Lock()


def hooks():
  """jetlink.openpilot.hooks.Hooks over this adapter, or the link off."""
  global _hooks
  with _making:
    if _hooks is None:
      _hooks = _guard()
    return _hooks


def _guard():
  # inside a function, so a jetlink that fails to import lands here too
  try:
    import jetlink
    if getattr(jetlink, '__file__', None) is None:
      return _Off()   # an empty jetlink_repo, which Python takes for a namespace package
    from jetlink.openpilot.hooks import Hooks
  except ModuleNotFoundError as e:
    if e.name == 'jetlink':
      return _Off('Jetlink package is missing')
    if (e.name or '').startswith('jetlink.'):
      return _unusable("jetlink package too old for this build", e)
    return _unusable(f"jetlink failed to load: {e}", e)
  except Exception as e:
    return _unusable(f"jetlink failed to load: {type(e).__name__}: {e}", e)
  try:
    return Hooks(API, adapter, link_on=link_on, log=_cloudlog)
  except Exception as e:
    return _unusable(str(e), e)   # another API, which it names


def _cloudlog():
  from openpilot.common.swaglog import cloudlog
  return cloudlog


def _unusable(why: str, error: Exception) -> _Off:
  try:
    _cloudlog().error("jetlink: %s", why, exc_info=error)
  except Exception:
    pass
  return _Off(why)


class _Off:
  """Every hook with the link off; reason() says why, to someone who turned
  the link on. The fork's own: jetlink's Off cannot answer for a jetlink that
  is missing or too old to have it, and one answer for every case keeps them
  alike."""
  # by hook; a callable is handed the hook's arguments. A wanted power-off goes
  # ahead: no jetlink must keep a comma on to drain the car's battery
  ANSWERS = {'should_run': False, 'status': None, 'prepare': False, 'attach': lambda model, *_: model,
             'handed_over': False, 'state': 'none', 'shutdown_step': lambda wanted, reason='': wanted,
             'model_state': None, 'should_extend_catalog': False, 'extend_catalog': lambda catalog: catalog,
             'swap_events': None, 'runtime': None}

  def __init__(self, why: str = ''):
    self.why = why

  def reason(self) -> str | None:
    return self.why if self.why and link_on() else None

  def __getattr__(self, name: str):
    if name not in self.ANSWERS:
      raise AttributeError(name)
    answer = self.ANSWERS[name]
    return answer if callable(answer) else lambda *args: answer


def _hook(name: str):
  def call(*args):
    return getattr(hooks(), name)(*args)
  call.__name__ = call.__qualname__ = name
  return call


# the hooks by the names the hook lines call, each this process's hooks() at
# the call: jetlink.openpilot.hooks says what each does and answers
HOOK_NAMES = (*_Off.ANSWERS, 'reason')
(should_run, status, prepare, attach, handed_over, state, shutdown_step, model_state, should_extend_catalog,
 extend_catalog, swap_events, runtime, reason) = map(_hook, HOOK_NAMES)

