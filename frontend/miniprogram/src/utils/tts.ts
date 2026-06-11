// src/utils/tts.ts —— 解析一段文本的可播放音频 URL
import { request } from '@/utils/request'

const BASE = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

/**
 * 返回可播放的音频 URL：
 * - 后端配置了 COS → 返回 COS 直链（已持久化，命中即复用，不重复合成）
 * - 未配 COS → 回退到 /tts/speak 流式接口
 */
export async function resolveSpeakUrl(text: string): Promise<string> {
  const fallback = `${BASE}/api/v1/tts/speak?text=${encodeURIComponent(text)}`
  try {
    const r = await request<{ url: string }>(
      `/api/v1/tts/url?text=${encodeURIComponent(text)}`, { method: 'GET' },
    )
    return r?.url || fallback
  } catch {
    return fallback
  }
}
