# BluePilot with Jetlink

Both branches are published as **experimental source installation candidates**.
They build on Linux and have working comma installers. Jetlink starts **off**.
The comma 4 installation is undergoing bench troubleshooting; the complete
comma/Jetson connection and vehicle behavior have not yet been validated.

**BP 7 validation issue:** its existing Ford CAN safety suite fails identically
on the original BP 7 base and this Jetlink branch, including the angle-mode
corroboration test. The port preserves that code; it does not resolve or waive
those failures. These results do not establish that BP 7 with angle steering
and experimental longitudinal control is safe to drive.

## Choose a branch

| Branch | Base | Installation URL |
| --- | --- | --- |
| `bp-7.0-jetlink` | BP 7, retaining its Ford extras | https://installer.comma.ai/michaelgaultjr/bp-7.0-jetlink |
| `bp-sunnypilot-jetlink` | BluePilot's `bp-sunnypilot` (`bp-sp`) | https://installer.comma.ai/michaelgaultjr/bp-sunnypilot-jetlink |

For the requested 2020 Corsair setup, `bp-7.0-jetlink` retains the BP 7 features.
The alternate branch keeps its own upstream feature set. Neither branch changes
Ford vehicle controllers, fingerprints, CAN safety limits, panda or opendbc
revisions, or automatically selects angle steering or alpha longitudinal control.

The repository remains `michaelgaultjr/bluepilot`. GitHub's
`michaelgaultjr/openpilot` redirect lets the standard comma installer locate it.
Do not create a separate repository at that alias without replacing the links.
Both URLs were checked with comma 4 setup headers and returned ELF installers
containing the expected repository and branch.

## Install and set up while parked

1. Save the current branch and settings, and keep the known-good upstream
   installer available: https://installer.comma.ai/BluePilotDev/bp-7.0.
2. Enter the chosen full installation URL in the comma's software installation
   screen. This is a source install: allow the normal first-boot build and
   downloads to finish. Keep the comma powered and online. Visiting the URL in
   a desktop browser can show a device-only message.
3. Confirm BluePilot starts normally with **Jetlink Off** before connecting the
   external computer. Record the vehicle settings instead of assuming that
   installation will preserve them.
4. Set up the **Jetson Orin Nano Super Developer Kit (8 GB)** using the pinned
   [Jetlink v0.9.0 Jetson guide](https://github.com/zoompilot/jetlink/blob/v0.9.0/docs/jetson.md).
   That release documents JetPack 7.2.1 as tested; follow its hardware and power
   requirements. Use separate power for the Jetson and comma, and a USB 3
   **Jetson USB-A to comma USB-C data cable**. The comma cannot power the Jetson.
5. On the Jetson, install the matching release:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/zoompilot/jetlink/v0.9.0/install.sh -o /tmp/jetlink-install.sh
   bash /tmp/jetlink-install.sh --ref v0.9.0
   ```

   Choose power options matching the actual socket. A socket that turns off
   after parking is switched power. The guide explains sleep, battery
   protection, and when a fully powered-off Jetson needs a manual restart.
6. Offroad, select **Settings > Models > Jetlink (Experimental) > USB** on the
   comma. Enabling it disables ADB because they share the USB port.
7. Connect the cable and allow the external model to download and prepare.
   Choose it in the Jetlink web interface or host tools; BluePilot's normal
   model selector still chooses the local model. Check the state in Models and
   run `jetlink status` on the Jetson. This port does not reproduce Zoompilot's
   home-button icon. The status distinguishes **disconnected / waiting for host**
   from model preparation. Preparation details say **Last update** because the
   upstream progress record has no timestamp; they do not prove a build is still
   advancing. Vehicle detection and calibration are not prerequisites for USB
   enumeration or offroad preparation.
8. Keep the host release and selected model fixed during validation. The client
   pin does not freeze the remote model catalogue. `jetlink update` updates the
   host, so review compatibility before using it.

To stop using the integration, select **Jetlink Off** while parked and restart
BluePilot. To roll back the entire port, reinstall the previously recorded
known-good branch. Do not test unplugging or crashes on public roads.

## Integration behavior

- Adapted from Zoompilot and Jetlink's porting guide, with Jetlink v0.9.0 vendored
  unchanged. License, metadata, guide, and 39 file checksums are retained under
  `third_party/jetlink/`.
- Both stock and Sunnypilot tinygrad runners retain the local model. External
  promotion waits until cruise and MADS are disabled; paused MADS still counts
  as enabled. Engagement is blocked for one second after promotion.
- **Link loss during assistance triggers a latched soft-disable and takeover
  alert.** This differs from Zoompilot's continuation behavior. The latch clears
  only after cruise and MADS are both disabled. Availability of the local model
  does not promise uninterrupted assistance.
- Transition handling does not suppress ordinary communication/localization
  errors while assistance is enabled. Genuine Chestnut retains its existing path.
- The optional owner restarts after a crash. Missing/incompatible Jetlink gives
  an offroad error when enabled and leaves the local path available. Automatic
  shutdown waits at most 30 seconds for the host and blocks drive startup during
  that wait. Reboot is not treated as host shutdown.
- Both display layouts provide local, offroad-only Off/USB/iOS controls. Jetlink
  parameters are not remotely writable through Sunnylink.
- BP 7 needed compatibility work for its older model-call API, camera-warp
  assets, schema, and navigation. Shared Sunnypilot ancestry was not sufficient
  to copy the Zoompilot integration unchanged.

## Validation on November 13, 2026

Tests ran on Ubuntu 24.04 x86-64 with each branch's pinned dependencies and
submodules. These are host tests, not ARM/QCOM device or vehicle validation.

| Check | `bp-7.0-jetlink` | `bp-sunnypilot-jetlink` |
| --- | --- | --- |
| Full native Linux build | Passed | Passed |
| Integration: native interfaces, both cameras, real local inference/reset, owner restart, cruise/MADS loss | 25 passed | 24 passed |
| Existing Ford vehicle/control and cruise state tests | 60 passed, 15 subtests | Included below |
| Existing MADS tests | 10 passed | Included below |
| Existing Ford safety, vehicle, cruise and MADS suite | Ford safety failures below | 209 passed, 164 skipped, 9,137 subtests |
| Connection display: unplugged/stale progress, waiting, connected, invalid progress | 5 passed | 5 passed |
| Both settings layouts: render, USB selection, ADB clearing, onroad lockout | Passed under Xvfb | Passed under Xvfb |
| Edited Python lint/syntax, whitespace, vendored checksums | Passed | Passed |

The unmodified Jetlink v0.9.0 `tests/openpilot`, owner, root, and gadget suites
passed **917 tests and 200 subtests**, with 4 skips on Linux. Earlier
Windows-only timing failures did not reproduce there; vendor code was not
patched to obtain these results.

The **BP 7 Ford safety suite is not passing**. The same isolated command on
original base `773f7f1` and the Jetlink branch produced identical results:
pytest reported **22,556 failures, 487 passes, 279 skips, and 1,930 passing
subtests**. The same 50 test method names failed on both. The opendbc tree and
panda revision are identical Git objects. A separate baseline checkout supplied
original vehicle/safety code; both used the built common runtime libraries.
This establishes that the observed failures predate the port, not that they are
harmless.

Reproduce after normal Linux dependency/submodule/LFS setup and build:

```sh
# BP 7; on bp-sunnypilot prefix the integration path with openpilot/
python -m unittest discover -s sunnypilot/jetlink_adapter/tests -p 'test_*.py' -v

# Ford safety, independently of application test fixtures
cd opendbc_repo
PYTHONPATH="$PWD:$PWD/.." python -m pytest --confcutdir=. -o addopts= -q opendbc/safety/tests/test_ford.py
```

Before driving, remaining validation includes comma 4 first boot and QCOM
execution, the intended model on the Jetson, model replay, bench tests of
unplug/crash/reconnect/lag/power/shutdown, alert timing and MADS behavior, thermal
and frame-time measurements, and resolution/review of BP 7 safety failures.
Controlled-course evaluation must use the actual Corsair and steering/
longitudinal configuration. None of those device/road checks was performed here.
AI assistance was used in authoring this port.

## Pinned sources

| Component | Revision |
| --- | --- |
| BluePilot `bp-7.0` | `773f7f1dc27cd10d622576a5074de4fefe60da73` |
| BluePilot `bp-sunnypilot` | `4e21f4974844725398af44b6cfd8d04907825904` |
| Zoompilot adapter/Blendful reference | `b51270b7b00a5b0a2b78c3acfdbca4be236ad255` |
| Jetlink `v0.9.0` | `9cfde98eec1d7cc714d800504944cf1a3944513d` |

References: [porting guide](https://github.com/zoompilot/jetlink/blob/v0.9.0/docs/porting.md),
[Zoompilot reference](https://github.com/zoompilot/zoompilot/tree/b51270b7b00a5b0a2b78c3acfdbca4be236ad255),
[installer alias documentation](https://github.com/sunnypilot/openpilot-installer-generator/blob/main/README.md).
