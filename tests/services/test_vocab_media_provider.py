"""词力通图/音频 provider 测试（P1 / D-101）。"""
from app.services import vocab_media_provider as p


def test_image_dev_mode_default():
    assert p.is_image_dev_mode() is True   # 默认 placeholder


def test_tts_dev_mode_default():
    assert p.is_tts_dev_mode() is True


def test_generate_images_devmock_count_and_determinism():
    urls = p.generate_images("confident", n=3)
    assert len(urls) == 3
    assert all(isinstance(u, str) and u.startswith("http") for u in urls)
    assert urls == p.generate_images("confident", n=3)  # 确定性


def test_generate_images_respects_n():
    assert len(p.generate_images("x", n=1)) == 1
    assert len(p.generate_images("x", n=5)) == 5


def test_generate_tts_devmock():
    u = p.generate_tts("hello world")
    assert isinstance(u, str) and u.startswith("http")
    assert u == p.generate_tts("hello world")  # 确定性
