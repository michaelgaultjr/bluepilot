"""Keep a Jetlink loss latched until both assistance modes disengage."""


class FailureLatch:
  def __init__(self):
    self.failed = False

  def update(self, link_lost: bool, in_control: bool) -> bool:
    self.failed = bool(in_control and (self.failed or link_lost))
    return self.failed
