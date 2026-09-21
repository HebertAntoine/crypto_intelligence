"""🎙️ Listening to a video the member is watching.

The member plays the video normally, on the official platform. The app
listens the way a person taking notes would: through the phone's or the
computer's microphone, or the audio of the browser tab they choose to share.
Nothing is downloaded, no protection is bypassed, no login is automated.

    audio chunks (every ~15 s) -> Whisper, locally on this machine's GPU
    -> timestamped transcript -> the LOT 3 chain (extraction + verification)
    -> reports -> plans (automatically once the member has validated a first
       test, otherwise waiting for their check)

Audio is never kept: each chunk is deleted as soon as it is transcribed. The
transcript stays in data/lexa/ (0600, ignored by Git), like every Lexa file.
"""

from __future__ import annotations

import gc
import json
import os
import queue
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..logging_setup import get_logger
from .store import database_path
from .transcript import Segment, render

log = get_logger(__name__)

WHISPER_MODEL = os.environ.get("LEXA_WHISPER_MODEL", "large-v3-turbo")
MAX_CHUNK_BYTES = 25 * 1024 * 1024
MAX_SESSION_SECONDS = 3 * 3600

#: Whisper's well-known inventions on silence or music: never Lexa's words.
HALLUCINATIONS = re.compile(
    r"(sous-titr|sous titr|radio-canada|amara\.org|merci d'avoir regardé|abonnez-vous|"
    r"n'oubliez pas de vous abonner|♪)", re.I)


def normalise_numbers(text: str) -> tuple[str, bool]:
    """« 0,5 120 » -> « 0,5120 »: Whisper splits long decimals into groups.

    Only a decimal directly followed by a group of exactly three digits is
    joined. Returns whether anything was joined, so the passage is flagged.
    """

    joined = re.sub(r"(\d+,\d+) (\d{3})(?![\d,])", r"\1\2", text)
    return joined, joined != text


def listen_dir() -> Path:
    path = database_path().parent / "listen"
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


# --- the model ------------------------------------------------------------------------

_MODEL = None
_MODEL_LOCK = threading.Lock()


def _cuda_paths() -> None:
    """ctranslate2 needs cuBLAS / cuDNN; they ship as pip wheels in the venv."""

    try:
        import nvidia  # type: ignore[import-not-found]

        base = Path(nvidia.__path__[0])
        extra = [str(base / "cublas" / "lib"), str(base / "cudnn" / "lib")]
        current = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = ":".join(extra + ([current] if current else []))
        import ctypes

        for lib in ("libcublas.so.12", "libcublasLt.so.12"):
            ctypes.CDLL(str(base / "cublas" / "lib" / lib), mode=ctypes.RTLD_GLOBAL)
        for name in sorted((base / "cudnn" / "lib").glob("libcudnn*.so.9")):
            ctypes.CDLL(str(name), mode=ctypes.RTLD_GLOBAL)
    except Exception as exc:  # CPU fallback below
        log.info("lexa_whisper_no_cuda_libs", error=str(exc))


def model():
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            from faster_whisper import WhisperModel

            _cuda_paths()
            try:
                _MODEL = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="int8_float16")
            except Exception as exc:
                log.warning("lexa_whisper_cpu_fallback", error=str(exc))
                _MODEL = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        return _MODEL


def release_model() -> None:
    """Free the GPU before the local LLM reads the transcript."""

    global _MODEL
    with _MODEL_LOCK:
        _MODEL = None
    gc.collect()


def transcribe_file(path: Path, offset_s: float, transcribe=None) -> tuple[list[dict], float]:
    """Segments of one audio file, shifted by where it sits in the video."""

    if transcribe is None:
        def transcribe(p):
            segments, info = model().transcribe(str(p), language="fr", vad_filter=True,
                                                condition_on_previous_text=False)
            return [(s.start, s.text) for s in segments], info.duration
    raw, duration = transcribe(path)
    out = []
    for start, text in raw:
        text = text.strip()
        if not text or HALLUCINATIONS.search(text):
            continue
        text, joined = normalise_numbers(text)
        out.append({"start_s": int(offset_s + start), "text": text, "joined_numbers": joined})
    return out, float(duration or 0)


# --- sessions ---------------------------------------------------------------------------


class Session:
    """One video being listened to. Chunks are transcribed in order, one at a time."""

    def __init__(self, sid: str) -> None:
        self.sid = sid
        self.path = listen_dir() / sid
        self.queue: queue.Queue[tuple[int, Path] | None] = queue.Queue()
        self.worker = threading.Thread(target=self._work, name=f"lexa-listen-{sid}", daemon=True)
        # The request thread and the worker both update the state.
        self.lock = threading.RLock()

    # state on disk, so a restart never loses a transcript
    def state(self) -> dict[str, Any]:
        with self.lock:
            return json.loads((self.path / "state.json").read_text())

    def save(self, **fields: Any) -> None:
        with self.lock:
            current = self.state() if (self.path / "state.json").exists() else {}
            current.update(fields)
            target = self.path / "state.json"
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(current, ensure_ascii=False, indent=1))
            os.chmod(temp, 0o600)
            temp.replace(target)

    def segments(self) -> list[dict]:
        file = self.path / "segments.jsonl"
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text().splitlines() if line.strip()]

    def _append(self, segments: list[dict]) -> None:
        file = self.path / "segments.jsonl"
        with file.open("a", encoding="utf-8") as handle:
            for seg in segments:
                handle.write(json.dumps(seg, ensure_ascii=False) + "\n")
        os.chmod(file, 0o600)

    def _work(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                break
            index, audio = item
            try:
                segments, duration = transcribe_file(audio, self.state()["audio_seconds"])
                self._append(segments)
                with self.lock:
                    state = self.state()
                    self.save(audio_seconds=state["audio_seconds"] + duration,
                              chunks_done=state["chunks_done"] + 1)
            except Exception as exc:
                log.warning("lexa_chunk_failed", session=self.sid, chunk=index, error=str(exc))
                self.save(errors=[*self.state().get("errors", []), f"Morceau {index} : {exc}"])
            finally:
                audio.unlink(missing_ok=True)  # the audio itself is never kept
        self._finish()

    def _finish(self) -> None:
        from . import test_run

        state = self.state()
        segments = [Segment(s["start_s"], s["text"]) for s in self.segments()]
        release_model()
        if not segments:
            self.save(state="FAILED", error="Aucune parole reconnue : rien n'a été analysé.")
            return
        joined = [s for s in self.segments() if s.get("joined_numbers")]
        self.save(state="ANALYSING", uncertain_numbers=len(joined))
        try:
            run_id = test_run.start(render(segments), title=state["title"],
                                    published_at=state.get("published_at"),
                                    source="Écoute de la vidéo (micro ou onglet), transcrite localement",
                                    background=False)
        except ValueError as exc:
            self.save(state="FAILED", error=str(exc))
            return
        run = test_run.get(run_id) or {}
        self.save(run_id=run_id)
        if (run.get("status") or {}).get("state") != "DONE":
            self.save(state="FAILED", error=(run.get("status") or {}).get("error", "Analyse échouée."))
            return
        if auto_import_enabled() and state.get("published_at"):
            try:
                video_id = test_run.import_run(run_id)
                self.save(state="IMPORTED", video_id=video_id)
                return
            except ValueError as exc:
                self.save(import_error=str(exc))
        self.save(state="TO_VALIDATE")


_SESSIONS: dict[str, Session] = {}


def start(*, title: str, published_at: str | None, video_url: str = "") -> str:
    sid = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    session = Session(sid)
    session.path.mkdir(mode=0o700)
    session.save(session_id=sid, state="LISTENING", title=title.strip() or "Vidéo Lexa",
                 published_at=published_at, video_url=video_url, started_at=time.time(),
                 chunks_received=0, chunks_done=0, audio_seconds=0.0, errors=[])
    session.worker.start()
    _SESSIONS[sid] = session
    return sid


def _session(sid: str) -> Session:
    if not re.fullmatch(r"\d{8}T\d{6}Z", sid) or sid not in _SESSIONS:
        raise ValueError("Écoute introuvable (ou le serveur a redémarré).")
    return _SESSIONS[sid]


def add_chunk(sid: str, data: bytes, mime: str = "") -> int:
    session = _session(sid)
    state = session.state()
    if state["state"] != "LISTENING":
        raise ValueError("Cette écoute est terminée.")
    if not data:
        return state["chunks_received"]
    if len(data) > MAX_CHUNK_BYTES:
        raise ValueError("Morceau audio trop gros (25 Mo maximum).")
    if state["audio_seconds"] > MAX_SESSION_SECONDS:
        raise ValueError("Écoute trop longue (3 h maximum).")
    with session.lock:
        index = session.state()["chunks_received"] + 1
        session.save(chunks_received=index)
    suffix = ".mp4" if "mp4" in mime or "aac" in mime else ".webm" if "webm" in mime else \
        ".ogg" if "ogg" in mime else ".mp3" if "mpeg" in mime else ".wav" if "wav" in mime else ".audio"
    audio = session.path / f"chunk-{index:05d}{suffix}"
    audio.write_bytes(data)
    os.chmod(audio, 0o600)
    session.queue.put((index, audio))
    return index


def finish(sid: str) -> None:
    session = _session(sid)
    if session.state()["state"] == "LISTENING":
        session.save(state="TRANSCRIBING")
        session.queue.put(None)


def status(sid: str) -> dict[str, Any]:
    session = _session(sid)
    state = session.state()
    segs = session.segments()
    return {**state, "segments": len(segs),
            "preview": [{"start_s": s["start_s"], "text": s["text"]} for s in segs[-8:]]}


# --- automatic import, earned by one validated test --------------------------------------

def _setting(key: str) -> str | None:
    from .store import LexaSettingRow, lexa_session

    with lexa_session() as s:
        row = s.get(LexaSettingRow, key)
        return row.value if row else None


def auto_import_enabled() -> bool:
    return _setting("auto_import") == "1"


def validated_once() -> bool:
    from . import test_run

    return any(r.get("imported_video_id") for r in test_run.list_runs())


def set_auto_import(enabled: bool) -> bool:
    """Automatic import is only allowed after one run was checked and imported by hand."""

    from .store import LexaSettingRow, lexa_session

    if enabled and not validated_once():
        raise ValueError("Valide d'abord un premier test à la main (rapport vérifié puis "
                         "« Importer ») : l'import automatique s'active ensuite.")
    with lexa_session() as s:
        row = s.get(LexaSettingRow, "auto_import")
        if row is None:
            s.add(LexaSettingRow(key="auto_import", value="1" if enabled else "0"))
        else:
            row.value = "1" if enabled else "0"
    return enabled
