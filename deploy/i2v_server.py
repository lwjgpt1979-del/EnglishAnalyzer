"""自托管文生视频服务(词力通动图)——跑在租的 GPU 机(推荐 48G 单卡)。

文生视频(T2V):不喂原图,纯靠文字描述生成动画(prompt 要完整描述"主体+场景+动作+风格")。

契约:
  POST /t2v   body: {"prompt": "...", "steps": 40, "guidance_scale": 4.0}
              header: Authorization: Bearer <I2V_TOKEN>
              返回: video/mp4 文件字节。多余字段(如 image_url)会被忽略。
  GET  /health -> {"ok": true, "model": ...}

默认 Wan2.2-TI2V-5B(48G 轻松、~1-3 分钟/条,质量强)。
  切最强档(慢):export I2V_MODEL=Wan-AI/Wan2.2-T2V-A14B-Diffusers

依赖(全新实例装最新版,别锁旧版——Wan2.2 需要新 diffusers + 新 torch;全 latest 互相兼容):
  M=https://pypi.tuna.tsinghua.edu.cn/simple
  pip install -U torch torchvision torchaudio -i $M
  pip install -U diffusers transformers accelerate ftfy -i $M
  pip install -U imageio imageio-ffmpeg pillow httpx fastapi "uvicorn[standard]" -i $M

起服务(HF_ENDPOINT 必设):
  export HF_ENDPOINT=https://hf-mirror.com
  I2V_TOKEN=<长随机串> uvicorn i2v_server:app --host 0.0.0.0 --port 6006
"""
from __future__ import annotations

import os
import uuid

import torch
from diffusers import AutoencoderKLWan, WanPipeline
from diffusers.utils import export_to_video
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

TOKEN = os.environ.get("I2V_TOKEN", "")  # 公网暴露必设;空则不校验
_MODEL = os.environ.get("I2V_MODEL", "Wan-AI/Wan2.2-TI2V-5B-Diffusers")
_IS_A14B = "a14b" in _MODEL.lower()

# 模型只在启动时加载一次。VAE 用 float32(Wan 官方推荐,数值更稳)。
vae = AutoencoderKLWan.from_pretrained(_MODEL, subfolder="vae", torch_dtype=torch.float32)
pipe = WanPipeline.from_pretrained(_MODEL, vae=vae, torch_dtype=torch.bfloat16)
if _IS_A14B:
    pipe.enable_model_cpu_offload()   # 27B 总参 > 48G,必须 offload(慢)
else:
    pipe.to("cuda")                    # 5B 在 48G 全速

# 生成规格按模型(官方推荐值)
if _IS_A14B:
    _H, _W, _FRAMES, _FPS = 720, 1280, 81, 16
else:  # TI2V-5B
    _H, _W, _FRAMES, _FPS = 704, 1280, 121, 24

app = FastAPI(title="engGramer Wan2.2 T2V")

_NEG = ("blurry, distorted, deformed, morphing, warping, ghosting, extra limbs, "
        "duplicated subject, low quality, worst quality, artifacts, text, watermark, "
        "static still image, cluttered background")


class Req(BaseModel):
    prompt: str
    steps: int = 40
    guidance_scale: float = 4.0
    num_frames: int | None = None   # 不填=模型默认(5B:121≈5s);控时长自定,须 4k+1(24fps:3s≈73)
    model_config = {"extra": "ignore"}   # 后端可能带 image_url 等多余字段,忽略


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": _MODEL, "a14b": _IS_A14B, "size": f"{_W}x{_H}", "frames": _FRAMES}


@app.post("/t2v")
def t2v(r: Req, authorization: str = Header("")) -> FileResponse:
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="bad token")
    prompt = f"{r.prompt}. Single clear consistent subject, smooth natural motion, static fixed camera."
    nf = r.num_frames or _FRAMES
    nf = max(5, ((nf - 1) // 4) * 4 + 1)   # Wan 要求 4k+1,自动向下对齐
    kw = dict(prompt=prompt, negative_prompt=_NEG, height=_H, width=_W,
              num_frames=nf, num_inference_steps=r.steps, guidance_scale=r.guidance_scale)
    if _IS_A14B:
        kw["guidance_scale_2"] = 3.0   # A14B 是双专家 MoE,低噪声阶段单独的引导系数
    frames = pipe(**kw).frames[0]
    path = f"/tmp/{uuid.uuid4().hex}.mp4"
    export_to_video(frames, path, fps=_FPS)
    return FileResponse(path, media_type="video/mp4", filename="t2v.mp4")
