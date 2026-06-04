import request, { unwrap } from './request'

export interface InstitutionOverview {
  teacher_count: number
  student_count: number
  member_count: number
  active_7d_count: number
}

export interface InstitutionProfile {
  id: string
  name: string
  contact_phone: string
  province_code: string
  city_code: string
  address: string
  status: string
  created_at: string
}

export function getOverview(): Promise<InstitutionOverview> {
  return unwrap<InstitutionOverview>(request.get('/institution/overview'))
}

export function getProfile(): Promise<InstitutionProfile> {
  return unwrap<InstitutionProfile>(request.get('/institution/profile'))
}

export function updateProfile(
  data: Partial<Pick<InstitutionProfile, 'name' | 'contact_phone' | 'address'>>,
): Promise<InstitutionProfile> {
  return unwrap<InstitutionProfile>(request.patch('/institution/profile', data))
}
