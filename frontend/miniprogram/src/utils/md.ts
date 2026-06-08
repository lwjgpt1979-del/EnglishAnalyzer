/**
 * 轻量 Markdown → HTML 转换器（WeChat miniprogram rich-text 专用）
 *
 * 支持格式：
 * - ## 标题  →  <h2>
 * - ### 标题 →  <h3>
 * - **粗体** →  <strong>
 * - - 列表项 →  <ul><li>
 * - 普通段落 →  <p>
 *
 * 不支持（rich-text 限制）：<a>、<script>、事件绑定
 * rpx 单位不支持 inline-style，用 em/px 代替
 */
export function md2html(md: string): string {
  if (!md) return ''

  const lines = md.split('\n')
  const result: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // h2
    if (line.startsWith('## ')) {
      result.push(`<h2 style="font-size:1.1em;font-weight:700;margin:12px 0 6px">${escapeLine(line.slice(3))}</h2>`)

    // h3
    } else if (line.startsWith('### ')) {
      result.push(`<h3 style="font-size:1em;font-weight:600;margin:10px 0 4px">${escapeLine(line.slice(4))}</h3>`)

    // 列表——收集连续 "- " 开头行
    } else if (line.startsWith('- ')) {
      const items: string[] = []
      while (i < lines.length && lines[i].startsWith('- ')) {
        items.push(`<li style="margin:2px 0">${applyInline(lines[i].slice(2))}</li>`)
        i++
      }
      result.push(`<ul style="padding-left:20px;margin:6px 0">${items.join('')}</ul>`)
      continue  // i already advanced

    // 空行——段落分隔，跳过
    } else if (line.trim() === '') {
      // no-op

    // 普通段落行
    } else {
      result.push(`<p style="margin:4px 0;line-height:1.7">${applyInline(line)}</p>`)
    }

    i++
  }

  return result.join('')
}

/** 行内转换：粗体、斜体 */
function applyInline(text: string): string {
  return escapeLine(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}

/** HTML 转义（防 XSS，rich-text 虽不执行 script，但养成好习惯） */
function escapeLine(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
