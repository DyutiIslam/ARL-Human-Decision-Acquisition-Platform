# ARL V13.2 — Remote Participant Camera/Microphone Fix

## Why V13.2 exists
V13.1 proved that the ARL application, camera, microphone, recording UI, participant heartbeat, and HTTPS worked locally on the moderator laptop. Remote workstations could reach TCP port 8000, but the self-signed HTTPS connection stalled during Windows Schannel TLS renegotiation before FastAPI received the request.

V13.2 removes that unstable TLS layer for the lab LAN. The moderator server returns to the known-working V13 HTTP transport. Remote participant browsers are launched in a **dedicated Microsoft Edge profile** with Chromium's secure-origin override for the one ARL origin. This makes `window.isSecureContext` true for `http://192.168.2.38:8000` and exposes `navigator.mediaDevices.getUserMedia()` without relying on certificate/TLS behavior.

## Moderator laptop (.38)
1. Extract the package.
2. Run `Run_ARL_V13_2.bat`.
3. Keep the server terminal open.
4. Moderator page: `http://127.0.0.1:8000/`.
5. If Windows Firewall asks, allow Python on the lab network. Existing port-8000 rules from earlier testing can remain.

## Participant 1 laptop (.37)
1. Copy the `Participant_Launchers` folder to the laptop.
2. Close the old ARL browser tabs.
3. Double-click `Launch_P1_Edge.bat`.
4. A separate Edge window/profile opens at `http://192.168.2.38:8000/p1`.
5. Click **Set Up P1 Camera + Mic** and allow camera/microphone access.
6. In the media panel, confirm:
   - `Secure context: YES`
   - `Media API: READY`
   - camera preview is visible
   - microphone meter responds

Use the matching launcher for P2–P5.

## Important
Do **not** manually type the participant URL into a normal Edge/Chrome window. A normal LAN HTTP page will show `Secure context: NO` and the camera/microphone API will be unavailable. Always open remote participant workstations with the supplied launcher.

## If the moderator IP changes
Open each `Launch_P*_Edge.bat` in Notepad and change:

`set "SERVER_IP=192.168.2.38"`

to the moderator's current IPv4 address.

## V13 functionality retained
V13.2 is based on the V13 master-sync/organized-data build and retains the experiment flow, 5 participants, 5 games × 4 rounds, timers, voting/confidence/reasoning responses, browser A/V recording, WebM uploads, separate audio, media-sync anchors, LSL markers, LabRecorder/XDF workflow, organized session output, and XDF converter.

## Diagnostic endpoint
The server includes `/api/diagnostics/network`, which reports the app version and the client address seen by FastAPI.
