# ARL Acquisition Interface V10.1 — One-Station Development Mode

Goal: remove strict testing restrictions so one participant station can be validated first.

## Changed
- Start Session no longer requires full setup lock, full participant connection, device map completion, LabRecorder QC confirmation, or modality QC confirmation.
- Minimum start requirements are now only:
  - word pairs available
  - LSL marker stream available
- The moderator still sees all checklist items as warnings/status indicators.
- The UI text now frames this as One-Station Setup for hardware integration.

## Why
The project should first validate one complete acquisition pipeline: one Emotiv, one Shimmer, one camera, and one microphone. Strict production-style gating will be reintroduced after that station is stable.

## Unchanged
- Spy Game logic
- Behavioral saving
- LSL markers
- XDF recording workflow with LabRecorder
- CSV/JSON exports
