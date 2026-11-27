import io
from urllib.error import HTTPError

import pytest

from genesis_core import model_hub as hub


class FakeResponse(io.BytesIO):
    def __init__(self, data, status=200, length=None):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Length": str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


MODEL = hub.CATALOG[0]
GGUF = b"GGUF" + b"x" * 5000


def test_recommend_scales_with_ram():
    assert hub.recommend(None) is hub.CATALOG[0]
    assert hub.recommend(2 * hub.GB).key == "qwen2.5-0.5b"
    assert hub.recommend(4 * hub.GB).key == "qwen2.5-1.5b"
    assert hub.recommend(16 * hub.GB).key == "qwen2.5-7b"


def test_resolve_spec():
    assert hub.resolve_spec("1") is hub.CATALOG[0]
    assert hub.resolve_spec("QWEN2.5-3B").key == "qwen2.5-3b"
    custom = hub.resolve_spec("hf:me/repo/sub/model-q4.gguf")
    assert custom.repo == "me/repo" and custom.filename == "sub/model-q4.gguf"
    for bad in ("99", "nope", "hf:me/repo/model.bin", "hf:me/repo/../x.gguf", "hf:bad repo/x/y.gguf"):
        with pytest.raises(hub.HubError):
            hub.resolve_spec(bad)


def test_download_success_and_progress(tmp_path):
    seen = []
    path = hub.download(MODEL, tmp_path, progress=lambda d, t: seen.append((d, t)),
                        opener=lambda req, timeout: FakeResponse(GGUF))
    assert path.read_bytes() == GGUF and not list(tmp_path.glob("*.part"))
    assert seen[-1] == (len(GGUF), len(GGUF))
    # already installed -> no network
    assert hub.download(MODEL, tmp_path, opener=lambda *a, **k: 1 / 0) == path
    assert hub.installed_models(tmp_path) == [path]


def test_download_resumes_partial(tmp_path):
    part = tmp_path / (MODEL.filename + ".part")
    part.write_bytes(GGUF[:1000])
    requests = []

    def opener(req, timeout):
        requests.append(req.headers.get("Range"))
        return FakeResponse(GGUF[1000:], status=206)

    path = hub.download(MODEL, tmp_path, opener=opener)
    assert requests == ["bytes=1000-"] and path.read_bytes() == GGUF


def test_download_rejects_incomplete_non_gguf_and_http_errors(tmp_path):
    with pytest.raises(hub.HubError, match="incomplete"):
        hub.download(MODEL, tmp_path, opener=lambda r, timeout: FakeResponse(GGUF[:100], length=len(GGUF)))
    # partial stays for resume
    assert list(tmp_path.glob("*.part"))
    other = tmp_path / "b"
    with pytest.raises(hub.HubError, match="not a GGUF"):
        hub.download(MODEL, other, opener=lambda r, timeout: FakeResponse(b"<html>" + b"x" * 50))
    assert not list(other.glob("*.part")) and not list(other.glob("*.gguf"))

    def raiser(code):
        def _open(req, timeout):
            raise HTTPError(req.full_url, code, "err", {}, None)
        return _open

    with pytest.raises(hub.HubError, match="not found"):
        hub.download(MODEL, tmp_path / "c", opener=raiser(404))
    with pytest.raises(hub.HubError, match="login"):
        hub.download(MODEL, tmp_path / "d", opener=raiser(401))


def test_download_only_from_huggingface():
    assert MODEL.url.startswith("https://huggingface.co/")
    with pytest.raises(hub.HubError, match="huggingface.co"):
        hub._check_url("https://evil.example/model.gguf")
    with pytest.raises(hub.HubError):
        hub._check_url("http://huggingface.co/x")


def test_download_refuses_when_disk_is_full(tmp_path, monkeypatch):
    class Usage:
        free = 10

    monkeypatch.setattr(hub.shutil, "disk_usage", lambda p: Usage)
    with pytest.raises(hub.HubError, match="disk space"):
        hub.download(MODEL, tmp_path, opener=lambda r, timeout: FakeResponse(GGUF))


def test_progress_bar_text():
    text = hub.progress_bar(50, 100, 0.0)
    assert "50.0%" in text and "█" in text
