import { ref } from 'vue'
import { getPresignUrl } from '@/api/upload'
import { createWrongQuestion } from '@/api/wrongQuestions'
import type { WrongQuestionOut } from '@/types/api'

type MimeType = 'image/jpeg' | 'image/png' | 'image/webp'

type UploadProgress =
  | 'idle'
  | 'choosing'
  | 'presigning'
  | 'uploading'
  | 'creating'
  | 'done'
  | 'error'

interface UploadOptions {
  questionType?: string
  difficulty?: number
}

/** 读取本地图片为纯 ArrayBuffer（跨 realm 安全）。H5 无 wx 文件 API，走 fetch 读 blob。 */
function readFileAsArrayBuffer(tempFilePath: string): Promise<ArrayBuffer> {
  // #ifdef H5
  // H5：chooseImage 返回 blob: URL，fetch 即可拿到二进制
  return fetch(tempFilePath).then((r) => {
    if (!r.ok) throw new Error(`读取文件失败：HTTP ${r.status}`)
    return r.arrayBuffer()
  })
  // #endif
  // #ifndef H5
  return new Promise<ArrayBuffer>((resolve, reject) => {
    wx.getFileSystemManager().readFile({
      filePath: tempFilePath,
      success: (res) => {
        const d = res.data as unknown
        const tag = Object.prototype.toString.call(d)
        if (tag === '[object ArrayBuffer]') {
          resolve(d as ArrayBuffer)
        } else if (
          tag === '[object Uint8Array]' ||
          (d && typeof d === 'object' && 'byteLength' in d && 'buffer' in d)
        ) {
          const u8 = d as Uint8Array
          const ab = u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength) as ArrayBuffer
          resolve(ab)
        } else {
          reject(new Error(`文件读取返回未知类型 ${tag}，请反馈给开发者`))
        }
      },
      fail: (err) => reject(new Error(err.errMsg || '读取文件失败')),
    })
  })
  // #endif
}

/**
 * 上传单张本地图片到 COS（presign → PUT），返回可访问的 file_url。
 * 供整卷多图上传等场景复用。不创建任何业务记录。
 */
export async function uploadOneImage(tempFilePath: string): Promise<string> {
  const lower = tempFilePath.toLowerCase()
  const contentType: MimeType = lower.endsWith('.png')
    ? 'image/png'
    : lower.endsWith('.webp')
      ? 'image/webp'
      : 'image/jpeg'

  const presign = await getPresignUrl(contentType)
  const arrayBuffer = await readFileAsArrayBuffer(tempFilePath)

  // dev 模式（is_mock=true）跳过实际 PUT：后端直接给了可访问的占位图 URL
  if (!presign.is_mock) {
    // #ifdef H5
    // H5：用 fetch 直传 COS 预签名 PUT（需 COS 桶为该 Origin 配置 CORS 允许 PUT）
    const resp = await fetch(presign.presign_url, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body: arrayBuffer,
    })
    if (resp.status !== 200 && resp.status !== 204) {
      throw new Error(`COS 上传失败：HTTP ${resp.status}`)
    }
    // #endif
    // #ifndef H5
    await new Promise<void>((resolve, reject) => {
      wx.request({
        url: presign.presign_url,
        method: 'PUT',
        data: arrayBuffer,
        header: { 'Content-Type': contentType },
        responseType: 'arraybuffer',
        success: (res) => {
          if (res.statusCode === 200 || res.statusCode === 204) {
            resolve()
          } else {
            reject(new Error(`COS 上传失败：HTTP ${res.statusCode}`))
          }
        },
        fail: (err) => reject(new Error(err.errMsg || 'COS 上传失败')),
      })
    })
    // #endif
  } else {
    console.warn('[uploadOneImage] dev mock 模式：跳过 COS PUT，直接用占位图 URL', presign.file_url)
  }

  return presign.file_url
}

export function useUpload() {
  const uploading = ref(false)
  const progress = ref<UploadProgress>('idle')
  const errorMsg = ref('')

  async function uploadAndCreate(
    options: UploadOptions = {},
  ): Promise<WrongQuestionOut | null> {
    uploading.value = true
    progress.value = 'choosing'
    errorMsg.value = ''

    try {
      // Step 1: 选图（用户取消时静默重置，不视为错误）
      const tempFilePath = await new Promise<string>((resolve, reject) => {
        uni.chooseImage({
          count: 1,
          sizeType: ['compressed'],
          sourceType: ['album', 'camera'],
          success: (res) => resolve(res.tempFilePaths[0]),
          fail: (err) => {
            const msg = err.errMsg || ''
            const cancelled = new Error(msg || '选图取消') as Error & { isCancelled?: boolean }
            cancelled.isCancelled = msg.includes('cancel')
            reject(cancelled)
          },
        })
      })

      // Step 2-4: presign → 读取 → 直传 COS（跨端，统一走 uploadOneImage）
      progress.value = 'uploading'
      const fileUrl = await uploadOneImage(tempFilePath)

      // Step 5: 创建错题记录
      progress.value = 'creating'
      const wq = await createWrongQuestion({
        source_image_url: fileUrl,
        question_type: options.questionType,
        difficulty: options.difficulty,
      })

      progress.value = 'done'
      return wq
    } catch (e) {
      // 用户主动取消选图：静默重置，不显示错误
      if ((e as { isCancelled?: boolean }).isCancelled) {
        progress.value = 'idle'
        return null
      }
      progress.value = 'error'
      errorMsg.value = (e as Error).message || '上传失败'
      return null
    } finally {
      uploading.value = false
    }
  }

  return { uploading, progress, errorMsg, uploadAndCreate }
}
