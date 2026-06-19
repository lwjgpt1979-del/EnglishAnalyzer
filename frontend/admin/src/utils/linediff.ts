// 轻量行级文本 diff(LCS),供内容版本对比展示。零依赖。
export interface DiffLine { type: 'same' | 'add' | 'del'; text: string }

export function lineDiff(base: string, incoming: string): DiffLine[] {
  const a = (base ?? '').split('\n')
  const b = (incoming ?? '').split('\n')
  const n = a.length, m = b.length
  // dp[i][j] = LCS 长度(从 i,j 到末尾)
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  const out: DiffLine[] = []
  let i = 0, j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push({ type: 'same', text: a[i] }); i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: 'del', text: a[i] }); i++ }
    else { out.push({ type: 'add', text: b[j] }); j++ }
  }
  while (i < n) out.push({ type: 'del', text: a[i++] })
  while (j < m) out.push({ type: 'add', text: b[j++] })
  return out
}
