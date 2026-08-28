from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import csv
import io
import json
import random
import socket
import threading
import webbrowser

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .db import init_db, get_session, DATA_DIR, engine
from .models import AcquisitionState, Participant, WordAssignment, EventLog, BehavioralResponse, SessionMetadata, EEGStreamSnapshot, SessionConfig
from .lsl import push_marker, lsl_available, lsl_status, ensure_outlet
from .eeg_lsl_monitor import scan_eeg_streams

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
WORD_PAIRS_FILE = BASE_DIR / "word_pairs.csv"
APP_VERSION = "v1.6-v11-browser-media-and-speech-beep"
MAX_GAMES = 5
MAX_ROUNDS = 4
PLAYERS = range(1, 6)

app = FastAPI(title="ARL Spy Game Acquisition Interface")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

MEDIA_STATUS: Dict[str, Dict[int, Dict[str, Any]]] = {}
MEDIA_LOCK = threading.Lock()

def safe_session_id(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})
    return cleaned or "S001"

def media_status_for(session_id: str) -> Dict[int, Dict[str, Any]]:
    sid = safe_session_id(session_id)
    with MEDIA_LOCK:
        current = MEDIA_STATUS.setdefault(sid, {})
        for player_id in PLAYERS:
            if player_id not in current:
                current[player_id] = {
                    "mode": "real" if player_id == 1 else "simulated",
                    "status": "not_ready" if player_id == 1 else "simulated",
                    "camera": player_id == 1,
                    "microphone": player_id == 1,
                    "segment": 0,
                    "updated_at_utc": utc_now().isoformat(),
                    "last_file": "",
                    "note": "P1 uses browser camera/microphone; P2-P5 are simulated during one-computer testing." if player_id > 1 else "",
                }
        return {k: dict(v) for k, v in current.items()}

def update_media_status(session_id: str, player_id: int, **changes: Any) -> Dict[str, Any]:
    sid = safe_session_id(session_id)
    media_status_for(sid)
    with MEDIA_LOCK:
        rec = MEDIA_STATUS[sid][player_id]
        rec.update(changes)
        rec["updated_at_utc"] = utc_now().isoformat()
        return dict(rec)


PHASES = {
    "WAITING", "SESSION_START", "GAME_READY", "WORD_PHASE",
    "SPEAKER_P1", "SPEAKER_P2", "SPEAKER_P3", "SPEAKER_P4", "SPEAKER_P5",
    "VOTE_PHASE", "CONFIDENCE_PHASE", "REASONING_PHASE",
    "ROUND_END", "GAME_END", "SESSION_END",
}
PHASE_DURATIONS_SEC = {
    "WORD_PHASE": 5,
    "SPEAKER_P1": 10, "SPEAKER_P2": 10, "SPEAKER_P3": 10, "SPEAKER_P4": 10, "SPEAKER_P5": 10,
    "VOTE_PHASE": 15,
    "CONFIDENCE_PHASE": 10,
    "REASONING_PHASE": 15,
}
PHASE_LABELS = {
    "WAITING": "Waiting / Pre-flight",
    "SESSION_START": "Session Started",
    "GAME_READY": "Game Ready",
    "WORD_PHASE": "Word Review",
    "SPEAKER_P1": "Participant 1 Speaking", "SPEAKER_P2": "Participant 2 Speaking", "SPEAKER_P3": "Participant 3 Speaking", "SPEAKER_P4": "Participant 4 Speaking", "SPEAKER_P5": "Participant 5 Speaking",
    "VOTE_PHASE": "Decision",
    "CONFIDENCE_PHASE": "Confidence Rating",
    "REASONING_PHASE": "Reasoning",
    "ROUND_END": "Round Complete",
    "GAME_END": "Game Complete",
    "SESSION_END": "Session Complete",
}


def utc_now() -> datetime:
    return datetime.utcnow()

def local_time_iso(dt: Optional[datetime] = None) -> str:
    """Return local machine time with timezone offset for human-readable lab logs."""
    from datetime import timezone
    base = dt or utc_now()
    return base.replace(tzinfo=timezone.utc).astimezone().isoformat()

def find_phase_start_event(db: Session, session_id: str, game_number: int, round_number: int, phase: str) -> Optional[EventLog]:
    marker = f"G{game_number}_R{round_number}_{phase}"
    rows = db.exec(select(EventLog).where(EventLog.session_id == session_id, EventLog.game_number == game_number, EventLog.round_number == round_number, EventLog.marker == marker).order_by(EventLog.id)).all()
    return rows[-1] if rows else None

def reaction_time_sec(start: Optional[EventLog], submit_lsl: Optional[float], submit_utc: datetime) -> Optional[float]:
    if start and start.lsl_time is not None and submit_lsl is not None:
        return round(max(0.0, float(submit_lsl) - float(start.lsl_time)), 4)
    if start and start.server_time_utc:
        return round(max(0.0, (submit_utc - start.server_time_utc).total_seconds()), 4)
    return None

class SetPhase(BaseModel):
    session_id: str = "S001"
    phase: str
    game_number: Optional[int] = Field(default=None, ge=1, le=MAX_GAMES)
    round_number: Optional[int] = Field(default=None, ge=1, le=MAX_ROUNDS)
    value: Optional[str] = None

class ForceEndPayload(BaseModel):
    session_id: str = "S001"
    reason: str = Field(default="moderator decision")
    note: str = ""

class NewSessionPayload(BaseModel):
    session_id: str = "S001"

class StartGame(BaseModel):
    session_id: str = "S001"
    game_number: int = Field(ge=1, le=MAX_GAMES)
    spy_player: Optional[int] = Field(default=None, ge=1, le=5)

class SubmitVote(BaseModel):
    session_id: str = "S001"
    game_number: int = Field(ge=1, le=MAX_GAMES)
    round_number: int = Field(ge=1, le=MAX_ROUNDS)
    player_id: int = Field(ge=1, le=5)
    vote_target: int = Field(ge=1, le=5)

class SubmitConfidence(BaseModel):
    session_id: str = "S001"
    game_number: int = Field(ge=1, le=MAX_GAMES)
    round_number: int = Field(ge=1, le=MAX_ROUNDS)
    player_id: int = Field(ge=1, le=5)
    confidence: int = Field(ge=1, le=5)

class SubmitReasoning(BaseModel):
    session_id: str = "S001"
    game_number: int = Field(ge=1, le=MAX_GAMES)
    round_number: int = Field(ge=1, le=MAX_ROUNDS)
    player_id: int = Field(ge=1, le=5)
    reasons: List[str] = []

class HeartbeatPayload(BaseModel):
    session_id: str = "S001"
    player_id: int = Field(ge=1, le=5)
    current_phase_seen: str = ""

class MetadataPayload(BaseModel):
    session_id: str = "S001"
    group_id: str = ""
    operator: str = ""
    experiment_version: str = APP_VERSION
    word_set_version: str = "word_pairs.csv"
    participant_p1: str = ""
    participant_p2: str = ""
    participant_p3: str = ""
    participant_p4: str = ""
    participant_p5: str = ""
    eeg_notes: str = ""
    ecg_notes: str = ""
    gsr_notes: str = ""
    emg_notes: str = ""
    audio_notes: str = ""
    video_notes: str = ""
    operator_notes: str = ""
    qc_labrecorder: bool = False
    qc_eeg: bool = False
    qc_ecg: bool = False
    qc_gsr: bool = False
    qc_emg: bool = False
    qc_audio: bool = False
    qc_video: bool = False
    session_notes: str = ""

class MediaEventPayload(BaseModel):
    session_id: str = "S001"
    player_id: int = Field(ge=1, le=5)
    event: str = Field(pattern="^(ready|recording_started|recording_stopped|upload_completed|error|permission_denied)$")
    segment: int = Field(default=0, ge=0)
    note: str = ""

class HardwareEventPayload(BaseModel):
    session_id: str = "S001"
    device: str
    player_id: Optional[int] = Field(default=None, ge=1, le=5)
    status: str = Field(pattern="^(connected|disconnected|issue|resolved)$")
    note: str = ""

class SessionConfigPayload(BaseModel):
    session_id: str = "S001"
    experiment_name: str = "spy_game"
    participant_count: int = Field(default=5, ge=1, le=5)
    enabled_modalities: List[str] = Field(default_factory=lambda: ["EEG"])
    device_map: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    output_root: str = ""
    setup_locked: bool = False

class LockSetupPayload(BaseModel):
    session_id: str = "S001"
    lock: bool = True


@app.on_event("startup")
def startup():
    init_db()
    # Always start the active control panel from a clean WAITING state.
    # Previous session data remain saved in data/sessions/ and the database.
    # This prevents the moderator page from reopening stuck in the last completed game/session.
    reset_active_state_on_startup()
    ip = get_local_ip()
    print("\n" + "=" * 72)
    print(f"ARL Acquisition Interface {APP_VERSION} is running")
    print(f"Moderator:     http://127.0.0.1:8000/")
    print(f"Observer:      http://127.0.0.1:8000/observer")
    print(f"Network host:  http://{ip}:8000/")
    print("Participant workstations:")
    for i in PLAYERS:
        print(f"  P{i}: http://{ip}:8000/p{i}")
    print("=" * 72 + "\n")
    import os
    if not bool(int(os.environ.get("ARL_NO_BROWSER", "0"))):
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:8000/")).start()

def get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"

def reset_active_state_on_startup() -> None:
    """Reset only the active experiment controller state.

    This does not delete prior events, responses, assignments, metadata, or saved
    session folders. It only prevents the UI from reopening in a previous
    completed/stale phase after restarting the server.
    """
    with Session(engine) as db:
        state = db.exec(select(AcquisitionState).where(AcquisitionState.id == 1)).first()
        if not state:
            state = AcquisitionState(id=1, session_id="S001", phase="WAITING")
            db.add(state)
        else:
            state.session_id = "S001"
            state.game_number = 1
            state.round_number = 1
            state.phase = "WAITING"
            state.active_speaker = None
            state.started_at = datetime.utcnow()
            state.updated_at = datetime.utcnow()
            db.add(state)
        db.commit()

def load_word_pairs() -> list[tuple[str, str]]:
    if not WORD_PAIRS_FILE.exists():
        WORD_PAIRS_FILE.write_text("common_word,spy_word\nPLANET,MOON\nOCEAN,LAKE\nCHAIR,SOFA\nSHIRT,JACKET\nBOOK,NOVEL\n", encoding="utf-8")
    pairs = []
    with WORD_PAIRS_FILE.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            common = (row.get("common_word") or "").strip().upper()
            spy = (row.get("spy_word") or "").strip().upper()
            if common and spy:
                pairs.append((common, spy))
    return pairs or [("PLANET", "MOON")]

def get_or_create_state(db: Session, session_id: str = "S001") -> AcquisitionState:
    state = db.exec(select(AcquisitionState).where(AcquisitionState.id == 1)).first()
    if not state:
        state = AcquisitionState(id=1, session_id=session_id, phase="WAITING")
        db.add(state)
        db.commit()
        db.refresh(state)
    return state

def assignments_for_game(db: Session, session_id: str, game_number: int) -> list[WordAssignment]:
    return db.exec(select(WordAssignment).where(WordAssignment.session_id == session_id, WordAssignment.game_number == game_number)).all()

def game_has_assignment(db: Session, session_id: str, game_number: int) -> bool:
    rows = assignments_for_game(db, session_id, game_number)
    return len(rows) == 5 and len({r.player_id for r in rows}) == 5

def response_rows(db: Session, session_id: str, game_number: int, round_number: int) -> list[BehavioralResponse]:
    return db.exec(select(BehavioralResponse).where(BehavioralResponse.session_id == session_id, BehavioralResponse.game_number == game_number, BehavioralResponse.round_number == round_number)).all()

def response_status_dict(db: Session, session_id: str, game_number: int, round_number: int) -> dict[str, dict[str, bool]]:
    rows = response_rows(db, session_id, game_number, round_number)
    status = {str(i): {"vote": False, "confidence": False, "reasoning": False} for i in PLAYERS}
    for r in rows:
        status[str(r.player_id)] = {"vote": r.vote_target is not None, "confidence": r.confidence is not None, "reasoning": r.reasoning_submitted_at is not None}
    return status

def all_submitted(db: Session, session_id: str, game_number: int, round_number: int, kind: str) -> bool:
    st = response_status_dict(db, session_id, game_number, round_number)
    return all(st[str(i)][kind] for i in PLAYERS)

def participants_connected(db: Session, session_id: str, max_age_sec: float = 5.0) -> bool:
    rows = db.exec(select(Participant).where(Participant.session_id == session_id)).all()
    by = {r.player_id: r for r in rows}
    now = datetime.utcnow()
    for i in PLAYERS:
        r = by.get(i)
        if not r or not r.last_seen_utc:
            return False
        if (now - r.last_seen_utc).total_seconds() > max_age_sec:
            return False
    return True

MODALITIES = ["EEG", "ECG", "GSR", "EMG", "Audio", "Video", "Microphone", "Camera"]

def _norm_modality(name: str) -> str:
    n = (name or "").strip()
    aliases = {"mic": "Microphone", "microphone": "Microphone", "audio": "Audio", "cam": "Camera", "camera": "Camera", "video": "Video", "eeg": "EEG", "ecg": "ECG", "gsr": "GSR", "emg": "EMG"}
    return aliases.get(n.lower(), n.upper() if n.lower() in {"eeg", "ecg", "gsr", "emg"} else n)

def get_or_create_config(db: Session, session_id: str = "S001") -> SessionConfig:
    rec = db.exec(select(SessionConfig).where(SessionConfig.session_id == session_id)).first()
    if not rec:
        default_map = {f"P{i:02d}": {"EEG": "", "ECG": "", "GSR": "", "EMG": "", "Audio": "", "Video": ""} for i in PLAYERS}
        rec = SessionConfig(session_id=session_id, experiment_name="spy_game", participant_count=5, enabled_modalities_json=json.dumps(["EEG"]), device_map_json=json.dumps(default_map))
        db.add(rec); db.commit(); db.refresh(rec)
    return rec

def config_dict(db: Session, session_id: str = "S001") -> Dict[str, Any]:
    rec = get_or_create_config(db, session_id)
    try:
        enabled = json.loads(rec.enabled_modalities_json or "[]")
    except Exception:
        enabled = []
    try:
        device_map = json.loads(rec.device_map_json or "{}")
    except Exception:
        device_map = {}
    return {
        "session_id": rec.session_id,
        "experiment_name": rec.experiment_name,
        "participant_count": rec.participant_count,
        "enabled_modalities": enabled,
        "device_map": device_map,
        "output_root": rec.output_root,
        "setup_locked": rec.setup_locked,
        "locked_at_utc": rec.locked_at_utc.isoformat() if rec.locked_at_utc else None,
        "created_at": rec.created_at.isoformat(),
        "updated_at": rec.updated_at.isoformat(),
    }

def config_has_complete_mapping(cfg: Dict[str, Any]) -> bool:
    enabled = cfg.get("enabled_modalities", [])
    device_map = cfg.get("device_map", {})
    for i in range(1, int(cfg.get("participant_count", 5)) + 1):
        pid = f"P{i:02d}"
        for m in enabled:
            # Audio/video may be room-level in early pilots, so mapping is recommended but not blocking.
            if m in {"Audio", "Video", "Camera", "Microphone"}:
                continue
            if not str(device_map.get(pid, {}).get(m, "")).strip():
                return False
    return True

def enabled_qc_ready(qc: Dict[str, Any], enabled: List[str]) -> bool:
    aliases = {"Microphone": "audio", "Camera": "video"}
    for m in enabled:
        key = aliases.get(m, m)
        if not bool(qc.get(key)):
            return False
    return True

def get_next_action(db: Session, state: AcquisitionState) -> Dict[str, Any]:
    sid, g, r, phase = state.session_id, state.game_number, state.round_number, state.phase
    if phase == "WAITING":
        return {"label": "Start Session", "kind": "phase", "phase": "SESSION_START"}
    if phase == "SESSION_START":
        if not game_has_assignment(db, sid, g):
            return {"label": "Create Current Game", "kind": "create_game"}
        return {"label": "Start Word Phase", "kind": "phase", "phase": "WORD_PHASE"}
    if phase == "GAME_READY":
        return {"label": "Start Word Phase", "kind": "phase", "phase": "WORD_PHASE"}
    if phase == "WORD_PHASE":
        return {"label": "Start Speaker P1", "kind": "phase", "phase": "SPEAKER_P1"}
    if phase.startswith("SPEAKER_P"):
        n = int(phase.split("P")[-1])
        if n < 5:
            return {"label": f"Start Speaker P{n+1}", "kind": "phase", "phase": f"SPEAKER_P{n+1}"}
        return {"label": "Start Vote", "kind": "phase", "phase": "VOTE_PHASE"}
    if phase == "VOTE_PHASE":
        ready = all_submitted(db, sid, g, r, "vote")
        return {"label": "Start Confidence" if ready else "Waiting for all votes", "kind": "phase", "phase": "CONFIDENCE_PHASE", "enabled": ready}
    if phase == "CONFIDENCE_PHASE":
        ready = all_submitted(db, sid, g, r, "confidence")
        return {"label": "Start Reasoning" if ready else "Waiting for all confidence ratings", "kind": "phase", "phase": "REASONING_PHASE", "enabled": ready}
    if phase == "REASONING_PHASE":
        ready = all_submitted(db, sid, g, r, "reasoning")
        return {"label": "End Round" if ready else "Waiting for all reasoning responses", "kind": "phase", "phase": "ROUND_END", "enabled": ready}
    if phase == "ROUND_END":
        if r < MAX_ROUNDS:
            return {"label": "Next Round: Word Phase", "kind": "phase", "phase": "WORD_PHASE", "round_number": r + 1}
        return {"label": "End Game", "kind": "phase", "phase": "GAME_END"}
    if phase == "GAME_END":
        if g < MAX_GAMES:
            return {"label": "Start Next Game", "kind": "next_game"}
        return {"label": "End Session", "kind": "phase", "phase": "SESSION_END"}
    return {"label": "Session Complete", "kind": "none", "phase": "SESSION_END", "enabled": False}

def marker_for_phase(state: AcquisitionState, phase: str) -> str:
    if phase in {"SESSION_START", "SESSION_END"}:
        return phase
    if phase == "GAME_READY":
        return f"G{state.game_number}_GAME_READY"
    return f"G{state.game_number}_R{state.round_number}_{phase}"

def log_event(db: Session, state: AcquisitionState, marker: str, player_id: Optional[int] = None, value: Optional[str] = None) -> EventLog:
    now_utc = utc_now()
    now_local = local_time_iso(now_utc)
    payload = {"session_id": state.session_id, "game_number": state.game_number, "round_number": state.round_number, "phase": state.phase, "active_speaker": state.active_speaker, "player_id": player_id, "value": value, "server_time_utc": now_utc.isoformat(), "server_time_local": now_local}
    lsl_time = push_marker(marker, payload)
    rec = EventLog(session_id=state.session_id, game_number=state.game_number, round_number=state.round_number, phase=state.phase, marker=marker, active_speaker=state.active_speaker, player_id=player_id, value=value, server_time_utc=now_utc, server_time_local=now_local, lsl_time=lsl_time)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

def last_connection_event(db: Session, session_id: str, player_id: int) -> Optional[EventLog]:
    markers = [f"P{player_id}_CONNECTED", f"P{player_id}_RECONNECTED", f"P{player_id}_DISCONNECTED"]
    return db.exec(
        select(EventLog)
        .where(EventLog.session_id == session_id, EventLog.player_id == player_id, EventLog.marker.in_(markers))
        .order_by(EventLog.id.desc())
    ).first()

def log_connection_event_if_needed(db: Session, state: AcquisitionState, player_id: int, connected: bool, note: str = "") -> None:
    """Log participant browser connection changes without spamming events.csv.

    Heartbeats are frequent, so CONNECTED/RECONNECTED is only logged when a station
    first appears or returns after a DISCONNECTED event. DISCONNECTED is logged when
    the moderator/status endpoint notices that a station heartbeat has timed out.
    """
    last = last_connection_event(db, state.session_id, player_id)
    if connected:
        if last is None:
            log_event(db, state, f"P{player_id}_CONNECTED", player_id=player_id, value=note or "heartbeat")
        elif last.marker == f"P{player_id}_DISCONNECTED":
            log_event(db, state, f"P{player_id}_RECONNECTED", player_id=player_id, value=note or "heartbeat")
    else:
        if last is None or last.marker != f"P{player_id}_DISCONNECTED":
            log_event(db, state, f"P{player_id}_DISCONNECTED", player_id=player_id, value=note or "heartbeat_timeout")

def upsert_response(db: Session, session_id: str, game_number: int, round_number: int, player_id: int) -> BehavioralResponse:
    rec = db.exec(select(BehavioralResponse).where(BehavioralResponse.session_id == session_id, BehavioralResponse.game_number == game_number, BehavioralResponse.round_number == round_number, BehavioralResponse.player_id == player_id)).first()
    if not rec:
        rec = BehavioralResponse(session_id=session_id, game_number=game_number, round_number=round_number, player_id=player_id)
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return rec

def validate_phase_transition(db: Session, state: AcquisitionState, target_phase: str, target_round: Optional[int]) -> None:
    if target_phase == "SESSION_END":
        return
    next_action = get_next_action(db, state)
    if not next_action.get("enabled", True):
        raise HTTPException(400, detail=next_action.get("label", "Current step is incomplete."))
    if next_action.get("kind") != "phase" or next_action.get("phase") != target_phase:
        raise HTTPException(400, detail=f"Invalid transition from {state.phase} to {target_phase}. Recommended action is: {next_action.get('label')}.")
    if target_phase == "SESSION_START" and not participants_connected(db, state.session_id):
        raise HTTPException(400, detail="Cannot start session until P1-P5 participant screens are connected.")
    if target_phase == "WORD_PHASE" and not game_has_assignment(db, state.session_id, state.game_number):
        raise HTTPException(400, detail="Cannot start word phase. Create the current game assignment first.")
    if target_phase == "CONFIDENCE_PHASE" and not all_submitted(db, state.session_id, state.game_number, state.round_number, "vote"):
        raise HTTPException(400, detail="Cannot start confidence phase until all votes are submitted.")
    if target_phase == "REASONING_PHASE" and not all_submitted(db, state.session_id, state.game_number, state.round_number, "confidence"):
        raise HTTPException(400, detail="Cannot start reasoning phase until all confidence ratings are submitted.")
    if target_phase == "ROUND_END" and not all_submitted(db, state.session_id, state.game_number, state.round_number, "reasoning"):
        raise HTTPException(400, detail="Cannot end round until all reasoning responses are submitted.")
    if target_phase == "GAME_END" and state.round_number < MAX_ROUNDS:
        raise HTTPException(400, detail="Cannot end game before Round 4 is complete.")

def select_spy_player(db: Session, session_id: str, requested: Optional[int] = None) -> int:
    if requested:
        return requested
    previous_spies = []
    for a in db.exec(select(WordAssignment).where(WordAssignment.session_id == session_id)).all():
        if a.spy_player not in previous_spies:
            previous_spies.append(a.spy_player)
    available = [i for i in PLAYERS if i not in previous_spies]
    return random.choice(available or list(PLAYERS))

def create_game_assignment(db: Session, session_id: str, game_number: int, spy_player: Optional[int]) -> dict:
    old = assignments_for_game(db, session_id, game_number)
    for rec in old:
        db.delete(rec)
    pairs = load_word_pairs()
    used = {(a.common_word, a.spy_word) for a in db.exec(select(WordAssignment).where(WordAssignment.session_id == session_id)).all() if a.game_number != game_number}
    available = [pair for pair in pairs if pair not in used] or pairs
    common, spy_word = random.choice(available)
    spy = select_spy_player(db, session_id, spy_player)
    for player_id in PLAYERS:
        role = "spy" if player_id == spy else "civilian"
        db.add(WordAssignment(session_id=session_id, game_number=game_number, player_id=player_id, role=role, word=spy_word if role == "spy" else common, common_word=common, spy_word=spy_word, spy_player=spy))
    state = get_or_create_state(db, session_id)
    state.session_id = session_id
    state.game_number = game_number
    state.round_number = 1
    state.phase = "GAME_READY"
    state.active_speaker = None
    state.updated_at = datetime.utcnow()
    db.add(state)
    db.commit()
    db.refresh(state)
    log_event(db, state, f"G{game_number}_ASSIGNMENT_CREATED", value=f"spy=P{spy};common={common};spy_word={spy_word}")
    return {"ok": True, "game_number": game_number, "spy_player": spy, "common_word": common, "spy_word": spy_word, "state": state}

# CSV/export helpers

def csv_events(db: Session, session_id: Optional[str] = None) -> str:
    rows = db.exec(select(EventLog).order_by(EventLog.id)).all()
    if session_id:
        rows = [r for r in rows if r.session_id == session_id]
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["id", "session_id", "game_number", "round_number", "phase", "marker", "active_speaker", "player_id", "value", "server_time_utc", "server_time_local", "lsl_time"])
    for r in rows:
        w.writerow([r.id, r.session_id, r.game_number, r.round_number, r.phase, r.marker, r.active_speaker, r.player_id, r.value, r.server_time_utc.isoformat(), r.server_time_local, r.lsl_time])
    return buf.getvalue()

def csv_behavior(db: Session, session_id: Optional[str] = None, player_id: Optional[int] = None) -> str:
    rows = db.exec(select(BehavioralResponse).order_by(BehavioralResponse.id)).all()
    if session_id:
        rows = [r for r in rows if r.session_id == session_id]
    if player_id is not None:
        rows = [r for r in rows if r.player_id == player_id]
    assignments = db.exec(select(WordAssignment)).all()
    assignment_map = {(a.session_id, a.game_number, a.player_id): a for a in assignments}
    spy_map = {(a.session_id, a.game_number): a.spy_player for a in assignments}
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["id", "session_id", "game_number", "round_number", "player_id", "role", "vote_target", "correct_vote", "confidence", "reasons_text", "vote_submitted_at", "vote_submitted_local", "vote_lsl_time", "vote_rt_sec", "confidence_submitted_at", "confidence_submitted_local", "confidence_lsl_time", "confidence_rt_sec", "reasoning_submitted_at", "reasoning_submitted_local", "reasoning_lsl_time", "reasoning_rt_sec", "submitted_at"])
    for r in rows:
        a = assignment_map.get((r.session_id, r.game_number, r.player_id)); spy = spy_map.get((r.session_id, r.game_number))
        correct = "" if r.vote_target is None or spy is None else int(r.vote_target == spy)
        w.writerow([r.id, r.session_id, r.game_number, r.round_number, r.player_id, a.role if a else "", r.vote_target or "", correct, r.confidence or "", r.reasons_text, r.vote_submitted_at.isoformat() if r.vote_submitted_at else "", r.vote_submitted_local, r.vote_lsl_time if r.vote_lsl_time is not None else "", r.vote_rt_sec if r.vote_rt_sec is not None else "", r.confidence_submitted_at.isoformat() if r.confidence_submitted_at else "", r.confidence_submitted_local, r.confidence_lsl_time if r.confidence_lsl_time is not None else "", r.confidence_rt_sec if r.confidence_rt_sec is not None else "", r.reasoning_submitted_at.isoformat() if r.reasoning_submitted_at else "", r.reasoning_submitted_local, r.reasoning_lsl_time if r.reasoning_lsl_time is not None else "", r.reasoning_rt_sec if r.reasoning_rt_sec is not None else "", r.submitted_at.isoformat()])
    return buf.getvalue()

def csv_assignments(db: Session, session_id: Optional[str] = None) -> str:
    rows = db.exec(select(WordAssignment).order_by(WordAssignment.id)).all()
    if session_id:
        rows = [r for r in rows if r.session_id == session_id]
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["id", "session_id", "game_number", "player_id", "role", "word", "common_word", "spy_word", "spy_player"])
    for r in rows:
        w.writerow([r.id, r.session_id, r.game_number, r.player_id, r.role, r.word, r.common_word, r.spy_word, r.spy_player])
    return buf.getvalue()

def metadata_dict(db: Session, session_id: str) -> Dict[str, Any]:
    meta = db.exec(select(SessionMetadata).where(SessionMetadata.session_id == session_id)).first()
    if not meta:
        return {"session_id": session_id, "warning": "No metadata saved yet", "app_version": APP_VERSION, "session_config": config_dict(db, session_id)}
    return {"session_id": meta.session_id, "group_id": meta.group_id, "operator": meta.operator, "experiment_version": meta.experiment_version, "word_set_version": meta.word_set_version, "participant_codes": {"P1": meta.participant_p1, "P2": meta.participant_p2, "P3": meta.participant_p3, "P4": meta.participant_p4, "P5": meta.participant_p5}, "sensor_notes": {"EEG": meta.eeg_notes, "ECG": meta.ecg_notes, "GSR": meta.gsr_notes, "EMG": meta.emg_notes, "audio": meta.audio_notes, "video": meta.video_notes}, "operator_notes": meta.operator_notes, "session_notes": getattr(meta, "session_notes", ""), "qc_checklist": json.loads(getattr(meta, "qc_checklist_json", "{}") or "{}"), "created_at": meta.created_at.isoformat(), "updated_at": meta.updated_at.isoformat(), "app_version": APP_VERSION, "session_config": config_dict(db, session_id)}

def session_integrity_report(db: Session, session_id: str) -> Dict[str, Any]:
    issues = []
    missing_votes: list[str] = []
    missing_confidence: list[str] = []
    missing_reasoning: list[str] = []
    assigns = db.exec(select(WordAssignment).where(WordAssignment.session_id == session_id)).all()
    for g in range(1, MAX_GAMES + 1):
        game_assign = [a for a in assigns if a.game_number == g]
        if game_assign and len(game_assign) != 5:
            issues.append(f"Game {g} has incomplete word assignment ({len(game_assign)}/5).")
        for r in range(1, MAX_ROUNDS + 1):
            st = response_status_dict(db, session_id, g, r)
            if any(v["vote"] or v["confidence"] or v["reasoning"] for v in st.values()):
                for kind in ["vote", "confidence", "reasoning"]:
                    missing = [f"P{p}" for p in PLAYERS if not st[str(p)][kind]]
                    if missing:
                        issues.append(f"Game {g} Round {r} missing {kind}: {', '.join(missing)}")
                        if kind == "vote": missing_votes.extend([f"G{g}R{r}:{m}" for m in missing])
                        if kind == "confidence": missing_confidence.extend([f"G{g}R{r}:{m}" for m in missing])
                        if kind == "reasoning": missing_reasoning.extend([f"G{g}R{r}:{m}" for m in missing])
    events = db.exec(select(EventLog).where(EventLog.session_id == session_id).order_by(EventLog.id)).all()
    force_events = [e for e in events if e.marker in {"FORCE_GAME_END", "FORCE_SESSION_END"}]
    last_force = force_events[-1] if force_events else None
    return {
        "ok": not issues,
        "issues": issues,
        "force_ended": bool(force_events),
        "force_end_type": None if not last_force else ("session" if last_force.marker == "FORCE_SESSION_END" else "game"),
        "force_end_reason": None if not last_force else last_force.value,
        "force_end_timestamp": None if not last_force else last_force.server_time_utc.isoformat(),
        "last_completed_game": max([e.game_number for e in events if e.marker.endswith("GAME_END") or e.marker == "FORCE_GAME_END"], default=None),
        "last_completed_round": max([e.round_number for e in events if e.marker.endswith("ROUND_END")], default=None),
        "missing_votes": missing_votes,
        "missing_confidence": missing_confidence,
        "missing_reasoning": missing_reasoning,
    }

def game_summary_dict(db: Session, session_id: str, game_number: int) -> Dict[str, Any]:
    events = db.exec(select(EventLog).where(EventLog.session_id == session_id, EventLog.game_number == game_number).order_by(EventLog.id)).all()
    rows = db.exec(select(BehavioralResponse).where(BehavioralResponse.session_id == session_id, BehavioralResponse.game_number == game_number)).all()
    assignments = assignments_for_game(db, session_id, game_number)
    rounds_with_data = sorted({r.round_number for r in rows} | {e.round_number for e in events if e.round_number})
    return {
        "session_id": session_id,
        "game_number": game_number,
        "rounds_with_data": rounds_with_data,
        "events_saved": len(events),
        "assignments_saved": len(assignments),
        "votes_collected": sum(1 for r in rows if r.vote_submitted_at),
        "confidence_collected": sum(1 for r in rows if r.confidence_submitted_at),
        "reasoning_collected": sum(1 for r in rows if r.reasoning_submitted_at),
        "generated_at_utc": datetime.utcnow().isoformat(),
    }

def session_summary_dict(db: Session, session_id: str) -> Dict[str, Any]:
    events = db.exec(select(EventLog).where(EventLog.session_id == session_id).order_by(EventLog.id)).all()
    rows = db.exec(select(BehavioralResponse).where(BehavioralResponse.session_id == session_id)).all()
    assignments = db.exec(select(WordAssignment).where(WordAssignment.session_id == session_id)).all()
    integrity = session_integrity_report(db, session_id)
    meta = metadata_dict(db, session_id)
    qc = meta.get("qc_checklist", {}) if isinstance(meta, dict) else {}
    games_completed = sorted({e.game_number for e in events if e.marker.endswith("GAME_END") or e.marker == "FORCE_GAME_END"})
    return {
        "session_id": session_id,
        "games_completed": games_completed,
        "game_count_completed": len(games_completed),
        "events_saved": len(events),
        "assignments_saved": len(assignments),
        "behavior_rows_saved": len(rows),
        "votes_collected": sum(1 for r in rows if r.vote_submitted_at),
        "confidence_collected": sum(1 for r in rows if r.confidence_submitted_at),
        "reasoning_collected": sum(1 for r in rows if r.reasoning_submitted_at),
        "behavioral_export_verified": True,
        "lsl_verified": bool(lsl_available()),
        "labrecorder_checked": bool(qc.get("LabRecorder")),
        "audio_verified": bool(qc.get("audio")),
        "video_verified": bool(qc.get("video")),
        "force_ended": integrity.get("force_ended"),
        "force_end_type": integrity.get("force_end_type"),
        "force_end_reason": integrity.get("force_end_reason"),
        "generated_at_utc": datetime.utcnow().isoformat(),
    }


def csv_eeg_streams(db: Session, session_id: Optional[str] = None) -> str:
    rows = db.exec(select(EEGStreamSnapshot).order_by(EEGStreamSnapshot.id)).all()
    if session_id:
        rows = [r for r in rows if r.session_id == session_id]
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["id", "session_id", "stream_name", "stream_type", "source_id", "hostname", "channel_count", "nominal_srate", "channel_format", "channel_labels_json", "likely_emotiv_insight", "sample_available", "sample_timestamp_lsl", "validation_status", "warnings_json", "captured_at_utc"])
    for r in rows:
        w.writerow([r.id, r.session_id, r.stream_name, r.stream_type, r.source_id, r.hostname, r.channel_count, r.nominal_srate, r.channel_format, r.channel_labels_json, r.likely_emotiv_insight, r.sample_available, r.sample_timestamp_lsl if r.sample_timestamp_lsl is not None else "", r.validation_status, r.warnings_json, r.captured_at_utc.isoformat()])
    return buf.getvalue()

def csv_hardware_events(db: Session, session_id: Optional[str] = None, player_id: Optional[int] = None) -> str:
    out = io.StringIO()
    fields = ["session_id", "game_number", "round_number", "phase", "marker", "player_id", "value", "server_time_utc", "server_time_local", "lsl_time"]
    w = csv.DictWriter(out, fieldnames=fields); w.writeheader()
    q = select(EventLog).where(EventLog.marker.startswith("HARDWARE_"))
    if session_id: q = q.where(EventLog.session_id == session_id)
    if player_id is not None: q = q.where(EventLog.player_id == player_id)
    for e in db.exec(q.order_by(EventLog.id)).all():
        w.writerow({k: getattr(e, k) for k in fields})
    return out.getvalue()

def save_session_files(db: Session, session_id: str) -> Dict[str, str]:
    out_dir = SESSIONS_DIR / session_id
    global_dir = out_dir / "global"
    participants_dir = out_dir / "participants"
    raw_dir = out_dir / "raw"
    for d in [out_dir, global_dir, participants_dir, raw_dir]:
        d.mkdir(parents=True, exist_ok=True)

    cfg = config_dict(db, session_id)
    manifest = {
        "session_id": session_id,
        "app_version": APP_VERSION,
        "metadata": metadata_dict(db, session_id),
        "session_config": cfg,
        "integrity_report": session_integrity_report(db, session_id),
        "generated_at_utc": datetime.utcnow().isoformat(),
        "folder_policy": "XDF/raw files are the master synchronized recording; CSV/JSON files are derived exports and audit records.",
    }

    files = {
        "manifest.json": json.dumps(manifest, indent=2),
        "global/events.csv": csv_events(db, session_id),
        "global/behavior.csv": csv_behavior(db, session_id),
        "global/assignments.csv": csv_assignments(db, session_id),
        "global/eeg_streams.csv": csv_eeg_streams(db, session_id),
        "global/metadata.json": json.dumps(metadata_dict(db, session_id), indent=2),
        "global/session_config.json": json.dumps(cfg, indent=2),
        "global/integrity_report.json": json.dumps(session_integrity_report(db, session_id), indent=2),
        "global/session_summary.json": json.dumps(session_summary_dict(db, session_id), indent=2),
    }
    # Backward-compatible root copies for older V8/V9 workflows.
    files.update({
        "events.csv": files["global/events.csv"],
        "behavior.csv": files["global/behavior.csv"],
        "assignments.csv": files["global/assignments.csv"],
        "eeg_streams.csv": files["global/eeg_streams.csv"],
        "metadata.json": files["global/metadata.json"],
        "integrity_report.json": files["global/integrity_report.json"],
        "session_summary.json": files["global/session_summary.json"],
    })

    games = sorted({r.game_number for r in db.exec(select(BehavioralResponse).where(BehavioralResponse.session_id == session_id)).all()} |
                   {a.game_number for a in db.exec(select(WordAssignment).where(WordAssignment.session_id == session_id)).all()} |
                   {e.game_number for e in db.exec(select(EventLog).where(EventLog.session_id == session_id)).all()})
    for game_number in games:
        files[f"global/game_{game_number}_summary.json"] = json.dumps(game_summary_dict(db, session_id, game_number), indent=2)

    for i in range(1, int(cfg.get("participant_count", 5)) + 1):
        pid = f"P{i:02d}"
        pdir = participants_dir / pid
        pdir.mkdir(parents=True, exist_ok=True)
        files[f"participants/{pid}/behavioral.csv"] = csv_behavior(db, session_id, player_id=i)
        files[f"participants/{pid}/device_map.json"] = json.dumps({"participant": pid, "devices": cfg.get("device_map", {}).get(pid, {}), "enabled_modalities": cfg.get("enabled_modalities", [])}, indent=2)
        files[f"participants/{pid}/quality_log.csv"] = csv_hardware_events(db, session_id, player_id=i)
        for m in cfg.get("enabled_modalities", []):
            safe = m.lower().replace(" ", "_")
            placeholder = {
                "participant": pid,
                "modality": m,
                "status": "reserved_for_postprocessed_stream_export",
                "note": "Raw synchronized samples should remain in XDF. Derived modality CSVs can be written here after XDF conversion.",
            }
            files[f"participants/{pid}/{safe}_placeholder.json"] = json.dumps(placeholder, indent=2)

    for name, content in files.items():
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return {name: str(out_dir / name) for name in files}

# Pages
@app.get("/", response_class=HTMLResponse)
def root(): return (STATIC_DIR / "moderator.html").read_text(encoding="utf-8")
@app.get("/observer", response_class=HTMLResponse)
def observer(): return (STATIC_DIR / "observer.html").read_text(encoding="utf-8")
@app.get("/participant", response_class=HTMLResponse)
def participant_page(): return (STATIC_DIR / "participant.html").read_text(encoding="utf-8")
@app.get("/p{player_id}", response_class=HTMLResponse)
def fixed_participant_page(player_id: int):
    if player_id < 1 or player_id > 5: raise HTTPException(404, detail="Participant station must be p1 through p5")
    return (STATIC_DIR / "participant.html").read_text(encoding="utf-8")

# API
@app.get("/api/health")
def health(): return {"ok": True, "lsl_available": lsl_available(), "app_version": APP_VERSION}

@app.get("/api/state")
def read_state(db: Session = Depends(get_session)):
    state = get_or_create_state(db)
    return {**state.dict(), "next_action": get_next_action(db, state), "phase_duration_sec": PHASE_DURATIONS_SEC.get(state.phase), "phase_label": PHASE_LABELS.get(state.phase, state.phase), "server_time_utc": datetime.utcnow().isoformat(), "has_assignment": game_has_assignment(db, state.session_id, state.game_number)}

@app.post("/api/participants/heartbeat")
def participant_heartbeat(payload: HeartbeatPayload, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    rec = db.exec(select(Participant).where(Participant.session_id == payload.session_id, Participant.player_id == payload.player_id)).first()
    was_timed_out = True
    if rec and rec.last_seen_utc:
        was_timed_out = (datetime.utcnow() - rec.last_seen_utc).total_seconds() > 5.0
    if not rec:
        rec = Participant(session_id=payload.session_id, player_id=payload.player_id)
    rec.current_phase_seen = payload.current_phase_seen
    rec.last_seen_utc = datetime.utcnow()
    db.add(rec)
    db.commit()
    log_connection_event_if_needed(db, state, payload.player_id, connected=True, note=f"phase={payload.current_phase_seen}")
    return {"ok": True, "last_seen_utc": rec.last_seen_utc.isoformat(), "reconnected": bool(was_timed_out)}

@app.get("/api/status/participants")
def participant_status(session_id: str = "S001", db: Session = Depends(get_session)):
    state = get_or_create_state(db, session_id)
    rows = db.exec(select(Participant).where(Participant.session_id == session_id)).all()
    now = datetime.utcnow()
    by = {r.player_id: r for r in rows}
    status = {}
    for i in PLAYERS:
        r = by.get(i)
        if not r or not r.last_seen_utc:
            status[str(i)] = {"connected": False, "last_seen_utc": None, "age_sec": None, "current_phase_seen": ""}
        else:
            age = (now - r.last_seen_utc).total_seconds()
            connected = age <= 5.0
            status[str(i)] = {"connected": connected, "last_seen_utc": r.last_seen_utc.isoformat(), "age_sec": round(age, 1), "current_phase_seen": r.current_phase_seen}
            if not connected:
                log_connection_event_if_needed(db, state, i, connected=False, note=f"last_seen_age_sec={round(age, 1)}")
    return {"session_id": session_id, "status": status}

@app.get("/api/status/responses")
def response_status(session_id: str = "S001", game_number: int = 1, round_number: int = 1, db: Session = Depends(get_session)):
    return {"session_id": session_id, "game_number": game_number, "round_number": round_number, "status": response_status_dict(db, session_id, game_number, round_number)}

@app.get("/api/status/preflight")
def preflight_status(session_id: str = "S001", db: Session = Depends(get_session)):
    p = participant_status(session_id, db)["status"]
    meta = metadata_dict(db, session_id)
    qc = meta.get("qc_checklist", {}) if isinstance(meta, dict) else {}
    cfg = config_dict(db, session_id)
    enabled = cfg.get("enabled_modalities", [])
    connected_required = {str(i): p.get(str(i), {}).get("connected", False) for i in range(1, int(cfg.get("participant_count", 5)) + 1)}
    checks = {
        "setup_locked": bool(cfg.get("setup_locked")),
        "participants_connected": all(connected_required.values()) if connected_required else False,
        "metadata_saved": "warning" not in meta,
        "word_pairs_available": len(load_word_pairs()) >= MAX_GAMES,
        "lsl_marker_stream": lsl_available(),
        "labrecorder_checked": bool(qc.get("LabRecorder")),
        "device_mapping_complete": config_has_complete_mapping(cfg),
        "enabled_modalities_checked": enabled_qc_ready(qc, enabled),
        "eeg_checked": bool(qc.get("EEG")),
        "ecg_checked": bool(qc.get("ECG")),
        "gsr_checked": bool(qc.get("GSR")),
        "emg_checked": bool(qc.get("EMG")),
        "audio_checked": bool(qc.get("audio")),
        "video_checked": bool(qc.get("video")),
    }
    # V10.1 relaxed development mode: do not block testing because sensors,
    # participant tabs, device mapping, LabRecorder QC, or setup lock are incomplete.
    # These remain visible as WARN/FAIL items in the moderator checklist, but Start
    # Session is allowed so one participant station can be integrated step by step.
    ready_strict = all([checks["setup_locked"], checks["participants_connected"], checks["word_pairs_available"], checks["lsl_marker_stream"], checks["labrecorder_checked"], checks["device_mapping_complete"], checks["enabled_modalities_checked"]])
    ready_minimum = checks["word_pairs_available"] and checks["lsl_marker_stream"]
    return {
        "session_id": session_id,
        "config": cfg,
        "checks": checks,
        "ready_minimum": ready_minimum,
        "ready_strict": ready_strict,
        "start_mode": "one_station_development",
        "note": "V10.1 allows Start Session with relaxed checks. Use the checklist to document missing sensors; strict validation can be re-enabled after one participant station is stable."
    }

@app.get("/api/session_config")
def get_session_config(session_id: str = "S001", db: Session = Depends(get_session)):
    return config_dict(db, session_id)

@app.post("/api/session_config")
def save_session_config(payload: SessionConfigPayload, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    rec = get_or_create_config(db, payload.session_id)
    if rec.setup_locked and state.phase not in {"WAITING", "SESSION_END"}:
        raise HTTPException(400, detail="Session setup is locked during an active recording. End the session before changing participant count or modalities.")
    enabled = []
    for m in payload.enabled_modalities:
        nm = _norm_modality(m)
        if nm and nm not in enabled:
            enabled.append(nm)
    rec.experiment_name = payload.experiment_name or "spy_game"
    rec.participant_count = payload.participant_count
    rec.enabled_modalities_json = json.dumps(enabled)
    rec.device_map_json = json.dumps(payload.device_map or {})
    rec.output_root = payload.output_root
    rec.setup_locked = bool(payload.setup_locked)
    rec.locked_at_utc = datetime.utcnow() if rec.setup_locked and not rec.locked_at_utc else (None if not rec.setup_locked else rec.locked_at_utc)
    rec.updated_at = datetime.utcnow()
    db.add(rec); db.commit(); db.refresh(rec)
    log_event(db, state, "SESSION_CONFIG_SAVED", value=json.dumps({"experiment": rec.experiment_name, "participants": rec.participant_count, "modalities": enabled, "locked": rec.setup_locked}))
    return {"ok": True, "config": config_dict(db, payload.session_id)}

@app.post("/api/session_config/lock")
def lock_session_config(payload: LockSetupPayload, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    rec = get_or_create_config(db, payload.session_id)
    if state.phase not in {"WAITING", "SESSION_END"}:
        raise HTTPException(400, detail="Setup can only be locked/unlocked before the session starts or after it ends.")
    rec.setup_locked = bool(payload.lock)
    rec.locked_at_utc = datetime.utcnow() if payload.lock else None
    rec.updated_at = datetime.utcnow()
    db.add(rec); db.commit(); db.refresh(rec)
    log_event(db, state, "SESSION_SETUP_LOCKED" if payload.lock else "SESSION_SETUP_UNLOCKED")
    return {"ok": True, "config": config_dict(db, payload.session_id)}

@app.post("/api/metadata")
def save_metadata(payload: MetadataPayload, db: Session = Depends(get_session)):
    rec = db.exec(select(SessionMetadata).where(SessionMetadata.session_id == payload.session_id)).first() or SessionMetadata(session_id=payload.session_id)
    data = payload.dict(); qc = {"LabRecorder": data.pop("qc_labrecorder", False), "EEG": data.pop("qc_eeg", False), "ECG": data.pop("qc_ecg", False), "GSR": data.pop("qc_gsr", False), "EMG": data.pop("qc_emg", False), "audio": data.pop("qc_audio", False), "video": data.pop("qc_video", False)}
    for k, v in data.items(): setattr(rec, k, v)
    rec.qc_checklist_json = json.dumps(qc); rec.updated_at = datetime.utcnow(); db.add(rec); db.commit()
    return {"ok": True}
@app.get("/api/metadata")
def get_metadata(session_id: str = "S001", db: Session = Depends(get_session)): return metadata_dict(db, session_id)

@app.post("/api/control/set_phase")
def set_phase(payload: SetPhase, db: Session = Depends(get_session)):
    if payload.phase not in PHASES: raise HTTPException(400, detail=f"Unknown phase: {payload.phase}")
    state = get_or_create_state(db, payload.session_id)
    if payload.phase == "SESSION_START":
        pf = preflight_status(payload.session_id, db)
        # V10.1 relaxed one-station development mode. Only block if the core
        # software prerequisites are missing. Hardware and full 5-participant
        # readiness are warnings, not blockers, until the first station works.
        if not pf.get("ready_minimum"):
            missing = [k for k, v in pf.get("checks", {}).items() if not v and k in {"word_pairs_available", "lsl_marker_stream"}]
            raise HTTPException(400, detail="Minimum start checks failed: " + ", ".join(missing))
    # Allow a clean new-session start from a completed/stale active state. This does not delete prior session files.
    if payload.phase == "SESSION_START" and (state.phase == "SESSION_END" or state.session_id != payload.session_id):
        state.session_id = payload.session_id
        state.game_number = payload.game_number or 1
        state.round_number = 1
        state.phase = "WAITING"
        state.active_speaker = None
        state.started_at = datetime.utcnow()
        state.updated_at = datetime.utcnow()
        db.add(state); db.commit(); db.refresh(state)
    validate_phase_transition(db, state, payload.phase, payload.round_number)
    previous_phase = state.phase
    previous_speaker = state.active_speaker
    if payload.game_number is not None: state.game_number = payload.game_number
    if payload.round_number is not None: state.round_number = payload.round_number
    state.session_id = payload.session_id or state.session_id
    state.phase = payload.phase
    state.active_speaker = int(payload.phase.split("P")[-1]) if payload.phase.startswith("SPEAKER_P") else None
    state.updated_at = datetime.utcnow(); db.add(state); db.commit(); db.refresh(state)
    marker = marker_for_phase(state, payload.phase); log_event(db, state, marker, value=payload.value)
    # Audible speech-boundary cue command markers. The browser plays one long tone
    # on every participant station when a speaking segment begins. Transitioning
    # from one speaker to the next uses one tone as both the prior end and next start.
    if payload.phase.startswith("SPEAKER_P"):
        log_event(db, state, f"G{state.game_number}_R{state.round_number}_SPEECH_BOUNDARY_BEEP", player_id=state.active_speaker, value=f"start=P{state.active_speaker}")
    elif previous_phase.startswith("SPEAKER_P") and not payload.phase.startswith("SPEAKER_P"):
        log_event(db, state, f"G{state.game_number}_R{state.round_number}_SPEECH_BOUNDARY_BEEP", player_id=previous_speaker, value=f"end=P{previous_speaker};next={payload.phase}")
    saved = save_session_files(db, state.session_id) if payload.phase in {"GAME_END", "SESSION_END"} else None
    return {"ok": True, "state": state, "marker": marker, "saved_files": saved, "integrity": session_integrity_report(db, state.session_id) if saved else None}

@app.post("/api/control/start_game")
def start_game(payload: StartGame, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    if state.phase not in {"SESSION_START", "GAME_END", "GAME_READY"}:
        raise HTTPException(400, detail=f"Cannot create a game from phase {state.phase}. Start session or finish the current game first.")
    return create_game_assignment(db, payload.session_id, payload.game_number, payload.spy_player)

@app.post("/api/control/next_game")
def next_game(session_id: str = "S001", db: Session = Depends(get_session)):
    state = get_or_create_state(db, session_id)
    if state.phase != "GAME_END": raise HTTPException(400, detail="Next game can only be created after the current game has ended.")
    if state.game_number >= MAX_GAMES: raise HTTPException(400, detail="Already at Game 5")
    return create_game_assignment(db, state.session_id, state.game_number + 1, None)

@app.post("/api/control/reset_game")
def reset_game(session_id: str = "S001", db: Session = Depends(get_session)):
    state = get_or_create_state(db, session_id); log_event(db, state, f"G{state.game_number}_GAME_RESET", value="moderator_reset")
    state.round_number = 1; state.phase = "GAME_READY" if game_has_assignment(db, state.session_id, state.game_number) else "SESSION_START"; state.active_speaker = None; state.updated_at = datetime.utcnow(); db.add(state); db.commit(); db.refresh(state)
    return {"ok": True, "state": state}

def clear_active_session_records(db: Session, session_id: str) -> Dict[str, int]:
    """Clear reusable active-session rows for a clean one-station test run.

    Saved files under data/sessions are not touched. This prevents old S001
    events, assignments, responses, participants, and metadata from leaking into
    a new pilot run when the operator reuses the same session ID.
    """
    deleted: Dict[str, int] = {}
    for model in (EventLog, BehavioralResponse, WordAssignment, Participant, SessionMetadata):
        rows = db.exec(select(model).where(model.session_id == session_id)).all()
        deleted[model.__name__] = len(rows)
        for row in rows:
            db.delete(row)
    cfg = db.exec(select(SessionConfig).where(SessionConfig.session_id == session_id)).first()
    if not cfg:
        cfg = SessionConfig(session_id=session_id, experiment_name="spy_game")
    cfg.participant_count = 1
    cfg.enabled_modalities_json = json.dumps(["ECG"])
    cfg.device_map_json = json.dumps({"P01": {"ECG": "ShimmerECG", "Markers": "ShimmerMarkers", "Diagnostics": "ShimmerDiagnostics_ECG"}})
    cfg.setup_locked = False
    cfg.locked_at_utc = None
    cfg.updated_at = datetime.utcnow()
    db.add(cfg)
    db.commit()
    return deleted

@app.post("/api/control/new_session")
def new_session(payload: NewSessionPayload, db: Session = Depends(get_session)):
    """Start a fresh active session state for a clean one-station test run."""
    deleted = clear_active_session_records(db, payload.session_id)
    state = get_or_create_state(db, payload.session_id)
    state.session_id = payload.session_id
    state.game_number = 1
    state.round_number = 1
    state.phase = "WAITING"
    state.active_speaker = None
    state.started_at = datetime.utcnow()
    state.updated_at = datetime.utcnow()
    db.add(state); db.commit(); db.refresh(state)
    get_or_create_config(db, payload.session_id)
    log_event(db, state, "ACTIVE_SESSION_RESET", value="new_session_requested_clean_v11")
    return {"ok": True, "state": state.dict(), "config": config_dict(db, payload.session_id), "cleared_active_rows": deleted}

@app.post("/api/control/force_end_game")
def force_end_game(payload: ForceEndPayload, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    if state.phase in {"WAITING", "SESSION_END"}:
        raise HTTPException(400, detail="No active game to force end.")
    reason = payload.reason.strip() or "moderator decision"
    if payload.note.strip():
        reason = f"{reason}: {payload.note.strip()}"
    log_event(db, state, "FORCE_GAME_END", value=reason)
    state.phase = "GAME_END"
    state.active_speaker = None
    state.updated_at = datetime.utcnow()
    db.add(state); db.commit(); db.refresh(state)
    saved = save_session_files(db, state.session_id)
    return {"ok": True, "state": state, "marker": "FORCE_GAME_END", "saved_files": saved, "integrity": session_integrity_report(db, state.session_id)}

@app.post("/api/control/force_end_session")
def force_end_session(payload: ForceEndPayload, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    reason = payload.reason.strip() or "moderator decision"
    if payload.note.strip():
        reason = f"{reason}: {payload.note.strip()}"
    log_event(db, state, "FORCE_SESSION_END", value=reason)
    state.phase = "SESSION_END"
    state.active_speaker = None
    state.updated_at = datetime.utcnow()
    db.add(state); db.commit(); db.refresh(state)
    saved = save_session_files(db, state.session_id)
    return {"ok": True, "state": state, "marker": "FORCE_SESSION_END", "saved_files": saved, "integrity": session_integrity_report(db, state.session_id)}

@app.get("/api/status/eeg")
def eeg_status(session_id: str = "S001", save_snapshot: bool = False, db: Session = Depends(get_session)):
    result = scan_eeg_streams(timeout=1.5, pull_sample=True)
    if save_snapshot and result.get("available"):
        state = get_or_create_state(db, session_id)
        for stream in result.get("streams", []):
            rec = EEGStreamSnapshot(
                session_id=session_id,
                stream_name=stream.get("name", ""),
                stream_type=stream.get("type", ""),
                source_id=stream.get("source_id", ""),
                hostname=stream.get("hostname", ""),
                channel_count=int(stream.get("channel_count") or 0),
                nominal_srate=float(stream.get("nominal_srate") or 0.0),
                channel_format=str(stream.get("channel_format") or ""),
                channel_labels_json=json.dumps(stream.get("channel_labels", [])),
                likely_emotiv_insight=bool(stream.get("likely_emotiv_insight")),
                sample_available=bool(stream.get("sample_available")),
                sample_timestamp_lsl=stream.get("sample_timestamp_lsl"),
                validation_status=stream.get("validation_status", ""),
                warnings_json=json.dumps(stream.get("warnings", [])),
            )
            db.add(rec)
        db.commit()
        log_event(db, state, "EEG_LSL_PREFLIGHT_SNAPSHOT", value=json.dumps(result.get("summary", {})))
    return result

@app.post("/api/eeg/log_preflight")
def eeg_log_preflight(session_id: str = "S001", db: Session = Depends(get_session)):
    return eeg_status(session_id=session_id, save_snapshot=True, db=db)

@app.post("/api/control/hardware_event")
def hardware_event(payload: HardwareEventPayload, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    marker = f"HARDWARE_{payload.status.upper()}_{payload.device.upper()}" + (f"_P{payload.player_id}" if payload.player_id else "")
    value = payload.note or payload.status
    log_event(db, state, marker, player_id=payload.player_id, value=value)
    return {"ok": True, "marker": marker}

@app.get("/api/media/status")
def get_media_status(session_id: str = "S001"):
    status = media_status_for(session_id)
    return {"session_id": safe_session_id(session_id), "status": {str(k): v for k, v in status.items()}}

@app.post("/api/media/event")
def media_event(payload: MediaEventPayload, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    status_map = {
        "ready": "ready",
        "recording_started": "recording",
        "recording_stopped": "stopped",
        "upload_completed": "saved",
        "error": "error",
        "permission_denied": "permission_denied",
    }
    rec = update_media_status(payload.session_id, payload.player_id, status=status_map[payload.event], segment=payload.segment, note=payload.note)
    marker = f"P{payload.player_id:03d}_MEDIA_{payload.event.upper()}"
    log_event(db, state, marker, player_id=payload.player_id, value=json.dumps({"segment": payload.segment, "note": payload.note}))
    return {"ok": True, "status": rec, "marker": marker}

@app.post("/api/media/upload")
async def media_upload(request: Request, session_id: str = "S001", player_id: int = 1, segment: int = 1, started_utc: str = "", ended_utc: str = "", media_kind: str = "camera_audio", camera_label: str = "", microphone_label: str = "", db: Session = Depends(get_session)):
    if player_id < 1 or player_id > 5:
        raise HTTPException(400, detail="player_id must be 1 through 5")
    data = await request.body()
    if not data:
        raise HTTPException(400, detail="Empty media upload")
    if len(data) > 2_000_000_000:
        raise HTTPException(413, detail="Media segment exceeds 2 GB limit")
    sid = safe_session_id(session_id)
    pid = f"P{player_id:03d}"
    media_dir = SESSIONS_DIR / sid / "participants" / pid / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    seg = max(1, int(segment))
    kind = "audio_only" if media_kind == "audio_only" else "camera_audio"
    filename = f"{pid}_{sid}_{kind}_part{seg:02d}.webm"
    path = media_dir / filename
    path.write_bytes(data)
    metadata = {
        "session_id": sid, "participant_id": pid, "segment": seg,
        "filename": filename, "media_kind": kind, "mime_type": request.headers.get("content-type", "video/webm"), "camera_label": camera_label, "microphone_label": microphone_label,
        "size_bytes": len(data), "started_utc": started_utc, "ended_utc": ended_utc,
        "received_utc": utc_now().isoformat(),
    }
    (media_dir / f"{pid}_{sid}_{kind}_part{seg:02d}_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    state = get_or_create_state(db, sid)
    update_media_status(sid, player_id, status="saved", segment=seg, last_file=str(path), note=f"{len(data)} bytes")
    log_event(db, state, f"P{player_id:03d}_MEDIA_UPLOAD_COMPLETED", player_id=player_id, value=json.dumps(metadata))
    return {"ok": True, "file": str(path), "metadata": metadata}

@app.get("/api/assignment")
def get_assignment(session_id: str, game_number: int, player_id: int, db: Session = Depends(get_session)):
    rec = db.exec(select(WordAssignment).where(WordAssignment.session_id == session_id, WordAssignment.game_number == game_number, WordAssignment.player_id == player_id)).first()
    if not rec: raise HTTPException(404, detail="No assignment found for this player/game")
    return {"player_id": player_id, "game_number": game_number, "word": rec.word, "role": rec.role}

@app.post("/api/responses/vote")
def submit_vote(payload: SubmitVote, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    if state.phase != "VOTE_PHASE" or state.game_number != payload.game_number or state.round_number != payload.round_number: raise HTTPException(400, detail="Vote submission is not allowed in the current phase.")
    rec = upsert_response(db, payload.session_id, payload.game_number, payload.round_number, payload.player_id)
    if rec.vote_submitted_at: raise HTTPException(400, detail="Vote already submitted for this round.")
    now_utc = utc_now()
    rec.vote_target = payload.vote_target
    rec.vote_submitted_at = now_utc
    rec.vote_submitted_local = local_time_iso(now_utc)
    rec.submitted_at = now_utc
    db.add(rec); db.commit(); db.refresh(rec)
    evt = log_event(db, state, f"G{payload.game_number}_R{payload.round_number}_VOTE_SUBMIT_P{payload.player_id}", player_id=payload.player_id, value=f"target=P{payload.vote_target}")
    rec.vote_lsl_time = evt.lsl_time
    rec.vote_rt_sec = reaction_time_sec(find_phase_start_event(db, payload.session_id, payload.game_number, payload.round_number, "VOTE_PHASE"), evt.lsl_time, now_utc)
    db.add(rec); db.commit()
    return {"ok": True, "vote_lsl_time": rec.vote_lsl_time, "vote_rt_sec": rec.vote_rt_sec}

@app.post("/api/responses/confidence")
def submit_confidence(payload: SubmitConfidence, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    if state.phase != "CONFIDENCE_PHASE" or state.game_number != payload.game_number or state.round_number != payload.round_number: raise HTTPException(400, detail="Confidence submission is not allowed in the current phase.")
    rec = upsert_response(db, payload.session_id, payload.game_number, payload.round_number, payload.player_id)
    if rec.confidence_submitted_at: raise HTTPException(400, detail="Confidence already submitted for this round.")
    now_utc = utc_now()
    rec.confidence = payload.confidence
    rec.confidence_submitted_at = now_utc
    rec.confidence_submitted_local = local_time_iso(now_utc)
    rec.submitted_at = now_utc
    db.add(rec); db.commit(); db.refresh(rec)
    evt = log_event(db, state, f"G{payload.game_number}_R{payload.round_number}_CONFIDENCE_SUBMIT_P{payload.player_id}", player_id=payload.player_id, value=str(payload.confidence))
    rec.confidence_lsl_time = evt.lsl_time
    rec.confidence_rt_sec = reaction_time_sec(find_phase_start_event(db, payload.session_id, payload.game_number, payload.round_number, "CONFIDENCE_PHASE"), evt.lsl_time, now_utc)
    db.add(rec); db.commit()
    return {"ok": True, "confidence_lsl_time": rec.confidence_lsl_time, "confidence_rt_sec": rec.confidence_rt_sec}

@app.post("/api/responses/reasoning")
def submit_reasoning(payload: SubmitReasoning, db: Session = Depends(get_session)):
    state = get_or_create_state(db, payload.session_id)
    if state.phase != "REASONING_PHASE" or state.game_number != payload.game_number or state.round_number != payload.round_number: raise HTTPException(400, detail="Reasoning submission is not allowed in the current phase.")
    rec = upsert_response(db, payload.session_id, payload.game_number, payload.round_number, payload.player_id)
    if rec.reasoning_submitted_at: raise HTTPException(400, detail="Reasoning already submitted for this round.")
    now_utc = utc_now()
    rec.reasons_text = ", ".join(payload.reasons)
    rec.reasoning_submitted_at = now_utc
    rec.reasoning_submitted_local = local_time_iso(now_utc)
    rec.submitted_at = now_utc
    db.add(rec); db.commit(); db.refresh(rec)
    evt = log_event(db, state, f"G{payload.game_number}_R{payload.round_number}_REASONING_SUBMIT_P{payload.player_id}", player_id=payload.player_id, value=rec.reasons_text)
    rec.reasoning_lsl_time = evt.lsl_time
    rec.reasoning_rt_sec = reaction_time_sec(find_phase_start_event(db, payload.session_id, payload.game_number, payload.round_number, "REASONING_PHASE"), evt.lsl_time, now_utc)
    db.add(rec); db.commit()
    return {"ok": True, "reasoning_lsl_time": rec.reasoning_lsl_time, "reasoning_rt_sec": rec.reasoning_rt_sec}

@app.get("/api/status/timers")
def timers(session_id: str = "S001", db: Session = Depends(get_session)):
    state = get_or_create_state(db, session_id)
    events = db.exec(select(EventLog).where(EventLog.session_id == state.session_id).order_by(EventLog.id)).all()
    now = datetime.utcnow()

    def elapsed_since_latest(pred):
        starts = [e.server_time_utc for e in events if pred(e)]
        return None if not starts else round((now - starts[-1]).total_seconds(), 1)

    return {
        "session_elapsed_sec": elapsed_since_latest(lambda e: e.marker == "SESSION_START"),
        "game_elapsed_sec": elapsed_since_latest(lambda e: e.game_number == state.game_number and ("ASSIGNMENT_CREATED" in e.marker or "WORD_PHASE" in e.marker)),
        "server_time_utc": now.isoformat(),
        "timer_rule": "latest_start_event_for_reused_session_ids",
    }

@app.get("/api/status/games")
def game_status(session_id: str = "S001", db: Session = Depends(get_session)):
    state = get_or_create_state(db, session_id); assignments = db.exec(select(WordAssignment).where(WordAssignment.session_id == state.session_id)).all(); assigned = {a.game_number for a in assignments}; events = db.exec(select(EventLog).where(EventLog.session_id == state.session_id)).all(); ended = {e.game_number for e in events if e.marker.endswith("GAME_END")}
    out = {}
    for i in range(1, MAX_GAMES+1):
        out[str(i)] = "active" if i == state.game_number and state.phase != "GAME_END" else "complete" if i in ended else "assigned" if i in assigned else "pending"
    return {"current_game": state.game_number, "games": out}

@app.get("/api/status/autosave")
def autosave_status(session_id: str = "S001"):
    out_dir = SESSIONS_DIR / session_id; files = ["events.csv", "behavior.csv", "assignments.csv", "metadata.json", "integrity_report.json", "session_summary.json"]
    return {"session_id": session_id, "folder": str(out_dir), "files": {name: (out_dir / name).exists() for name in files}}

@app.get("/api/status/markers")
def marker_inspector(session_id: str = "S001", limit: int = 10, db: Session = Depends(get_session)):
    rows = db.exec(select(EventLog).where(EventLog.session_id == session_id).order_by(EventLog.id)).all()[-limit:]
    return {"markers": [{"id": r.id, "marker": r.marker, "phase": r.phase, "player_id": r.player_id, "value": r.value, "server_time_utc": r.server_time_utc.isoformat(), "server_time_local": r.server_time_local, "lsl_time": r.lsl_time} for r in rows]}

@app.get("/api/status/completeness")
def completeness(session_id: str = "S001", db: Session = Depends(get_session)): return session_integrity_report(db, session_id)
@app.get("/api/lsl/status")
def api_lsl_status():
    return lsl_status()

@app.post("/api/lsl/init")
def api_lsl_init():
    ok = ensure_outlet()
    return {"ok": ok, **lsl_status()}

@app.post("/api/lsl/test_marker")
def api_lsl_test_marker(session_id: str = "S001", db: Session = Depends(get_session)):
    state = get_or_create_state(db, session_id)
    # Preserve the requested session id if the moderator is testing before normal session flow.
    if session_id and state.session_id != session_id:
        state.session_id = session_id
    evt = log_event(db, state, "LSL_TEST_MARKER", value="manual_test")
    return {
        "ok": evt.lsl_time is not None,
        "marker": evt.marker,
        "server_time_utc": evt.server_time_utc.isoformat(),
        "server_time_local": evt.server_time_local,
        "lsl_time": evt.lsl_time,
        "lsl_status": lsl_status(),
    }

@app.get("/api/status/xdf")
def xdf_status(session_id: str = "S001", db: Session = Depends(get_session)):
    meta = metadata_dict(db, session_id); qc = meta.get("qc_checklist", {}) if isinstance(meta, dict) else {}
    status = lsl_status()
    return {
        "lsl_available": status["available"],
        "lsl_outlet_created": status["outlet_created"],
        "lsl_stream_name": status["stream_name"],
        "lsl_source_id": status["source_id"],
        "lsl_local_clock": status["local_clock"],
        "lsl_last_error": status["last_error"],
        "labrecorder_checked": bool(qc.get("LabRecorder")),
        "xdf_ready": status["available"] and status["outlet_created"] and bool(qc.get("LabRecorder")),
        "note": "Use Initialize LSL Marker Stream, then open LabRecorder and verify the SpyGameMarkers stream appears. Test Marker writes LSL_TEST_MARKER to events.csv and the LSL stream."
    }
@app.get("/api/status/sessions")
def sessions_status():
    folders = sorted([p.name for p in SESSIONS_DIR.iterdir() if p.is_dir()]) if SESSIONS_DIR.exists() else []
    return {"sessions": folders}

@app.get("/api/word_pairs.csv", response_class=PlainTextResponse)
def export_word_pairs(): return WORD_PAIRS_FILE.read_text(encoding="utf-8")
@app.get("/api/export/events.csv", response_class=PlainTextResponse)
def export_events(session_id: Optional[str] = None, db: Session = Depends(get_session)): return csv_events(db, session_id)
@app.get("/api/export/behavior.csv", response_class=PlainTextResponse)
def export_behavior(session_id: Optional[str] = None, db: Session = Depends(get_session)): return csv_behavior(db, session_id)
@app.get("/api/export/assignments.csv", response_class=PlainTextResponse)
def export_assignments(session_id: Optional[str] = None, db: Session = Depends(get_session)): return csv_assignments(db, session_id)
@app.get("/api/export/session_config.json")
def export_session_config(session_id: str = "S001", db: Session = Depends(get_session)): return config_dict(db, session_id)
@app.post("/api/save_session")
def save_session(session_id: str = "S001", db: Session = Depends(get_session)): return {"ok": True, "saved_files": save_session_files(db, session_id), "integrity": session_integrity_report(db, session_id)}
