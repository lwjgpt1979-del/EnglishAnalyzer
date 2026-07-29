/**
 * 词卡播放偏好(例句连读 / 打开自动播)。
 * 弹层 WordCard 与词力通连读共用 read_seq key。
 */
const KEY_SEQ = 'vocab_read_seq'
const KEY_AUTO = 'vocab_card_autoplay'

function readBool(key: string, defaultVal: boolean): boolean {
  try {
    const v = uni.getStorageSync(key)
    if (v === '' || v === undefined || v === null) return defaultVal
    return v === true || v === '1' || v === 1
  } catch {
    return defaultVal
  }
}

function writeBool(key: string, on: boolean) {
  try {
    uni.setStorageSync(key, on ? 1 : 0)
  } catch { /* 存储失败静默 */ }
}

/** @returns 是否开启例句连读;默认 true(与词力通一致) */
export function getReadSeq(): boolean {
  return readBool(KEY_SEQ, true)
}

/** @param on 是否开启例句连读 */
export function setReadSeq(on: boolean) {
  writeBool(KEY_SEQ, on)
}

/**
 * 打开词卡是否自动播(方案 2:等同执行一次「发音」)。
 * @returns 默认 false(少打扰)
 */
export function getCardAutoPlay(): boolean {
  return readBool(KEY_AUTO, false)
}

/** @param on 是否打开词卡自动播 */
export function setCardAutoPlay(on: boolean) {
  writeBool(KEY_AUTO, on)
}
