"""
Azure Speech boundary. Recorded audio in, one string out — the same string the chat box
produces, so nothing downstream knows a question was spoken (D35).

The short-audio REST endpoint is a single POST, so it is written here rather than pulling in
the Speech SDK for one call.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from app.config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, SPEECH_LANGUAGE

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_HOST = "https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"

# Regional form, so the resource needs no custom subdomain configured.
_TOKEN_HOST = "https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"

# The only two the REST API for short audio decodes. Anything else is accepted and answered
# with an empty transcript, indistinguishable from silence, so it is refused here instead.
ACCEPTED = ("audio/wav", "audio/ogg")


def transcribe(audio: bytes, content_type: str) -> str:
    """The words in `audio`, or "" when the service heard none.

    `content_type` must be one the service decodes — WAV/PCM 16 kHz mono or OGG/OPUS. Raises
    ValueError otherwise, and RuntimeError when the resource is unconfigured or rejects the
    call, so the route answers with a status rather than a transcript to distrust.
    """
    if not (AZURE_SPEECH_KEY and AZURE_SPEECH_REGION):
        raise RuntimeError("Missing in backend/.env: AZURE_SPEECH_KEY, AZURE_SPEECH_REGION")
    if not content_type.startswith(ACCEPTED):
        raise ValueError(f"Unsupported audio format: {content_type or 'none given'}")

    url = _HOST.format(region=AZURE_SPEECH_REGION) + "?" + urllib.parse.urlencode(
        {"language": SPEECH_LANGUAGE, "format": "simple", "profanity": "raw"}
    )
    request = urllib.request.Request(
        url,
        data=audio,
        headers={
            "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
            "Content-Type": content_type,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Speech service returned {error.code}") from error
    except OSError as error:
        raise RuntimeError("Speech service unreachable") from error

    # Measured: this endpoint answers 200 "Success" with an empty DisplayText for silence,
    # for an unsupported codec and for bytes that are not audio at all. So "" means only
    # "nothing was heard" and the caller cannot tell those three apart (D35).
    text = body.get("DisplayText", "") if body.get("RecognitionStatus") == "Success" else ""
    if not text:
        # Duration is the only signal that separates the two: audio it could not decode
        # comes back a few hundred thousand ticks long whatever was recorded.
        logger.info(
            "no transcript: %s bytes of %s, service reported %s", len(audio), content_type, body
        )
    return text


def issue_token() -> tuple[str, str]:
    """A ten-minute token for the browser, and the region it is scoped to.

    The subscription key never leaves the backend; the streaming recogniser authenticates
    with this instead (D36).
    """
    if not (AZURE_SPEECH_KEY and AZURE_SPEECH_REGION):
        raise RuntimeError("Missing in backend/.env: AZURE_SPEECH_KEY, AZURE_SPEECH_REGION")

    request = urllib.request.Request(
        _TOKEN_HOST.format(region=AZURE_SPEECH_REGION),
        data=b"",
        headers={"Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY, "Content-Length": "0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return response.read().decode(), AZURE_SPEECH_REGION
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Token endpoint returned {error.code}") from error
    except OSError as error:
        raise RuntimeError("Token endpoint unreachable") from error
