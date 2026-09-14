# Browser Media Reliability Patch

## Added
- Camera and microphone selectors for P1.
- Live microphone level meter.
- Explicit video/audio track validation before recording.
- VP8/Opus preferred for broader Windows/browser playback compatibility.
- Combined camera+audio WebM recording.
- Separate audio-only WebM recording from the selected microphone.
- Camera and microphone names recorded in metadata.
- Moderator-generated long beep before each speaking phase.
- P1 beep mixed into the recorded audio stream when P1 is active.

## Output files
- `P001_<session>_camera_audio_partXX.webm`
- `P001_<session>_audio_only_partXX.webm`
- matching metadata JSON files

## Validation completed in build environment
- Python backend compiles.
- Participant JavaScript syntax passes `node --check`.
- Moderator JavaScript syntax passes `node --check`.

Live camera/microphone playback must be validated on the Windows acquisition computer.
