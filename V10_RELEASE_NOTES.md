# ARL Acquisition Interface V10 — Reliability Layer

V10 keeps the Spy Game behavior unchanged and adds acquisition reliability controls.

## Main additions

- Moderator-side session configuration panel.
- Select participant count and enabled modalities before the session starts.
- Participant-to-device mapping table.
- Setup lock before Start Session.
- Strict preflight gate before Start Session.
- Session manifest export.
- Global/participant folder organization.
- Participant-specific behavioral CSV export.
- Participant device map and quality log exports.
- Reserved modality export placeholders for future XDF-derived EEG/ECG/GSR/EMG/audio/video CSVs.

## Reliability rule

Start Session is blocked unless strict preflight is ready:

- setup is locked
- required participant screens are connected
- word pairs are available
- LSL marker stream is initialized
- LabRecorder QC is checked
- required participant-device mappings are complete
- enabled modalities are checked in QC

## Intended Phase 3 hardware test

Use one complete participant acquisition pipeline first:

- 1 Emotiv EEG
- 1 Shimmer ECG/GSR/EMG
- 1 camera
- 1 microphone

Then scale to five participants after the single-pipeline test is reliable.
