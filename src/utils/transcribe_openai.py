"""
Simple transcription helper using OpenAI Audio (Whisper-like) API.
Writes audio bytes to a temp file and calls the API to transcribe.
Set OPENAI_API_KEY in environment.
Adjust model name to the transcription model you have access to.
"""
import os
import tempfile
import openai

def transcribe_audio_bytes(audio_bytes: bytes, model: str = "whisper-1"):
    """
    Transcribe audio bytes. Default model "whisper-1" is used as an example.
    Returns transcription string ('' on error).
    """
    api_key = os.environ.get("OPENAI_API_KEY") or None
    if api_key:
        openai.api_key = api_key

    # write bytes to temp file
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    try:
        tf.write(audio_bytes)
        tf.flush()
        tf.close()
        # call OpenAI's audio transcription endpoint
        # Some openai client versions support openai.Audio.transcribe or openai.Audio.create
        try:
            resp = openai.Audio.transcribe(model=model, file=open(tf.name, "rb"))
            # resp may be dict-like; try common keys
            if isinstance(resp, dict):
                return resp.get("text", "") or str(resp)
            # sometimes resp is string
            return str(resp)
        except Exception:
            # fallback to older style
            try:
                resp = openai.Whisper.create(model=model, file=open(tf.name, "rb"))
                if isinstance(resp, dict):
                    return resp.get("text", "") or str(resp)
                return str(resp)
            except Exception as e:
                return ""
    finally:
        try:
            os.unlink(tf.name)
        except Exception:
            pass
    return ""
