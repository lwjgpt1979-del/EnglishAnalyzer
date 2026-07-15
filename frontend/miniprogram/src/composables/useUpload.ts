import { getPresignUrl } from '@/api/upload'
import { BASE_URL } from '@/utils/request'

type MimeType = 'image/jpeg' | 'image/png' | 'image/webp'

// #ifdef H5
/**
 * H5 中转上传：浏览器无法直传 COS（桶未配 CORS），改用 uni.uploadFile 传到后端，
 * 由后端代传 COS 后返回 file_url。小程序端不走此路（见 uploadOneImage 的 #ifndef H5 分支）。
 */
function uploadViaProxy(tempFilePath: string): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    uni.uploadFile({
      url: `${BASE_URL}/api/v1/upload/proxy`,
      filePath: tempFilePath,
      name: 'file',
      header: { Authorization: `Bearer ${uni.getStorageSync('access_token') || ''}` },
      success: (res) => {
        try {
          const body = JSON.parse(res.data) as {
            code?: number; message?: string; data?: { file_url?: string }
          }
          if (res.statusCode === 200 && body.code === 200 && body.data?.file_url) {
            resolve(body.data.file_url)
          } else {
            reject(new Error(body.message || `上传失败：HTTP ${res.statusCode}`))
          }
        } catch {
          reject(new Error('上传响应解析失败'))
        }
      },
      fail: (err) => reject(new Error(err.errMsg || '上传失败')),
    })
  })
}
// #endif

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
  // #ifdef H5
  // H5 浏览器无法直传 COS（桶未配 CORS），走后端中转上传
  return uploadViaProxy(tempFilePath)
  // #endif

  // #ifndef H5
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
    console.warn('[uploadOneImage] dev mock 模式：跳过 COS PUT，直接用占位图 URL', presign.file_url)
  }

  return presign.file_url
  // #endif
}
