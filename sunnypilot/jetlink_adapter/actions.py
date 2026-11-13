# Adapted from Zoompilot, Copyright (c) 2026 Zeph Leggett, MIT licensed.
def with_blendful(get_action_from_model, min_lat_control_speed: float):
  """Stock modeld's action function taking Blendful's callback as modeld_v2's does. Stock leaves the curvature
  unsmoothed (LAT_SMOOTH_SECONDS 0), so the correction added to its answer is the one modeld_v2 adds before smoothing."""
  def action(model_output, prev_action, lat_action_t, long_action_t, v_ego, blendful=None):
    action = get_action_from_model(model_output, prev_action, lat_action_t, long_action_t, v_ego)
    if blendful is not None:
      correction = blendful(action.desiredCurvature)
      if v_ego > min_lat_control_speed:
        action.desiredCurvature += correction
    return action
  return action
