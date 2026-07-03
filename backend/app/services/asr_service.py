"""电销通话录音 → 文本(腾讯云「录音文件识别」,说话人分离=客户/座席分轨)。

dev-mock:未配腾讯云密钥(settings.cos_secret_id 仍是 placeholder)时返回占位转写,
链路可离线测;配了真密钥即走腾讯 ASR。腾讯云 SecretId/Key 是账号级,复用 COS 那对。

注意:录音文件识别是**异步任务**(创建→轮询),真实转写要数十秒。生产应放后台任务里跑,
不要卡在 webhook 上;本模块 transcribe() 同步返回,调用方自行决定是否后台化。
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

_log = logging.getLogger(__name__)
_REGION = settings.cos_region or "ap-guangzhou"


def is_dev_mock() -> bool:
    """未配真腾讯云密钥、或未装 asr SDK 子包 → dev-mock(占位转写,不真调)。"""
    if settings.cos_secret_id.startswith("placeholder"):
        return True
    try:
        import tencentcloud.asr  # noqa: F401 — 需 pip install tencentcloud-sdk-python-asr
        return False
    except ImportError:
        return True


def _mock_transcribe(recording_url: str) -> str:
    return ("【dev-mock 转写】客户:你们这个课程多少钱?能支持中考冲刺吗?我们再考虑一下怎么合作。 "
            "座席:好的,我把课程详情和中考冲刺模块发您,方便加个微信吗?")


def _tencent_transcribe_sync(recording_url: str, *, poll_max: int = 60, poll_sleep: float = 3.0) -> str:
    """腾讯云录音文件识别:CreateRecTask(说话人分离)→ 轮询 DescribeTaskStatus → 文本。"""
    import time
    from tencentcloud.common import credential
    from tencentcloud.asr.v20190614 import asr_client, models

    cred = credential.Credential(settings.cos_secret_id, settings.cos_secret_key)
    client = asr_client.AsrClient(cred, _REGION)

    req = models.CreateRecTaskRequest()
    req.EngineModelType = "16k_zh"      # 16k 中文通用(纯电话 8k 录音可换 "8k_zh")
    req.ChannelNum = 1
    req.ResTextFormat = 0
    req.SourceType = 0                  # 0=音频 URL
    req.Url = recording_url
    req.SpeakerDiarization = 1          # 说话人分离(客户/座席分轨)
    req.SpeakerNumber = 2
    task_id = client.CreateRecTask(req).Data.TaskId

    status_req = models.DescribeTaskStatusRequest()
    status_req.TaskId = task_id
    for _ in range(poll_max):
        time.sleep(poll_sleep)
        data = client.DescribeTaskStatus(status_req).Data
        if data.Status == 2:            # 2=成功
            return data.Result or ""
        if data.Status == 3:            # 3=失败
            raise RuntimeError(data.ErrorMsg or "ASR 识别失败")
    raise TimeoutError("ASR 轮询超时")


def _clean(raw: str) -> str:
    """去掉腾讯返回的 [说话人:起,说话人:止,序号] 时间戳标记,按说话人分行标注客户/座席。

    格式如 `[0:0.130,0:1.430,0]  文本`。首个出现的说话人当「客户」(通常被叫先说),另一个「座席」。
    """
    import re
    lines, spk_label = [], {}
    for ln in (raw or "").splitlines():
        m = re.match(r"\s*\[(\d+):[^\]]*\]\s*(.*)", ln)
        if m:
            spk, txt = m.group(1), m.group(2).strip()
            if spk not in spk_label:
                spk_label[spk] = "客户" if len(spk_label) == 0 else "座席"
            if txt:
                lines.append(f"{spk_label[spk]}:{txt}")
        else:
            t = ln.strip()
            if t:
                lines.append(t)
    return "\n".join(lines)


async def transcribe(recording_url: str, *, source: str = "call") -> str:
    """录音 URL → 转写文本(去时间戳、按说话人标注)。dev-mock 或失败 → 占位文本(不阻断链路)。"""
    if not (recording_url or "").strip():
        return ""
    if is_dev_mock():
        return _mock_transcribe(recording_url)
    try:
        raw = await asyncio.to_thread(_tencent_transcribe_sync, recording_url)
        return _clean(raw) or raw
    except Exception as exc:  # noqa: BLE001
        _log.warning("腾讯 ASR 失败,退回占位转写: %s", exc)
        return _mock_transcribe(recording_url)
