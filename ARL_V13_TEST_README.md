# ARL V13 — Master Sync + Organized Data Test Build

This build extends the validated V12.2 all-five-participant media build without changing the working WebM storage design.

## What changed

1. **Automatic media synchronization anchors**
   - Each participant records a `Pxx_MEDIA_SYNC` anchor immediately after recording starts, every 5 seconds, and immediately before recording stops.
   - The browser sends media elapsed time; the server stamps the event on the same LSL clock used by `SpyGameMarkers`.
   - Every anchor is therefore present in the master XDF through the `SpyGameMarkers` stream.
   - A participant sidecar is also written automatically:
     `data/sessions/S001/participants/P01/media/P01_S001_media_sync.csv`.

2. **Master-XDF session structure**
   - Every ARL session creates a `master/` directory.
   - Save the LabRecorder recording directly as:
     `data/sessions/S001/master/S001_MASTER.xdf`.
   - LabRecorder should record all visible physiological LSL streams plus `SpyGameMarkers` into this single file.

3. **Important audio/video policy**
   - Raw camera/video and microphone media are **not** written as video frames or PCM audio into XDF.
   - Raw media remain the validated `.webm` files under each participant `media/` folder.
   - The XDF contains the synchronization anchors required to map every WebM timestamp onto the LSL/physiology timeline automatically during post-processing.
   - This avoids a very large/fragile XDF while preserving a single synchronized master clock.

4. **Organized XDF → CSV converter**
   - Use `Run_XDF_Converter.bat` and select the one master XDF.
   - The converter now creates:
     - `markers/S001_SpyGameMarkers.csv` — marker JSON expanded into readable columns.
     - `markers/S001_Event_Timeline.csv` — simplified human-readable timeline.
     - `participants/P01/P01_ECG.csv`, `P01_EMG.csv`, `P01_GSR.csv`, `P01_EEG.csv`, etc. when the stream can be mapped from the ARL device map.
     - corresponding P02–P05 modality CSVs.
     - `unmapped_streams/` for streams that cannot safely be assigned rather than guessing.
     - `overview/S001_Aligned_Overview_10Hz.csv` — a common 10 Hz QC/visualization table containing all numeric mapped streams plus current game/round/phase/speaker/marker context.
     - `stream_summary.csv` and `stream_report.json`.
   - Every exported physiological CSV retains `lsl_timestamp` and adds `experiment_time_s`, where `SESSION_START = 0`.

5. **Readable marker format**
   Marker data that previously appeared as one JSON string in `ch_01` is expanded into columns such as:
   `experiment_time_s, lsl_timestamp, server_time_local, session_id, game_number, round_number, phase, active_speaker, player_id, marker, value`.
   Media-sync nested fields are also expanded where available.

## Before the next test

1. Start ARL V13.
2. Configure participant/device mapping in Moderator Setup and save it.
3. Set up camera + microphone on each participant station.
4. Start Consensys/Emotiv LSL streams as applicable.
5. Open LabRecorder and select **all physiological streams + SpyGameMarkers**.
6. Save LabRecorder output to `data/sessions/S001/master/S001_MASTER.xdf`.
7. Start LabRecorder before starting the ARL session.
8. Run the experiment.
9. End the ARL session normally and wait until media says saved.
10. Stop LabRecorder last.
11. Run `Run_XDF_Converter.bat` on `S001_MASTER.xdf`.

## Pass criteria for the next test

- One `S001_MASTER.xdf` contains every selected LSL physiology stream plus `SpyGameMarkers`.
- P01–P05 WebM files are physically present in participant media folders.
- Each active participant has a `Pxx_S001_media_sync.csv` sidecar.
- Converted `S001_SpyGameMarkers.csv` has separate readable columns rather than a single JSON column.
- `experiment_time_s` is present in converted physiological files.
- Participant/modality streams with valid device mapping land in the correct participant folder.
- `S001_Aligned_Overview_10Hz.csv` is generated for whole-session QC.

Do not delete the original XDF or WebM files after conversion. They are the authoritative raw/master data.
