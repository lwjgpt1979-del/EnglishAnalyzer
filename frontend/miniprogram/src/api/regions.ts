import { request } from '@/utils/request'

// 行政区划地区（后端 region 表唯一源，公开免登录，懒加载省→市→区县→乡镇）
export interface RegionNode {
  code: string
  name: string
  parent_code: string | null
  level: number
  leaf: boolean
}

/** 取某父级的下级地区；不传 parent 取全部省级。 */
export function listRegions(parent?: string): Promise<RegionNode[]> {
  const q = parent ? `?parent=${encodeURIComponent(parent)}` : ''
  return request<RegionNode[]>(`/api/v1/regions${q}`, { method: 'GET' })
}
