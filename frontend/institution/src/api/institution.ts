import request, { unwrap } from './request'

export interface InstitutionOverview {
  teacher_count: number
  student_count: number
  member_count: number
  active_7d_count: number
  expiring_30d_count: number
  month_purchase_fen: number
  tier_distribution: Record<string, number>
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
  monthly_paper_quota: number | null
}

export function setTeacherQuota(teacherId: string, quota: number | null): Promise<InstitutionTeacher> {
  return unwrap<InstitutionTeacher>(request.patch(`/institution/teachers/${teacherId}/quota`, { monthly_paper_quota: quota }))
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

export interface RenewableStudent {
  student_id: string; nickname: string | null; tier: string; expires_at: string
}

export function listRenewableStudents(expiringDays?: number): Promise<RenewableStudent[]> {
  const q = expiringDays != null ? `?expiring_days=${expiringDays}` : ''
  return unwrap<RenewableStudent[]>(request.get(`/institution/renewable-students${q}`))
}
export function batchRenew(studentIds: string[], durationMonths: number): Promise<{ renewed_count: number; total_amount_fen: number; skipped: string[] }> {
  return unwrap(request.post('/institution/batch-renew', { student_ids: studentIds, duration_months: durationMonths }))
}

export interface BillItem { date: string; type: string; summary: string; amount_fen: number }

export function listBills(): Promise<BillItem[]> {
  return unwrap<BillItem[]>(request.get('/institution/bills'))
}

// ── 机构自助入驻申请（M47，公开免登录）──────────────────────────────────
export interface InstitutionApplyPayload {
  name: string
  contact_phone: string
  province_code: string
  city_code: string
  address: string
  code: string
}

export interface CaptchaData { captcha_id: string; image_svg: string }

export function getApplyCaptcha(): Promise<CaptchaData> {
  return unwrap<CaptchaData>(request.get('/institution/apply/captcha'))
}

export function applySendCode(
  phone: string, captchaId: string, captchaCode: string,
): Promise<{ sent: boolean }> {
  return unwrap<{ sent: boolean }>(request.post('/institution/apply/send-code', {
    phone, captcha_id: captchaId, captcha_code: captchaCode,
  }))
}

export function applyInstitution(
  payload: InstitutionApplyPayload,
): Promise<{ institution_id: string; name: string; status: string }> {
  return unwrap(request.post('/institution/apply', payload))
}
