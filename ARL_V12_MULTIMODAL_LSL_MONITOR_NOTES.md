# ARL V12 — Multimodal LSL Monitor (Sprint 1)

## Purpose
Extend the existing EEG-only LSL preflight into a hardware-agnostic acquisition discovery layer without controlling EmotivPRO, ConsensysPRO, LabRecorder, or physiological hardware.

## Added
- `app/acquisition_lsl_monitor.py`
- `GET /api/status/acquisition`

## Detected modality classes
- EEG
- ECG
- EMG
- GSR / EDA
- Eye tracking
- Markers
- Audio
- Video
- Other

## Metadata returned for each visible LSL stream
- Native stream name and type
- ARL modality classification
- Source ID and UID
- Hostname
- Channel count and channel labels
- Nominal sampling rate
- Channel format
- LSL creation time
- Participant hint when P1–P5 is encoded in stream metadata
- Non-invasive sample availability check for continuous streams
- Validation status and warnings

## Compatibility
The existing `/api/status/eeg` endpoint and `eeg_lsl_monitor.py` remain unchanged.

## First hardware validation
1. Start ARL.
2. Start ConsensysPRO with one Shimmer modality (ECG first).
3. Enable its native LSL output.
4. Open `http://127.0.0.1:8000/api/status/acquisition`.
5. Record the exact stream name, type, source ID, channel labels, sampling rate, and modality classification returned by ARL.
6. Repeat for EMG, then GSR, then Emotiv EEG.

Do not add participant-readiness rules until the real vendor stream naming/metadata has been observed.
