# BluePilot Jetlink integration — development only

This is an uninstalled development port, not a road-validated build. Jetlink is off
by default. No Ford vehicle controller, vehicle fingerprint, CAN safety limit,
panda revision, or opendbc revision was changed.

## Pinned sources

| Component | Revision |
| --- | --- |
| BluePilot `bp-sunnypilot` (installation short name `bp-sp`) | `4e21f4974844725398af44b6cfd8d04907825904` |
| Zoompilot `main`, adapter and Blendful bridge reference | `b51270b7b00a5b0a2b78c3acfdbca4be236ad255` |
| Jetlink `v0.9.0`, vendored comma package | `9cfde98eec1d7cc714d800504944cf1a3944513d` |

The Jetlink package under `jetlink/` is copied from that release, with line
endings normalized. Its license, package metadata, README, and the release's
porting guide are retained under `third_party/jetlink/`. The adapter and action
bridge retain Zoompilot attribution. `third_party/jetlink/manifest.json` records
the exact vendored package content. Upstream URLs:

- https://github.com/BluePilotDev/bluepilot/tree/bp-sunnypilot
- https://github.com/zoompilot/zoompilot/tree/b51270b7b00a5b0a2b78c3acfdbca4be236ad255
- https://github.com/zoompilot/jetlink/blob/v0.9.0/docs/porting.md

## Behavior and deliberate differences

- Both stock and Sunnypilot tinygrad model runners wrap their existing small
  model with Jetlink. The port does not replace either runner's normal path.
- Actual Chestnut hardware retains its native path. A USB host cable is not
  mistaken for Chestnut while Jetlink is enabled.
- Jetlink's readiness state travels alongside each model message. Switching
  and no-entry events use this state rather than a periodically written status
  file. The readiness check includes ordinary engagement and MADS enabled,
  including MADS paused, matching Zoompilot's adapter.
- **Different from Zoompilot:** loss while either assistance mode is enabled
  adds BluePilot's existing `bigModelFailed` soft-disable event. This is latched
  until both cruise and MADS are disabled. The small model is available during
  the transition; the port does not promise uninterrupted assistance.
- Expected settling frames are forgiven only with neither assistance mode
  enabled. Genuine communication/localization errors while engaged are not
  suppressed by the Jetlink settling flag.
- The owner process may restart after a crash. Missing or incompatible Jetlink
  falls back through the adapter and reports an offroad error when enabled.
- Automatic shutdown waits at most 30 seconds for Jetlink. Drive startup is
  blocked during that wait. Reboot behavior is not changed to power off the host.
- Both display layouts have a local, offroad-only Off/USB/iOS control. Enabling
  Jetlink clears ADB; the ADB controls are unavailable while Jetlink is enabled.
  The comma and host need separate power.
- **External model choice belongs to the Jetlink app/server.** The BluePilot
  Chestnut catalogue is deliberately not repurposed. There is no new Sunnylink
  remote control or automatic catalogue migration. Pin the external model and
  host release during validation; vendoring the client does not pin the host's
  model catalogue.

## Validation

Local results, November 13, 2026:

- Portable BluePilot integration tests: 17 passed.
- Python lint on the edited integration files: passed.
- Both model-runner contract checks from Jetlink: passed.
- Jetlink's unmodified v0.9.0 event/hook/joining suites on Windows: 152 passed,
  2 failed, 73 subtests passed. A diagnostic rerun using `perf_counter` as the
  monotonic clock passed 153, with 1 failure still remaining. The remaining
  failure is `RuntimeRecordTest.test_a_wake_while_a_record_is_written_is_not_lost`.
  Its cause is unresolved; do not treat it as harmless or hide it. Reproduce on
  Linux before approving this port. No upstream Jetlink code was changed to
  make these tests pass.
- Full native build, native integration tests, replay, UI rendering, USB timing,
  and vehicle testing: not run. No usable Linux development distro or running
  Docker engine was available in this workspace.

Portable checks execute the actual added selfdrived event block with Jetlink's
real event tracker, and check off/absent behavior, MADS, promotion/no-entry,
failure latching, stale state, adapter fallback hooks, both model-runner seams,
and the action bridge. They do not instantiate the real model GPU or controls.

From the repository root:

```sh
python -m unittest discover -s openpilot/sunnypilot/jetlink_adapter/tests -p test_portable.py -v
```

After installing the normal Linux BluePilot development dependencies,
initializing its pinned submodules, downloading LFS assets, and building native
libraries and schema:

```sh
python -m unittest discover -s openpilot/sunnypilot/jetlink_adapter/tests -p test_native.py -v
```

The native suite must not be counted as passed without that environment.
The initial Windows checkout has LFS pointers and uninitialized vehicle/runtime
submodules. It is source for review, not an installable release artifact.

## Gates before an installation candidate

1. Full Linux/device build, compiled schema and params tests, adapter conformance,
   process lifecycle tests, and existing BluePilot/Ford safety tests.
2. Model replay for both runners and every intended small-model format, with
   Jetlink disabled and enabled; compare baseline-disabled behavior and confirm
   output formats, recurrent-state reset, calibration, and action timing.
3. Bench tests on the actual comma and external host: cold start, unplug,
   process crash, repeated reconnect, bad output, sustained lag, failed
   preparation, sleep/wake, reboot, shutdown, and depleted/unstable power.
4. UI review on the actual comma, takeover alert timing, complete MADS/cruise
   state-machine traces, and no-entry timing around model transitions.
5. Thermal soak with measured frame-time distribution and missed deadlines;
   validate host cooling, power, model checksum, and USB cable.
6. BluePilot/Jetlink maintainer review, then controlled-course evaluation for
   the 2020 Corsair with the user's actual longitudinal-control configuration.

Do not infer safety from compilation, the portable tests, or shared Sunnypilot
ancestry. Preserve the installed known-good branch and settings before any
future device work. No device installation, external publication, or road test
was performed for this port. AI assistance was used in authoring this change.
