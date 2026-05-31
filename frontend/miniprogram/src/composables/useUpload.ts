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

      // Step 2: 检测图片类型
      const lower = tempFilePath.toLowerCase()
      const contentType: MimeType = lower.endsWith('.png')
        ? 'image/png'
        : lower.endsWith('.webp')
          ? 'image/webp'
          : 'image/jpeg'

      // Step 3: 获取预签名 URL
      progress.value = 'presigning'
      const presign = await getPresignUrl(contentType)

      // Step 4: 读取图片为 ArrayBuffer，直传 COS presigned PUT URL
      // 注意：不同微信 SDK 版本 / 模拟器返回的 binary 类型不一致
      // （可能是 ArrayBuffer / Uint8Array / Node Buffer），统一规整为 ArrayBuffer
      progress.value = 'uploading'
      const arrayBuffer = await new Promise<ArrayBuffer>((resolve, reject) => {
        wx.getFileSystemManager().readFile({
          filePath: tempFilePath,
          success: (res) => {
            const d = res.data as unknown
            // 小程序 service / page 跨 realm 时 instanceof ArrayBuffer 会失败，
            // 改用 Object.prototype.toString 做跨 realm 安全检测
            const tag = Object.prototype.toString.call(d)
            if (tag === '[object ArrayBuffer]') {
              resolve(d as ArrayBuffer)
            } else if (
              tag === '[object Uint8Array]' ||
              (d && typeof d === 'object' && 'byteLength' in d && 'buffer' in d)
            ) {
              // Uint8Array / Node Buffer — 切片得到纯 ArrayBuffer
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

      // dev 模式（is_mock=true）跳过实际 PUT：后端直接给了可访问的占位图 URL
      if (!presign.is_mock) {
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
      } else {
        console.warn('[useUpload] dev mock 模式：跳过 COS PUT，直接用占位图 URL', presign.file_url)
      }

      // Step 5: 创建错题记录
      progress.value = 'creating'
      const wq = await createWrongQuestion({
        source_image_url: presign.file_url,
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
