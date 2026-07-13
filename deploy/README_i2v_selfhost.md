# 自托管图生视频(词力通动图)· 最终操作手册

把「现有静态配图 → 图生视频(真运动)→ 存 COS」放到租的 GPU 机上跑,后端通过 `/i2v` HTTP 服务调用。
默认模型 **LTX-Video**(轻快,4090 上一条约 30-90s)。

- 服务代码:[`deploy/i2v_server.py`](./i2v_server.py)
- 后端接入:`app/core/config.py`(`video_provider`/`selfhost_i2v_url`/`selfhost_i2v_token`)
  + `app/services/vocab_media_provider.py`(`_selfhost_i2v_to_cos`)

> ⚠️ **依赖版本必须锁定**(这是反复踩坑后的可用组合,别用 latest):
> `torch 2.4.1 / torchvision 0.19.1 / torchaudio 2.4.1`(cu121)· `diffusers 0.32.2` · `transformers 4.46.3`
> 三层版本互咬,任一层太新都会崩(torch.xpu 缺失 / flash_attn_3 schema / FLAX_WEIGHTS_NAME 缺失)。

---

## A. 远程 GPU 机(Featurize RTX 4090 48G)

### A1. 开实例
- GPU **1×RTX 4090 48G**、计费 **按量 ¥3/小时**(先按量验证,别一上来包日/周)。
- 镜像 **App(推荐)**(Docker + Python 3.11 + PyTorch)。磁盘 700GB 够。

### A2. 装依赖(SSH 进实例;全程走国内镜像,pytorch.org CDN 连不上)
```bash
# 统一用清华 PyPI 镜像(慢/缺就换 https://mirrors.aliyun.com/pypi/simple/)
M=https://pypi.tuna.tsinghua.edu.cn/simple

# 1) torch 三件套对齐 2.4.1 / cu121(镜像版自带 torch.xpu;与现驱动 cu121 一致,不怕变 CPU 版)
pip install -U torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 -i $M

# 2) diffusers 钉稳定版(含 LTX、兼容 torch 2.4)+ transformers 钉兼容版(仍含 FLAX_WEIGHTS_NAME)
pip install "diffusers==0.32.2" "transformers==4.46.3" -i $M

# 3) 其余依赖
pip install accelerate sentencepiece imageio imageio-ffmpeg pillow httpx fastapi "uvicorn[standard]" -i $M

# 4) 验证版本 + CUDA(关键三项全绿才继续)
python - <<'PY'
import torch, torchaudio, torchvision, diffusers, transformers
print("torch", torch.__version__, "| torchaudio", torchaudio.__version__, "| torchvision", torchvision.__version__)
print("diffusers", diffusers.__version__, "| transformers", transformers.__version__)
print("cuda", torch.cuda.is_available(), "| xpu", hasattr(torch, "xpu"))
PY
# 期望:torch 2.4.1+cu121 | torchaudio 2.4.1+cu121 | torchvision 0.19.1+cu121
#       diffusers 0.32.2 | transformers 4.46.3
#       cuda True | xpu True
```

### A3. 上传服务代码
把 [`deploy/i2v_server.py`](./i2v_server.py) 传到实例(平台文件上传 / scp / vim 粘贴),放 `~/work/`。

### A4. 启动服务(必须设 HF 镜像,否则拉不到权重)
```bash
export HF_ENDPOINT=https://hf-mirror.com                       # huggingface.co 被墙,走国内镜像
export I2V_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
echo "记下这个 token(后端要用): $I2V_TOKEN"
uvicorn i2v_server:app --host 0.0.0.0 --port 6006
```
- **首次自动下载 LTX-Video 权重(约 20-40GB,含 T5,等几分钟到十几分钟)**;中断重跑同条命令会断点续传。
- 日志出现 `Uvicorn running on http://0.0.0.0:6006` 即就绪。后台常驻用 `nohup ... &` 或 `tmux`。
- 把 export 固化免得每次忘:`echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc`

### A5. 机上自测
```bash
curl -s http://localhost:6006/health           # {"ok":true,"model":"Lightricks/LTX-Video"}
curl -X POST http://localhost:6006/i2v \
  -H "Authorization: Bearer $I2V_TOKEN" -H "Content-Type: application/json" \
  -d '{"image_url":"https://<你COS上任意一张配图>.png","prompt":"a person walks across the street with clear motion"}' \
  --output test.mp4
# 能拿到能播的 test.mp4 → 服务通了
```

### A6. 把 6006 暴露给后端(二选一)
- **平台端口映射**:Featurize 给一个公网地址 → 后端 `selfhost_i2v_url` 填 `https://xxx.../i2v`。
- **SSH 隧道**(通用):在跑后端的机器上 `ssh -N -L 6006:localhost:6006 <user>@<gpu-host>`
  → 后端 `selfhost_i2v_url` 填 `http://localhost:6006/i2v`。
> 公网暴露**务必带 `I2V_TOKEN`**,否则谁都能白嫖你的 GPU。

---

## B. 本地后端(engGramer)接入
`backend/.env` 增加(用 A4/A6 的地址与 token):
```dotenv
VIDEO_PROVIDER=selfhost
SELFHOST_I2V_URL=http://localhost:6006/i2v      # 或平台公网 https://.../i2v
SELFHOST_I2V_TOKEN=<A4 记下的 I2V_TOKEN>
```
**重启后端**(改 .env 需重启)。生成逻辑不变:`generate_gif_for_word` → `i2v_to_cos` 按 `VIDEO_PROVIDER`
分派到自托管服务,拿回 mp4 字节转存 COS,写入 `vocabulary_words.gif_url`。切回智谱:`VIDEO_PROVIDER=zhipu`。
> COS 必须是真配置(自托管返回 mp4 字节,靠 COS 托管出直链)。

---

## C. 批量刷 + 关机
- admin「词力通媒体」→ 筛动词 → **批量生成动图**(逐词调自托管服务)。
- 4090 上 LTX 约 30-90s/条 → 300 词约 4-8 GPU-小时 ≈ **¥12-24**。
- **刷完立刻在平台停/关实例**(按小时计费,开着就烧 ¥3/小时)。

---

## 踩坑对照(报错 → 原因 → 解)
| 报错关键字 | 原因 | 解 |
|---|---|---|
| `torch has no attribute 'xpu'` | torch 2.2.2 太旧 | 升 torch 2.4.1(A2 步1) |
| `download.pytorch.org ... SSLEOFError` | 连不上 pytorch CDN | 走清华/阿里镜像 `-i`(A2) |
| `libtorchaudio.so: undefined symbol` | torchaudio 没跟 torch 一起升 | 三件套同升 2.4.1(A2 步1) |
| `infer_schema ... flash_attn_3` | diffusers 太新,torch 2.4 跟不上 | 钉 diffusers 0.32.2(A2 步2) |
| `cannot import FLAX_WEIGHTS_NAME` | transformers 太新 | 钉 transformers 4.46.3(A2 步2) |
| `Cannot load model ... fetch metadata from Hub` | huggingface.co 被墙 | `export HF_ENDPOINT=https://hf-mirror.com`(A4) |

## 成本对照(约 300 动词)
| 方案 | 成本 | 备注 |
|---|---|---|
| 自托管 LTX @4090 | ¥12-24 + 搭建 | 量大/复刷最省 |
| 智谱 cogvideox-2 | ¥150(散)/ ¥120(优选包) | 零搭建 |
| 智谱 cogvideox-3 | ¥300 | 质量最新 |
