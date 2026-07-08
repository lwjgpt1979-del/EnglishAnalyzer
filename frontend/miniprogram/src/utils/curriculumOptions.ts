/**
 * 教材版本/年级/学期可选值——后台单一真源(GET /curriculum/options)。
 * 全端学生页共用此加载器:进程内缓存 + 去重并发 + 网络失败兜底。
 * 前端不再各页写死 GRADES/TEXTBOOK_VERSIONS,格式永远和后台一致。
 */
import { getCurriculumOptions, type CurriculumOptions } from '@/api/curriculum'

// 兜底:仅当接口不可达时用(注释见 CLAUDE.md「运营可配置读后台」)。实际值以后台为准。
const FALLBACK: CurriculumOptions = {
  textbook_versions: ['译林版', '人教版', '外研版', '北师大版', '冀教版'],
  grades: ['小学1年级', '小学2年级', '小学3年级', '小学4年级', '小学5年级', '小学6年级',
           '初中7年级', '初中8年级', '初中9年级', '高中1年级', '高中2年级', '高中3年级'],
  semesters: ['上', '下'],
}

let cache: CurriculumOptions | null = null
let inflight: Promise<CurriculumOptions> | null = null

/** 拉取偏好可选值(缓存);失败回落兜底,永不 reject。 */
export async function loadCurriculumOptions(): Promise<CurriculumOptions> {
  if (cache) return cache
  if (!inflight) {
    inflight = getCurriculumOptions()
      .then((o) => {
        cache = (o && o.grades?.length) ? o : FALLBACK
        return cache
      })
      .catch(() => FALLBACK)
      .finally(() => { inflight = null })
  }
  return inflight
}

/** 同步兜底(用作 ref 初始值,onMounted 再用后台值覆盖)。 */
export function curriculumFallback(): CurriculumOptions {
  return { ...FALLBACK }
}
