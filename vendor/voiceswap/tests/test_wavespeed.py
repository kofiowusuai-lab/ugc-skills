import pytest

from voiceswap.wavespeed import (
    WaveSpeedClient,
    parse_submit,
    parse_result,
    WaveSpeedError,
)


class FakeResp:
    def __init__(self, payload, status_code=200, content=b""):
        self._payload = payload
        self.status_code = status_code
        self.content = content

    def json(self):
        return self._payload


# ---- response parsing -------------------------------------------------------

def test_parse_submit_reads_id_and_poll_url():
    payload = {"code": 200, "data": {
        "id": "task-1",
        "status": "pending",
        "urls": {"get": "https://api.wavespeed.ai/api/v3/predictions/task-1/result"},
    }}
    task_id, poll_url = parse_submit(payload)
    assert task_id == "task-1"
    assert poll_url.endswith("/predictions/task-1/result")


def test_parse_result_completed_with_outputs_array():
    payload = {"data": {"status": "completed",
                        "outputs": ["https://cdn/out.mp4"]}}
    status, url, err = parse_result(payload)
    assert status == "completed"
    assert url == "https://cdn/out.mp4"
    assert err is None


def test_parse_result_completed_with_single_output():
    payload = {"data": {"status": "completed", "output": "https://cdn/o.mp4"}}
    status, url, err = parse_result(payload)
    assert status == "completed" and url == "https://cdn/o.mp4"


def test_parse_result_pending_has_no_url():
    status, url, err = parse_result({"data": {"status": "processing"}})
    assert status == "processing" and url is None


def test_parse_result_failed_surfaces_error():
    payload = {"data": {"status": "failed", "error": "bad input"}}
    status, url, err = parse_result(payload)
    assert status == "failed" and err == "bad input"


# ---- client orchestration ---------------------------------------------------

class FakeHttp:
    """Records calls; returns queued responses by URL pattern."""

    def __init__(self):
        self.posts = []
        self.gets = []
        self._get_queue = []

    def queue_get(self, resp):
        self._get_queue.append(resp)

    def post(self, url, headers=None, data=None, json=None, files=None):
        self.posts.append({"url": url, "json": json, "data": data is not None})
        if "media/upload" in url:
            return FakeResp({"data": {"download_url": f"https://cdn/{len(self.posts)}.bin"}})
        if "lipsync" in url:
            return FakeResp({"data": {"id": "t1", "status": "pending",
                "urls": {"get": "https://api.wavespeed.ai/api/v3/predictions/t1/result"}}})
        raise AssertionError("unexpected post " + url)

    def get(self, url, headers=None):
        self.gets.append(url)
        return self._get_queue.pop(0)


def test_lipsync_uploads_submits_and_polls(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"VID")
    audio = tmp_path / "a.wav"; audio.write_bytes(b"AUD")

    http = FakeHttp()
    http.queue_get(FakeResp({"data": {"status": "processing"}}))
    http.queue_get(FakeResp({"data": {"status": "completed",
                                      "outputs": ["https://cdn/final.mp4"]}}))

    client = WaveSpeedClient(api_key="K", http=http, sleep_fn=lambda s: None)
    out = client.lipsync(str(video), str(audio), model="sync/lipsync-2")

    assert out == "https://cdn/final.mp4"
    # two uploads (video, audio) + one submit
    assert sum("media/upload" in p["url"] for p in http.posts) == 2
    submit = [p for p in http.posts if "lipsync" in p["url"]][0]
    assert submit["url"].endswith("/sync/lipsync-2")
    assert "video" in submit["json"] and "audio" in submit["json"]
    assert len(http.gets) == 2  # polled until completed


def test_lipsync_raises_on_failed_status(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"V")
    audio = tmp_path / "a.wav"; audio.write_bytes(b"A")
    http = FakeHttp()
    http.queue_get(FakeResp({"data": {"status": "failed", "error": "boom"}}))
    client = WaveSpeedClient(api_key="K", http=http, sleep_fn=lambda s: None)
    with pytest.raises(WaveSpeedError) as e:
        client.lipsync(str(video), str(audio))
    assert "boom" in str(e.value)
