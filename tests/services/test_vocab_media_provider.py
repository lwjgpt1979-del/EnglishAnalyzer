"""词力通图/音频 provider 测试（P1 / D-101）。"""
import pytest

from app.services import vocab_media_provider as p


def test_image_dev_mode_default():
    assert p.is_image_dev_mode() is True   # 默认 placeholder


def test_tts_dev_mode_default():
    assert p.is_tts_dev_mode() is True


@pytest.mark.asyncio
async def test_t2i_devmock_placeholder_and_deterministic():
    # 图片入口已是 async t2i_to_cos(prompt, label=)，dev-mock 返回 placehold 占位
    u = await p.t2i_to_cos("a confident person", label="confident")
    assert isinstance(u, str) and u.startswith("https://placehold.co")
    assert u == await p.t2i_to_cos("a confident person", label="confident")  # 同prompt确定性


@pytest.mark.asyncio
async def test_t2i_devmock_distinct_prompts_distinct_urls():
    u1 = await p.t2i_to_cos("apple on a table", label="apple")
    u2 = await p.t2i_to_cos("a running dog", label="dog")
    assert u1 != u2  # 不同 prompt → 不同占位URL（按 prompt 哈希）


def test_generate_tts_devmock_returns_empty():
    # 397df9b：mock 不再写假音频URL（卡片发音走 tts_service 兜底），故返回空串
    assert p.generate_tts("hello world") == ""
