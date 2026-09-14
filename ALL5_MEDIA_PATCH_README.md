# ARL V12.2 All-5 Participant Media Patch

This build enables browser camera + microphone recording for P1-P5 and saves uploaded media inside the existing ARL data tree.

Expected layout:

```text
data/sessions/S001/participants/P01/media/
data/sessions/S001/participants/P02/media/
...
data/sessions/S001/participants/P05/media/
```

Each participant creates:
- `P0X_S001_camera_audio_part01.webm`
- `P0X_S001_audio_only_part01.webm`
- JSON metadata files for both recordings

Important: browser camera/microphone permissions must be granted on each participant workstation. For remote participant laptops, use a browser context that permits `getUserMedia()` (typically HTTPS or localhost).
