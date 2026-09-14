# ARL V11.1 Browser Media + Speech Boundary Beep

## Added
- P1 browser camera and microphone setup using `getUserMedia`.
- P1 live media preview.
- Automatic combined camera/audio WebM recording when the session enters `SESSION_START`.
- Automatic stop and upload when the session enters `SESSION_END`.
- Session media storage under `data/sessions/<session>/participants/P001/media/`.
- Per-segment JSON metadata with UTC start/end/receive times and file size.
- Media lifecycle markers in `SpyGameMarkers`:
  - `P001_MEDIA_READY`
  - `P001_MEDIA_RECORDING_STARTED`
  - `P001_MEDIA_RECORDING_STOPPED`
  - `P001_MEDIA_UPLOAD_COMPLETED`
  - `P001_MEDIA_ERROR`
- Moderator browser-media status panel.
- P2-P5 simulated camera/microphone status for single-computer browser-tab testing.
- Long 1.2 kHz speech-boundary tone (~0.85 s) on the active participant station before each speaking phase.
- Explicit `Gx_Ry_SPEECH_BOUNDARY_BEEP` LSL markers at speaker starts and at the final speaker-to-next-phase boundary.

## Current validation scope
- P1 real camera + microphone on localhost.
- P2-P5 simulated media status.
- Five browser tabs may still be used for the Spy Game workflow.
- Media problems do not block experiment control.

## Important deployment note
Browser camera/microphone access works on `localhost`. Access from separate participant laptops over plain `http://<IP>:8000` may be blocked by browser secure-context rules. Multi-laptop deployment should use HTTPS or an approved browser policy before production data collection.

## Operator sequence
1. Open P1.
2. Click **Enable Sound** and test the long beep.
3. Click **Set Up P1 Camera + Mic** and grant permission.
4. Verify P1 shows `ready` in the moderator media panel.
5. Start the session; P1 should change to `recording`.
6. Complete/end the session and keep P1 open until it shows `Saved segment`.
7. Verify the WebM and metadata JSON in the session media folder.
