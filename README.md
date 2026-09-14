# ARL V13.2 Remote Media Fix

For multi-laptop operation, start the moderator with `Run_ARL_V13_2.bat` and open each remote participant only with the matching file in `Participant_Launchers/`. See `V13_2_REMOTE_MEDIA_FIX_README.md`.

# ARL Acquisition Interface - v8 Phase 1 LSL Marker Build

This build preserves the tested v7 acquisition workflow and adds Phase 1 LSL marker-stream testing tools.

## Run

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open the moderator page:

```text
http://127.0.0.1:8000/
```

Participant pages:

```text
http://127.0.0.1:8000/p1
http://127.0.0.1:8000/p2
http://127.0.0.1:8000/p3
http://127.0.0.1:8000/p4
http://127.0.0.1:8000/p5
```

Observer page:

```text
http://127.0.0.1:8000/observer
```

## Phase 1 LSL Test Procedure

1. Start the ARL interface.
2. Open the moderator page.
3. In **Recording Readiness and QC**, click **Initialize LSL Marker Stream**.
4. Open **LabRecorder**.
5. Verify that the stream **SpyGameMarkers** appears.
6. Select the stream in LabRecorder.
7. Click **Send Test LSL Marker** in the moderator panel.
8. Confirm `LSL_TEST_MARKER` appears in the moderator marker inspector and in `events.csv`.
9. Start a short LabRecorder recording and stop it.
10. Open the XDF and verify that the marker stream is present.

## LSL Marker Stream

- Stream name: `SpyGameMarkers`
- Stream type: `Markers`
- Source ID: `arl_spygame_control_pc`
- Channel count: 1
- Format: JSON string

Each marker sample contains a JSON payload with fields such as:

```json
{
  "marker": "G1_R1_SPEAKER_P1",
  "lsl_time": 123456.789,
  "session_id": "S001",
  "game_number": 1,
  "round_number": 1,
  "phase": "SPEAKER_P1",
  "player_id": null,
  "value": null,
  "server_time_utc": "...",
  "server_time_local": "..."
}
```

## Notes

- LabRecorder recording status cannot be controlled directly from this web app.
- The moderator must still manually verify that LabRecorder is recording and that the XDF has been saved.
- If the marker stream does not appear in LabRecorder, click **Initialize LSL Marker Stream** first.
- If `pylsl` or `liblsl` is missing, the UI will show an LSL error but the behavioral interface will still run.

## V11.1 browser media test
See `V11_1_BROWSER_MEDIA_NOTES.md` for P1 camera/microphone recording, simulated P2-P5 media status, and long speech-boundary beep validation.
