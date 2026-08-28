import json
from typing import Optional, Dict, Any

try:
    from pylsl import StreamInfo, StreamOutlet, local_clock
except Exception:  # pylsl/liblsl may not be installed during early UI testing
    StreamInfo = None
    StreamOutlet = None
    local_clock = None

STREAM_NAME = "SpyGameMarkers"
STREAM_TYPE = "Markers"
SOURCE_ID = "arl_spygame_control_pc"

_outlet: Optional[object] = None
_last_error: Optional[str] = None


def lsl_available() -> bool:
    """True when pylsl imported successfully and the local LSL clock is available."""
    return StreamInfo is not None and StreamOutlet is not None and local_clock is not None


def get_outlet():
    """Create or return the single LSL marker outlet used by the acquisition app."""
    global _outlet, _last_error
    if not lsl_available():
        _last_error = "pylsl/liblsl is not available. Install pylsl and make sure liblsl is accessible."
        return None
    if _outlet is None:
        try:
            info = StreamInfo(
                name=STREAM_NAME,
                type=STREAM_TYPE,
                channel_count=1,
                nominal_srate=0,
                channel_format="string",
                source_id=SOURCE_ID,
            )
            # Add minimal metadata so the stream is self-describing in LabRecorder/XDF.
            desc = info.desc()
            desc.append_child_value("manufacturer", "ARL Spy Game Acquisition Interface")
            desc.append_child_value("content_type", "JSON event markers")
            desc.append_child_value("stream_name", STREAM_NAME)
            desc.append_child_value("source_id", SOURCE_ID)
            _outlet = StreamOutlet(info)
            _last_error = None
        except Exception as exc:  # keep UI alive even if LSL outlet creation fails
            _last_error = str(exc)
            _outlet = None
    return _outlet


def ensure_outlet() -> bool:
    """Force creation of the marker stream outlet so LabRecorder can see it before the session starts."""
    return get_outlet() is not None


def lsl_status() -> Dict[str, Any]:
    """Return diagnostic status for the moderator panel."""
    clock_value = None
    if lsl_available():
        try:
            clock_value = float(local_clock())
        except Exception:
            clock_value = None
    return {
        "available": lsl_available(),
        "outlet_created": _outlet is not None,
        "stream_name": STREAM_NAME,
        "stream_type": STREAM_TYPE,
        "source_id": SOURCE_ID,
        "local_clock": clock_value,
        "last_error": _last_error,
    }


def push_marker(marker: str, payload: dict) -> Optional[float]:
    """Push one JSON marker to LSL. Returns LSL local_clock time or None if unavailable."""
    global _last_error
    outlet = get_outlet()
    if outlet is None or not lsl_available():
        return None
    try:
        ts = float(local_clock())
        sample = {"marker": marker, "lsl_time": ts, **payload}
        outlet.push_sample([json.dumps(sample)], timestamp=ts)
        _last_error = None
        return ts
    except Exception as exc:
        _last_error = str(exc)
        return None
