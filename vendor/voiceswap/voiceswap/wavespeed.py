"""WaveSpeed AI client for lip-sync (sync.so models hosted on WaveSpeed).

Flow: upload the video and audio to get URLs, submit them to a lipsync model,
poll the prediction until it completes, return the output video URL. This is
how we re-animate the speaker's mouth to match the new ElevenLabs voice, so the
result is in sync no matter how the audio was generated.

Docs: https://wavespeed.ai/docs/get-started-api
"""
import os
import time
from typing import Callable, Optional, Tuple

BASE = "https://api.wavespeed.ai/api/v3"
UPLOAD_URL = f"{BASE}/media/upload/binary"


class WaveSpeedError(RuntimeError):
    pass


def parse_submit(payload: dict) -> Tuple[str, str]:
    data = payload.get("data", payload)
    task_id = data["id"]
    poll_url = data.get("urls", {}).get("get") or f"{BASE}/predictions/{task_id}/result"
    return task_id, poll_url


def parse_result(payload: dict) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (status, output_url_or_None, error_or_None)."""
    data = payload.get("data", payload)
    status = data.get("status")
    output = None
    outputs = data.get("outputs")
    if outputs:
        output = outputs[0]
    elif data.get("output"):
        output = data["output"]
    error = data.get("error")
    return status, output, error


class WaveSpeedClient:
    def __init__(
        self,
        api_key: str,
        http=None,
        sleep_fn: Callable[[float], None] = time.sleep,
        base: str = BASE,
    ):
        if http is None:
            import requests
            http = requests
        self.api_key = api_key
        self.http = http
        self.sleep_fn = sleep_fn
        self.base = base

    def _headers(self, json_body: bool = True) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def upload(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        url = f"{UPLOAD_URL}?ext={ext}" if ext else UPLOAD_URL
        with open(path, "rb") as fh:
            resp = self.http.post(
                url, headers=self._headers(json_body=False), data=fh.read()
            )
        payload = resp.json()
        data = payload.get("data", payload)
        url = data.get("download_url") or data.get("url")
        if not url:
            raise WaveSpeedError(f"upload returned no url: {payload}")
        return url

    def submit(self, model: str, body: dict) -> Tuple[str, str]:
        resp = self.http.post(
            f"{self.base}/{model}", headers=self._headers(), json=body
        )
        return parse_submit(resp.json())

    def poll(self, poll_url: str, interval: float = 3.0, timeout: float = 600.0) -> str:
        waited = 0.0
        while True:
            resp = self.http.get(poll_url, headers=self._headers(json_body=False))
            status, output, error = parse_result(resp.json())
            if status == "completed":
                if not output:
                    raise WaveSpeedError("completed but no output url")
                return output
            if status in ("failed", "error"):
                raise WaveSpeedError(f"lipsync failed: {error}")
            if waited >= timeout:
                raise WaveSpeedError(f"timed out after {timeout}s (status={status})")
            self.sleep_fn(interval)
            waited += interval

    def lipsync(
        self,
        video_path: str,
        audio_path: str,
        model: str = "sync/lipsync-2",
        interval: float = 3.0,
        timeout: float = 600.0,
    ) -> str:
        video_url = self.upload(video_path)
        audio_url = self.upload(audio_path)
        _, poll_url = self.submit(model, {"video": video_url, "audio": audio_url})
        return self.poll(poll_url, interval=interval, timeout=timeout)

    def download(self, url: str, out_path: str) -> str:
        resp = self.http.get(url, headers=self._headers(json_body=False))
        with open(out_path, "wb") as fh:
            fh.write(resp.content)
        return out_path


def make_client(api_key: Optional[str] = None) -> WaveSpeedClient:
    key = api_key or os.environ.get("WAVESPEED_API_KEY")
    if not key:
        raise WaveSpeedError("WAVESPEED_API_KEY not set")
    return WaveSpeedClient(api_key=key)
