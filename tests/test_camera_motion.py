import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
import homeassistant.components.camera as ha_camera
from custom_components.album_slideshow import camera, image_processing as ip


def test_live_camera_motion_toggle_pause_navigation_and_disconnect(monkeypatch):
    cam = object.__new__(camera.AlbumSlideshowCamera)
    cam.entry = SimpleNamespace(entry_id="album")
    unsubscribe = Mock()
    cam._viewers = SimpleNamespace(async_add_stream=lambda entry_id: unsubscribe)
    cam.store = SimpleNamespace(ken_burns=False, paused=False, slide_interval=10)
    cam.frame_interval = 0.5
    cam.content_type = "image/jpeg"
    cam._last_video = None
    cam._current_frame = object()
    cam._frame_id = 1
    cam._motion_viewers = 0
    cam._motion_lock = asyncio.Lock()
    cam._clear_motion()
    with Image.linear_gradient("L").resize((1600, 900)).convert("RGB") as photo:
        cam._framebuffer = ip.encode_image(photo)
    decoded = Mock(wraps=ip.motion_source)
    monkeypatch.setattr(ip, "motion_source", decoded)

    async def run_job(func, *args):
        return func(*args)

    cam.hass = SimpleNamespace(async_add_executor_job=run_job)
    now = 100.0
    monkeypatch.setattr(camera, "time", SimpleNamespace(monotonic=lambda: now))

    async def stream(request, fetch, mime, interval):
        nonlocal now
        assert await fetch() is cam._framebuffer
        now += 1
        cam.store.ken_burns = True
        start = await fetch()
        now += 4
        moving = await fetch()
        assert moving != start
        with Image.open(BytesIO(moving)) as image:
            assert image.size == (1280, 720)
            assert image.format == "JPEG"
        assert await cam.async_camera_image() is cam._framebuffer
        assert decoded.call_count == 1
        cam.store.paused = True
        now += 1
        assert await fetch() == moving
        cam._frame_id += 1
        now += 1
        assert await fetch() != moving
        assert decoded.call_count == 2
        cam.store.ken_burns = False
        now += 1
        assert await fetch() is cam._framebuffer
        return "closed"

    monkeypatch.setattr(ha_camera, "async_get_still_stream", stream, raising=False)
    assert asyncio.run(cam.handle_async_mjpeg_stream(None)) == "closed"
    unsubscribe.assert_called_once()
    assert cam._motion_viewers == 0
    assert cam._motion_source is None
