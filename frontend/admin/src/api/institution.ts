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

export interface InstitutionTeacher {
  id: string
  nickname: string | null
  phone: string | null
  subject: string | null
  cert_status: string
}

export function generateTeacherInviteCode(): Promise<{ code: string; expires_at: string }> {
  return unwrap(request.post('/institution/teachers/invite-code'))
}

export function listTeachers(): Promise<InstitutionTeacher[]> {
  return unwrap<InstitutionTeacher[]>(request.get('/institution/teachers'))
}

export function removeTeacher(teacherId: string): Promise<{ removed: string }> {
  return unwrap(request.delete(`/institution/teachers/${teacherId}`))
}

export interface ActivationCode { code: string; status: string; used_at: string | null }
export interface PurchaseDetail {
  id: string; tier: string; duration_months: number; quantity: number
  amount_fen: number; status: string; created_at: string; codes: ActivationCode[]
}
export interface PurchaseListItem {
  id: string; tier: string; duration_months: number; quantity: number
  amount_fen: number; status: string; created_at: string
  used_count: number; total_count: number
}

export function createPurchase(data: { tier: string; duration_months: number; quantity: number }): Promise<PurchaseDetail> {
  return unwrap<PurchaseDetail>(request.post('/institution/purchases', data))
}
export function listPurchases(): Promise<PurchaseListItem[]> {
  return unwrap<PurchaseListItem[]>(request.get('/institution/purchases'))
}
export function getPurchaseCodes(purchaseId: string): Promise<ActivationCode[]> {
  return unwrap<ActivationCode[]>(request.get(`/institution/purchases/${purchaseId}/codes`))
}
