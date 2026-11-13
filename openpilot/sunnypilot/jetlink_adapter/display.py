"""Connection-aware UI text; never interpret cached progress as USB presence."""
import math
from typing import NamedTuple


class StatusText(NamedTuple):
  label: str
  detail: str


def status_text(status) -> StatusText:
  if status is None:
    return StatusText('unavailable', 'Jetlink status unavailable')
  if status.reason:
    return StatusText('unavailable', str(status.reason))
  if not status.enabled:
    return StatusText('off', 'Select USB or iOS to enable Jetlink')
  # Jetlink's phase intentionally describes model preparation, even when the
  # host is absent. Its progress record can outlive the connection or worker.
  if not status.present:
    label = 'disconnected' if status.port == 'empty' else 'waiting for host'
    return StatusText(label, 'No external computer detected; check USB and host power')
  if status.active:
    return StatusText('active', status.active_model or 'External model running')
  if status.phase == 'prepared':
    return StatusText('prepared', status.active_model or 'External model prepared')
  if status.phase == 'waiting':
    return StatusText('waiting', 'Ready to switch when assistance is disengaged')

  progress = status.progress or {}
  stage = str(progress.get('stage') or '').replace('_', ' ')
  message = str(progress.get('msg') or '').strip()
  detail = stage
  try:
    fraction = float(progress['frac'])
    if stage and stage not in ('connect', 'failed', 'ready') and math.isfinite(fraction) and 0 <= fraction <= 1:
      detail += f' {fraction:.0%}'
  except (KeyError, TypeError, ValueError):
    pass
  if message:
    detail = f'{detail}: {message}' if detail else message
  if detail:
    # The vendor record has no timestamp. Describe it as the last report,
    # rather than claiming the build is still advancing.
    return StatusText(status.phase, f'Last update: {detail}')
  if status.phase == 'preparing':
    return StatusText('connected', 'Waiting for preparation status')
  return StatusText(status.phase, f'USB connected; {status.phase}')
