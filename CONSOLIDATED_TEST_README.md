# ARL V12 Consolidated — P1 Multimodal Test Build

This package consolidates the uploaded ARL base repository with the uploaded V12 multimodal LSL monitor patch while retaining the browser-media-enabled `static/participant.html` from the base repository.

## Intended validation scope

- P1 browser task
- P1 camera + microphone browser recording
- separate P1 audio-only recording
- SpyGameMarkers LSL outlet
- Shimmer ECG / EMG / GSR streamed by Consensys Pro to LSL
- LabRecorder XDF recording
- V12 read-only LSL acquisition monitor

## Start

Run `Run_ARL_V12_Consolidated.bat`.

Then open:

- P1: `http://127.0.0.1:8000/p1`
- Moderator: `http://127.0.0.1:8000/moderator`
- LSL acquisition monitor JSON: `http://127.0.0.1:8000/api/status/acquisition`

On the P1 welcome page you should see:

- Enable Sound
- Test Long Beep
- Set Up P1 Camera + Mic

## Media behavior

P1 browser media uses `getUserMedia()` and `MediaRecorder`.

When P1 media is prepared and the session enters `SESSION_START`, recording starts. At `SESSION_END`, recording stops and uploads to:

`data/sessions/<SESSION_ID>/participants/P001/media/`

Expected outputs include:

- `P001_<SESSION>_camera_audio_part01.webm`
- `P001_<SESSION>_audio_only_part01.webm`
- matching metadata JSON files

Media lifecycle events are also sent to the ARL event/marker path, including READY, RECORDING_STARTED, RECORDING_STOPPED, UPLOAD_COMPLETED, and ERROR events.

## Shimmer / LabRecorder

Consensys Pro remains the Shimmer streaming application. Do not use Consensys RECORD for this integration test. Enable Consensys LSL and stream the three P1 devices. LabRecorder remains the master XDF recorder.

Expected visible LSL streams for the current P1 test are:

- `Shimmer_6231` — ECG
- `Shimmer_0A67` — EMG
- `Shimmer_BA1B` — GSR
- `SpyGameMarkers` — ARL markers

Check `/api/status/acquisition` before recording to confirm streams are visible to ARL.

## Important

Browser camera/microphone access is most reliable for this one-station validation through `127.0.0.1` / localhost. Keep the participant page open after session end until media upload has completed.
