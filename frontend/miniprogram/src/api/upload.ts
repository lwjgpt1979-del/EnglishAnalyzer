import { request } from '@/utils/request'
import type { PresignData } from '@/types/api'

export function getPresignUrl(contentType: string): Promise<PresignData> {
  return request<PresignData>('/api/v1/upload/presign', {
    method: 'POST',
    data: { content_type: contentType },
  })
}
