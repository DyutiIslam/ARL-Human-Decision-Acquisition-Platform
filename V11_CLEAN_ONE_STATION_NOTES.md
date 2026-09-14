# ARL V11 Clean One-Station Hardware Integration Baseline

Purpose: restore reliable V8/V9-style session/game reset behavior while keeping the V10.2 readable XDF converter and relaxed one-station workflow.

## What changed
- Version label updated to V11 clean one-station baseline.
- New Session now clears active database rows for the reused session ID before starting a fresh run.
- Timer status now uses the latest SESSION_START / game-start marker, not old markers from earlier reused S001 tests.
- Fixed the manual LSL test marker endpoint to use the active state correctly.
- Moderator setup defaults to 1 participant and ECG-first one-station testing.
- Full production checklist items are shown as later/warnings instead of distracting hard failures.

## One-station validation order
1. Start server.
2. Open moderator, observer, and P1 browser.
3. Click Start New Session / Clear Active State.
4. Initialize LSL Marker Stream.
5. Open LabRecorder and verify SpyGameMarkers.
6. Send Test LSL Marker.
7. Run a short Spy Game flow with SpyGameMarkers only.
8. Start SensorChrono Shimmer bridge and confirm LabRecorder sees:
   - ShimmerECG
   - ShimmerMarkers
   - ShimmerDiagnostics_ECG
9. Record XDF in LabRecorder.
10. Run readable XDF converter GUI.

## Not changed
- No new Spy Game task features.
- No direct dependency on Consensys or EmotivPRO.
- Emotiv integration remains paused until LSL/Cortex license access is confirmed.
