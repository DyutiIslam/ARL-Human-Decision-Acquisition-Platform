from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from pylsl import StreamInlet, resolve_streams, local_clock
except Exception:
    StreamInlet = None
    resolve_streams = None
    local_clock = None

EXPECTED_INSIGHT_CHANNELS = {"AF3", "AF4", "T7", "T8", "Pz"}
EXPECTED_INSIGHT_SRATE = 128.0


@dataclass
class EEGStreamCheck:
    name: str
    type: str
    source_id: str
    hostname: str
    channel_count: int
    nominal_srate: float
    channel_format: str
    created_at_lsl: float
    channel_labels: List[str]
    likely_emotiv_insight: bool
    sample_available: bool
    sample_timestamp_lsl: Optional[float]
    sample_length: Optional[int]
    validation_status: str
    warnings: List[str]

    def dict(self) -> Dict[str, Any]:
        return asdict(self)


def eeg_lsl_available() -> bool:
    return StreamInlet is not None and resolve_streams is not None and local_clock is not None


def _child_text(node: Any, name: str) -> str:
    try:
        child = node.child(name)
        value = child.child_value()
        return value or ""
    except Exception:
        return ""


def _channel_labels(info: Any) -> List[str]:
    labels: List[str] = []
    try:
        ch = info.desc().child("channels").child("channel")
        for _ in range(info.channel_count()):
            label = _child_text(ch, "label") or _child_text(ch, "name")
            if label:
                labels.append(label)
            ch = ch.next_sibling()
    except Exception:
        pass
    return labels


def _is_eeg_candidate(info: Any) -> bool:
    try:
        stype = (info.type() or "").lower()
        name = (info.name() or "").lower()
        return "eeg" in stype or "eeg" in name or "emotiv" in name or "insight" in name
    except Exception:
        return False


def scan_eeg_streams(timeout: float = 1.5, pull_sample: bool = True) -> Dict[str, Any]:
    """Discover EEG-like LSL streams and perform a non-invasive sample check.

    This does not record data and does not modify any stream. LabRecorder remains
    responsible for XDF recording. This function is only for acquisition preflight.
    """
    if not eeg_lsl_available():
        return {
            "available": False,
            "lsl_clock": None,
            "streams": [],
            "summary": {"total_eeg_candidates": 0, "insight_like_streams": 0, "valid_streams": 0},
            "error": "pylsl/liblsl is not available. Install pylsl and make sure liblsl is accessible.",
        }

    found: List[EEGStreamCheck] = []
    try:
        infos = resolve_streams(wait_time=timeout)
    except Exception as exc:
        return {
            "available": True,
            "lsl_clock": float(local_clock()) if local_clock else None,
            "streams": [],
            "summary": {"total_eeg_candidates": 0, "insight_like_streams": 0, "valid_streams": 0},
            "error": str(exc),
        }

    for info in infos:
        if not _is_eeg_candidate(info):
            continue

        labels = _channel_labels(info)
        label_set = set(labels)
        warnings: List[str] = []
        sample_available = False
        sample_ts: Optional[float] = None
        sample_len: Optional[int] = None

        name = info.name() or ""
        stype = info.type() or ""
        source_id = info.source_id() or ""
        hostname = info.hostname() or ""
        channel_count = int(info.channel_count())
        nominal_srate = float(info.nominal_srate())
        channel_format = str(info.channel_format())
        created_at_lsl = float(info.created_at())

        likely_insight = (
            channel_count == 5
            and (not labels or EXPECTED_INSIGHT_CHANNELS.issubset(label_set))
            and 120 <= nominal_srate <= 130
        ) or ("insight" in name.lower()) or ("emotiv" in name.lower() and channel_count == 5)

        if channel_count != 5:
            warnings.append(f"Expected 5 Insight EEG channels, found {channel_count}.")
        if nominal_srate and not (120 <= nominal_srate <= 130):
            warnings.append(f"Expected approximately 128 Hz, found {nominal_srate} Hz.")
        if labels and not EXPECTED_INSIGHT_CHANNELS.issubset(label_set):
            warnings.append(f"Expected channel labels {sorted(EXPECTED_INSIGHT_CHANNELS)}, found {labels}.")

        if pull_sample:
            try:
                inlet = StreamInlet(info, max_buflen=2, recover=True)
                sample, ts = inlet.pull_sample(timeout=0.35)
                if sample is not None:
                    sample_available = True
                    sample_ts = float(ts)
                    sample_len = len(sample)
                    if sample_len != channel_count:
                        warnings.append(f"Sample length {sample_len} does not match channel count {channel_count}.")
            except Exception as exc:
                warnings.append(f"Sample pull failed: {exc}")

        if likely_insight and sample_available and not warnings:
            validation_status = "valid_insight_eeg"
        elif likely_insight and sample_available:
            validation_status = "insight_eeg_with_warnings"
        elif likely_insight:
            validation_status = "insight_eeg_no_sample"
        elif sample_available:
            validation_status = "eeg_candidate_sample_available"
        else:
            validation_status = "eeg_candidate_no_sample"

        found.append(EEGStreamCheck(
            name=name,
            type=stype,
            source_id=source_id,
            hostname=hostname,
            channel_count=channel_count,
            nominal_srate=nominal_srate,
            channel_format=channel_format,
            created_at_lsl=created_at_lsl,
            channel_labels=labels,
            likely_emotiv_insight=likely_insight,
            sample_available=sample_available,
            sample_timestamp_lsl=sample_ts,
            sample_length=sample_len,
            validation_status=validation_status,
            warnings=warnings,
        ))

    valid = [s for s in found if s.validation_status in {"valid_insight_eeg", "insight_eeg_with_warnings"}]
    return {
        "available": True,
        "lsl_clock": float(local_clock()),
        "streams": [s.dict() for s in found],
        "summary": {
            "total_eeg_candidates": len(found),
            "insight_like_streams": sum(1 for s in found if s.likely_emotiv_insight),
            "valid_streams": len(valid),
        },
        "error": None,
    }
