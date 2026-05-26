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
      progress.value = 'uploading'
      const arrayBuffer = await new Promise<ArrayBuffer>((resolve, reject) => {
        wx.getFileSystemManager().readFile({
          filePath: tempFilePath,
          success: (res) => {
            if (!(res.data instanceof ArrayBuffer)) {
              reject(new Error('读取文件返回非 ArrayBuffer，请重试'))
              return
            }
            resolve(res.data)
          },
          fail: (err) => reject(new Error(err.errMsg || '读取文件失败')),
        })
      })

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
