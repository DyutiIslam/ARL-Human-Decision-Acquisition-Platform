from __future__ import annotations
from datetime import datetime
from typing import Optional
import uuid
from sqlmodel import SQLModel, Field


class Participant(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: str = Field(index=True)
    player_id: int = Field(ge=1, le=5, index=True)
    code: str = Field(default="")
    current_phase_seen: str = Field(default="")
    last_seen_utc: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AcquisitionState(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    session_id: str = Field(default="S001", index=True)
    game_number: int = Field(default=1, ge=1, le=5)
    round_number: int = Field(default=1, ge=1, le=4)
    phase: str = Field(default="WAITING")
    active_speaker: Optional[int] = Field(default=None, ge=1, le=5)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WordAssignment(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    game_number: int = Field(ge=1, le=5, index=True)
    player_id: int = Field(ge=1, le=5)
    role: str
    word: str
    common_word: str
    spy_word: str
    spy_player: int = Field(ge=1, le=5)


class EventLog(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    game_number: int
    round_number: int
    phase: str
    marker: str = Field(index=True)
    active_speaker: Optional[int] = None
    player_id: Optional[int] = None
    value: Optional[str] = None
    server_time_utc: datetime = Field(default_factory=datetime.utcnow, index=True)
    server_time_local: str = Field(default="")
    lsl_time: Optional[float] = None


class BehavioralResponse(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    game_number: int = Field(ge=1, le=5)
    round_number: int = Field(ge=1, le=4)
    player_id: int = Field(ge=1, le=5)
    vote_target: Optional[int] = Field(default=None, ge=1, le=5)
    confidence: Optional[int] = Field(default=None, ge=1, le=5)
    reasons_text: str = Field(default="")
    vote_submitted_at: Optional[datetime] = None
    vote_submitted_local: str = Field(default="")
    vote_lsl_time: Optional[float] = None
    vote_rt_sec: Optional[float] = None
    confidence_submitted_at: Optional[datetime] = None
    confidence_submitted_local: str = Field(default="")
    confidence_lsl_time: Optional[float] = None
    confidence_rt_sec: Optional[float] = None
    reasoning_submitted_at: Optional[datetime] = None
    reasoning_submitted_local: str = Field(default="")
    reasoning_lsl_time: Optional[float] = None
    reasoning_rt_sec: Optional[float] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class SessionMetadata(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)
    group_id: str = Field(default="")
    operator: str = Field(default="")
    experiment_version: str = Field(default="v1.1-acquisition-final")
    word_set_version: str = Field(default="default_v1")
    participant_p1: str = Field(default="")
    participant_p2: str = Field(default="")
    participant_p3: str = Field(default="")
    participant_p4: str = Field(default="")
    participant_p5: str = Field(default="")
    eeg_notes: str = Field(default="")
    ecg_notes: str = Field(default="")
    gsr_notes: str = Field(default="")
    emg_notes: str = Field(default="")
    audio_notes: str = Field(default="")
    video_notes: str = Field(default="")
    operator_notes: str = Field(default="")
    qc_checklist_json: str = Field(default="{}")
    session_notes: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EEGStreamSnapshot(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    stream_name: str = Field(default="", index=True)
    stream_type: str = Field(default="")
    source_id: str = Field(default="")
    hostname: str = Field(default="")
    channel_count: int = Field(default=0)
    nominal_srate: float = Field(default=0.0)
    channel_format: str = Field(default="")
    channel_labels_json: str = Field(default="[]")
    likely_emotiv_insight: bool = Field(default=False)
    sample_available: bool = Field(default=False)
    sample_timestamp_lsl: Optional[float] = None
    validation_status: str = Field(default="")
    warnings_json: str = Field(default="[]")
    captured_at_utc: datetime = Field(default_factory=datetime.utcnow, index=True)


class SessionConfig(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)
    experiment_name: str = Field(default="spy_game")
    participant_count: int = Field(default=5, ge=1, le=5)
    enabled_modalities_json: str = Field(default='["EEG"]')
    device_map_json: str = Field(default="{}")
    output_root: str = Field(default="")
    setup_locked: bool = Field(default=False)
    locked_at_utc: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
