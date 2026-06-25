<!-- src/pages/long-sentence/index.vue — 长难句学习 -->
<template>
  <view class="ls-page">
    <view v-if="loading" class="center-tip">加载中…</view>
    <view v-else-if="!items.length" class="center-tip">暂无长难句(运营审核发布后可见)</view>

    <view v-else class="scroll">
      <!-- 顶部:今日学习进度 + 打卡 -->
      <view class="header">
        <view class="prog">
          <text class="prog-label">今日学会 <text class="prog-num">{{ learnedCount }}</text> 句<text v-if="recTarget" class="prog-hint"> · 为你匹配难度 ~{{ recTarget }}</text></text>
          <view class="prog-bar"><view class="prog-fill" :style="{ width: pct + '%' }" /></view>
        </view>
        <view class="streak" @tap="openCalendar"><view class="ic ic-flame streak-ic" />{{ checkinStatus ? '连续 ' + checkinStatus.current_streak + ' 天' : '打卡' }}</view>
      </view>

      <!-- 句子卡 -->
      <view class="card sent-card">
        <view class="sc-top">
          <view class="nav">
            <text class="nav-btn" :class="{ dis: index === 0 }" @tap="prev">‹</text>
            <text class="nav-cur">第 {{ index + 1 }} 句</text>
            <text class="nav-btn" :class="{ dis: recing }" @tap="next">›</text>
          </view>
          <text v-if="isReview" class="review-tag">复习</text>
          <text v-if="srcLabel" class="src-tag">{{ srcLabel }}</text>
          <view class="sc-spacer" />
          <view v-if="difficulty != null" class="diff-ring" :class="diffLevel.cls">
            <text class="dr-num">{{ difficulty }}</text>
            <text class="dr-lb">难度·{{ diffLevel.label }}</text>
          </view>
        </view>

        <!-- 脚手架:按学生水平给该做什么 -->
        <view class="scaffold" :class="tier">
          <view class="ic sc-ic" :class="scaffold.ic" />
          <view class="sc-body"><text class="sc-label">{{ scaffold.label }}</text><text class="sc-tip">{{ scaffold.tip }}</text></view>
          <text v-if="!showStruct" class="sc-act" @tap="showStruct = true">显示结构</text>
        </view>

        <!-- 原句:连续流式段落,每段彩色虚线下划线,序号锚在该段首词下(保持原设计,勿改) -->
        <view v-if="showStruct && segments.length" class="sentence" :class="{ eye: eyeMode }" :style="{ fontSize: fontPx + 'rpx' }">
          <text v-for="s in segments" :key="s.idx" class="seg" :style="{ color: colorOf(s.idx), borderBottomColor: colorOf(s.idx) }"><text class="fw">{{ s.first }}<text class="badge" :style="{ background: colorOf(s.idx) }">{{ s.idx }}</text></text>{{ (s.rest ? ' ' + s.rest : '') + ' ' }}</text>
        </view>
        <text v-else class="plain">{{ detail?.text }}</text>

        <view v-if="showTranslate && analysis?.translation" class="trans">{{ analysis.translation }}</view>

        <!-- 图例:本句实际出现的颜色 → 成分类型(内联) -->
        <view v-if="showStruct && legend.length" class="legend">
          <view v-for="l in legend" :key="l.color" class="lg-item">
            <text class="lg-dot" :style="{ background: l.color }" /><text class="lg-tx">{{ l.label }}</text>
          </view>
        </view>

        <!-- R9.4 生词复现:本句里你在学的未掌握词,点一下顺势快测 -->
        <view v-if="vocabHits.length" class="vhits">
          <text class="vhits-lb">这句里你在学的词</text>
          <text v-for="h in vocabHits" :key="h.word_id" class="vhit-chip" @tap="openHit(h)">{{ h.word }}</text>
        </view>

        <!-- 工具栏:听 / 字号 / 护眼 / 翻译 / 收藏 / 更多 -->
        <view class="toolbar">
          <view class="tb" :class="{ on: playing }" @tap="listen"><view class="ic ic-volume tb-ic" /><text class="tb-tx">{{ playing ? '停止' : (loadingAudio ? '…' : '听') }}</text></view>
          <view class="tb" @tap="decFont"><text class="tb-ic tb-az">A−</text><text class="tb-tx">缩小</text></view>
          <view class="tb" @tap="incFont"><text class="tb-ic tb-az">A+</text><text class="tb-tx">放大</text></view>
          <view class="tb" :class="{ on: eyeMode }" @tap="eyeMode = !eyeMode"><view class="ic ic-eye tb-ic" /><text class="tb-tx">护眼</text></view>
          <view class="tb" :class="{ on: showTranslate }" @tap="showTranslate = !showTranslate"><view class="ic ic-translate tb-ic" /><text class="tb-tx">翻译</text></view>
          <view class="tb" :class="{ on: favorited }" @tap="toggleFav"><view class="ic tb-ic" :class="favorited ? 'ic-star-on' : 'ic-star'" /><text class="tb-tx">收藏</text></view>
          <view class="tb" @tap="onMore"><view class="ic ic-more tb-ic" /><text class="tb-tx">更多</text></view>
        </view>

        <!-- 理解检测:过关才算学(双探针:点主干 + 句意/逻辑),θ 实测校准 -->
        <view class="check">
          <view v-if="!checking && !result" class="check-cta" @tap="startCheck">
            <view class="ic ic-brain check-cta-ic" /><text class="check-cta-tx">检测理解 · 过关才算学会这句</text>
          </view>

          <view v-else-if="checking && !result" class="check-panel">
            <view v-for="(p, pi) in probes" :key="p.key" class="probe">
              <text class="probe-q">{{ pi + 1 }}. {{ p.prompt }}</text>
              <view class="probe-opts">
                <text v-for="(o, oi) in p.options" :key="oi" class="probe-opt"
                      :class="{ on: probeAnswers[p.key] === o }" @tap="pickProbe(p.key, o)">{{ o }}</text>
              </view>
            </view>
            <view class="self">
              <text class="self-q">顺便说下感受(可选):</text>
              <text class="self-btn easy" :class="{ on: selfRating === 'easy' }" @tap="toggleSelf('easy')">太简单</text>
              <text class="self-btn ok" :class="{ on: selfRating === 'ok' }" @tap="toggleSelf('ok')">刚好</text>
              <text class="self-btn hard" :class="{ on: selfRating === 'hard' }" @tap="toggleSelf('hard')">有点难</text>
            </view>
            <view class="check-submit" :class="{ dis: !allAnswered || submitting }" @tap="submitCheck">{{ submitting ? '判分中…' : '提交检测' }}</view>
          </view>

          <view v-else class="check-result" :class="{ pass: result?.passed, fail: !result?.passed }">
            <view class="cr-head">
              <view class="ic cr-ic" :class="result?.passed ? 'ic-check-circle' : 'ic-warning'" />
              <text class="cr-title">{{ result?.passed ? '理解通过 · 这句算学会了' : '还没全懂 · 已加入复习,稍后再练' }}</text>
            </view>
            <view v-for="pr in (result?.probes || [])" :key="pr.key" class="cr-probe" :class="{ ok: pr.correct }">
              <text class="cr-tag">{{ pr.correct ? '✓' : '✗' }}</text>
              <view class="cr-body">
                <text class="cr-label">{{ probeLabel(pr.key) }}{{ pr.correct ? ' · 答对' : '' }}</text>
                <text v-if="!pr.correct" class="cr-ans">正确答案:{{ pr.correct_answer }}</text>
                <text v-if="!pr.correct && pr.misconception" class="cr-mis">{{ pr.misconception }}</text>
              </view>
            </view>
          </view>

          <!-- 进阶·短翻译产出项:维度评分,检验「会输出」(理解检测后可选) -->
          <view v-if="result" class="prod">
            <view v-if="!transOpen && !transResult" class="prod-cta" @tap="openTrans">
              <view class="ic ic-pen prod-cta-ic" /><text class="prod-cta-tx">进阶 · 试译这句,检验输出</text>
            </view>
            <view v-else-if="!transResult" class="prod-panel">
              <!-- #ifdef MP-WEIXIN -->
              <view class="pv-row">
                <view class="pv-toggle" @tap="togglePvMode">
                  <view class="ic" :class="pvMode === 'voice' ? 'ic-keyboard' : 'ic-mic'" style="width:34rpx;height:34rpx" />
                </view>
                <view v-if="pvMode === 'voice'" class="pv-hold" :class="{ holding: pvRecording }"
                  @touchstart="pvStart" @touchmove="pvMove" @touchend="pvEnd" @touchcancel="pvEnd">
                  {{ pvRecording ? '松开 完成' : '按住 说中文' }}
                </view>
                <textarea v-else v-model="transAnswer" class="prod-input pv-grow" :maxlength="200"
                          placeholder="用中文写出这句的意思(尽量把主干、逻辑关系、修饰都译到位)" />
              </view>
              <!-- #endif -->
              <!-- #ifndef MP-WEIXIN -->
              <textarea v-model="transAnswer" class="prod-input" :maxlength="200"
                        placeholder="用中文写出这句的意思(尽量把主干、逻辑关系、修饰都译到位)" />
              <!-- #endif -->
              <view class="prod-submit" :class="{ dis: !transAnswer.trim() || transSubmitting }" @tap="submitTrans">{{ transSubmitting ? '评分中…' : '提交翻译' }}</view>
            </view>
            <view v-else class="prod-result">
              <view class="pr-head">
                <text class="pr-score" :class="{ pass: transResult.passed }">{{ transResult.total }}/{{ transResult.max }}</text>
                <text class="pr-verdict" :class="{ pass: transResult.passed }">{{ transResult.passed ? '输出达标 ✓' : '还需打磨' }}</text>
                <text class="pr-redo" @tap="redoTrans">重译</text>
              </view>
              <view v-for="d in transResult.dimensions" :key="d.key" class="pr-dim">
                <view class="pr-dim-top">
                  <text class="pr-dim-label">{{ d.label }}</text>
                  <view class="pr-dots"><text v-for="n in d.max" :key="n" class="pr-dot" :class="{ on: n <= d.score }" /></view>
                </view>
                <text v-if="d.note" class="pr-dim-note">{{ d.note }}</text>
              </view>
              <view v-if="transResult.feedback" class="pr-fb"><text class="pr-fb-lb">总评</text>{{ transResult.feedback }}</view>
            </view>
          </view>

          <!-- 迁移挑战:换一句同结构新句,验证「真会这个句法」而非「记住这道题」 -->
          <view v-if="result?.passed" class="tf">
            <view v-if="!tfStarted" class="tf-cta" @tap="startTransfer">
              <view class="ic ic-refresh tf-cta-ic" /><text class="tf-cta-tx">迁移挑战 · 换个同结构的新句试试</text>
            </view>
            <view v-else-if="tfLoading" class="tf-loading">正在找同结构的新句…</view>
            <view v-else-if="!tfItem" class="tf-empty">暂时没有同结构的新句,继续学下一句吧</view>
            <view v-else class="tf-card">
              <view class="tf-head">
                <text class="tf-badge">迁移挑战</text>
                <text v-for="s in tfShared" :key="s" class="tf-tag">{{ s }}</text>
              </view>
              <text class="tf-sent">{{ tfItem.text }}</text>

              <template v-if="!tfResult">
                <view v-for="(p, pi) in tfProbes" :key="p.key" class="probe">
                  <text class="probe-q">{{ pi + 1 }}. {{ p.prompt }}</text>
                  <view class="probe-opts">
                    <text v-for="(o, oi) in p.options" :key="oi" class="probe-opt"
                          :class="{ on: tfAnswers[p.key] === o }" @tap="pickTf(p.key, o)">{{ o }}</text>
                  </view>
                </view>
                <view class="check-submit" :class="{ dis: !tfAllAnswered || tfSubmitting }" @tap="submitTf">{{ tfSubmitting ? '判分中…' : '提交迁移检测' }}</view>
              </template>

              <view v-else class="tf-result" :class="tfResult.verdict">
                <view class="tf-rhead">
                  <view class="ic tf-ric" :class="tfResult.verdict === 'transferred' ? 'ic-trophy' : 'ic-refresh'" />
                  <text class="tf-rtitle">{{ tfResult.verdict === 'transferred' ? '迁移成功 · 真的掌握了这个句法!' : '像是记住了原题 · 换句就卡住了' }}</text>
                </view>
                <text class="tf-rdesc">{{ tfResult.verdict === 'transferred' ? ('在新句里也认出了「' + tfShared.join('、') + '」,说明学的是结构不是这道题。') : ('「' + tfShared.join('、') + '」还没真正掌握,已加入复习,过段时间再练。') }}</text>
                <view v-for="pr in tfResult.probes" :key="pr.key" class="cr-probe" :class="{ ok: pr.correct }">
                  <text class="cr-tag">{{ pr.correct ? '✓' : '✗' }}</text>
                  <view class="cr-body">
                    <text class="cr-label">{{ probeLabel(pr.key) }}{{ pr.correct ? ' · 答对' : '' }}</text>
                    <text v-if="!pr.correct" class="cr-ans">正确答案:{{ pr.correct_answer }}</text>
                    <text v-if="!pr.correct && pr.misconception" class="cr-mis">{{ pr.misconception }}</text>
                  </view>
                </view>
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- Tab 卡 -->
      <view class="card">
        <view class="seg-tabs">
          <text v-for="t in TABS" :key="t.key" class="seg-tab" :class="{ on: tab === t.key }" @tap="tab = t.key">{{ t.label }}</text>
        </view>

        <!-- 句子结构:主干 → 从句/修饰(紧凑树)-->
        <view v-if="tab === 'struct'">
          <view v-if="trunkText || clauseSegs.length" class="st">
            <view v-if="trunkText" class="st-trunk">主干:{{ trunkText }}</view>
            <text v-if="clauseSegs.length" class="st-arrow">⌄</text>
            <view v-if="clauseSegs.length" class="st-children">
              <view v-for="s in clauseSegs" :key="s.idx" class="st-clause" :style="{ background: tintOf(s.idx), borderColor: colorOf(s.idx) }">
                <view class="st-chead">
                  <text class="st-cno" :style="{ background: colorOf(s.idx) }">{{ s.idx }}</text>
                  <text class="st-ctype" :style="{ color: colorOf(s.idx) }">{{ s.type }}</text>
                </view>
                <text class="st-ctext">{{ s.text }}</text>
              </view>
            </view>
          </view>
          <text v-else class="empty">暂无结构数据</text>
        </view>

        <!-- 句子成分 -->
        <view v-else-if="tab === 'comp'" class="tab-body">
          <view v-for="c in compRows" :key="c.label" class="comp-row">
            <text class="comp-label">{{ c.label }}</text><text class="comp-val">{{ c.val }}</text>
          </view>
          <text v-if="!compRows.length" class="empty">暂无成分数据</text>
        </view>

        <!-- 重点词汇 -->
        <view v-else-if="tab === 'words'" class="tab-body">
          <view v-for="(w, i) in (analysis?.key_words || [])" :key="i" class="word-row">
            <view class="word-head"><text class="word">{{ w.word }}</text><text v-if="w.pos" class="word-pos">{{ w.pos }}</text></view>
            <text v-if="w.meaning" class="word-mean">{{ w.meaning }}</text>
          </view>
          <text v-if="!(analysis?.key_words || []).length" class="empty">暂无重点词汇</text>
        </view>

        <!-- 语法点 -->
        <view v-else class="tab-body">
          <view v-for="(g, i) in gpList" :key="i" class="gp-row" :style="{ background: g.tint }">
            <text class="gp-name" :style="{ color: g.color }">{{ g.name }}</text>
            <text v-if="g.explanation" class="gp-exp">{{ g.explanation }}</text>
          </view>
          <text v-if="!gpList.length" class="empty">暂无语法点</text>
        </view>
      </view>

      <!-- 结构解析 -->
      <view class="card" v-if="analysis?.sentence_type || (analysis?.explanations || []).length || analysis?.summary">
        <view class="sec-row">
          <text class="sec-title">结构解析</text>
          <text class="link" @tap="openKpDetail">查看语法点详解 ›</text>
        </view>
        <view v-if="analysis?.sentence_type" class="stype">
          <view class="ic ic-layout stype-ic" />
          <text class="stype-tx">{{ analysis.sentence_type.replace(/。$/, '') }}</text>
        </view>
        <view class="tl">
          <view v-for="e in (analysis?.explanations || [])" :key="e.idx" class="tl-row">
            <view class="tl-rail"><text class="tl-dot" :style="{ background: colorOf(e.idx) }">{{ e.idx }}</text></view>
            <text class="tl-text">{{ e.text }}</text>
          </view>
        </view>
        <view v-if="analysis?.summary" class="summary"><text class="summary-lb">小结</text>{{ analysis.summary }}</view>
      </view>

      <view class="footer-space" />
    </view>

    <!-- 底部固定栏 -->
    <view v-if="!loading && items.length" class="footer">
      <view class="foot-side" @tap="go('/pages/vocabulary/index')"><view class="ic ic-book fs-ic" /><text class="fs-tx">生词本</text></view>
      <view class="foot-main" @tap="next">再学一句</view>
      <view class="foot-side" @tap="go('/pages/wrong-questions/list')"><view class="ic ic-help fs-ic" /><text class="fs-tx">错题本</text></view>
    </view>

    <!-- 更多:底部弹层 -->
    <!-- R9.4 生词快测弹层 -->
    <view v-if="hitWord" class="more-mask" @tap="closeHit">
      <view class="hit-sheet" @tap.stop>
        <view class="hit-head"><text class="hit-word">{{ hitWord.word }}</text><text class="hit-close" @tap="closeHit">✕</text></view>
        <view v-if="!hitProbe" class="hit-tip">加载中…</view>
        <view v-else>
          <text class="probe-q">{{ hitProbe.prompt }}</text>
          <view class="probe-opts">
            <text v-for="(o, i) in hitProbe.options" :key="i" class="probe-opt"
              :class="{ on: hitPick === o, ok: hitResult && o === hitResult.correct_answer, no: hitResult && hitPick === o && o !== hitResult.correct_answer }"
              @tap="!hitResult && (hitPick = o)">{{ o }}</text>
          </view>
          <view v-if="!hitResult" class="check-submit" :class="{ dis: !hitPick }" @tap="submitHit">提交</view>
          <view v-else class="hit-fb" :class="hitResult.correct ? 'ok' : 'no'">
            {{ hitResult.correct ? '✓ 在语境里认得出' : ('✗ 正确:' + hitResult.correct_answer + (hitResult.misconception ? '|' + hitResult.misconception : '')) }}
          </view>
        </view>
      </view>
    </view>

    <view v-if="moreOpen" class="more-mask" @tap="moreOpen = false">
      <view class="more-sheet" @tap.stop>
        <view class="more-grab" />
        <view class="more-item" @tap="moreToggleStruct"><view class="ic ic-eye mi-ic" /><text class="mi-tx">{{ showStruct ? '隐藏原句结构' : '显示原句结构' }}</text><text class="mi-arrow">›</text></view>
        <view class="more-item" @tap="moreCopy"><view class="ic ic-clipboard mi-ic" /><text class="mi-tx">复制原句</text><text class="mi-arrow">›</text></view>
        <view class="more-item" @tap="moreDiff"><view class="ic ic-chart mi-ic" /><text class="mi-tx">难度说明</text><text class="mi-arrow">›</text></view>
        <view class="more-item" @tap="moreKp"><view class="ic ic-book mi-ic" /><text class="mi-tx">查看语法点详解</text><text class="mi-arrow">›</text></view>
        <view class="more-cancel" @tap="moreOpen = false">取消</view>
      </view>
    </view>

    <!-- 打卡日历弹层 -->
    <view v-if="calOpen" class="cal-mask" @tap="calOpen = false">
      <view class="cal-card" @tap.stop>
        <view class="cal-head">
          <view class="cal-title"><view class="ic ic-calendar cal-title-ic" /><text>学习打卡</text></view>
          <text class="cal-close" @tap="calOpen = false">✕</text>
        </view>
        <view class="cal-stats">
          <view class="cal-stat"><text class="cs-num">{{ cal?.current_streak ?? 0 }}</text><text class="cs-lb">连续天数</text></view>
          <view class="cal-stat"><text class="cs-num">{{ cal?.longest_streak ?? 0 }}</text><text class="cs-lb">历史最高</text></view>
          <view class="cal-stat"><text class="cs-num">{{ cal?.checked_count ?? 0 }}</text><text class="cs-lb">本月打卡</text></view>
        </view>
        <view class="cal-grid">
          <text v-for="w in ['日','一','二','三','四','五','六']" :key="w" class="cal-wd">{{ w }}</text>
          <view v-for="(c, i) in calCells" :key="i" class="cal-cell" :class="{ checked: c.checked, today: c.today, blank: !c.day }">
            <text v-if="c.day">{{ c.day }}</text>
          </view>
        </view>
        <view class="cal-foot">
          <text class="cal-btn" :class="{ done: checkinStatus?.checked_in_today }" @tap="doCheckin">
            {{ checkinStatus?.checked_in_today ? '今日已打卡 ✓' : '立即打卡' }}
          </text>
        </view>
      </view>
    </view>

    <!-- #ifdef MP-WEIXIN -->
    <!-- 试译·微信式「按住说话」录音浮层 -->
    <view v-if="pvRecording" class="rec-mask">
      <view class="rec-panel" :class="{ cancel: pvCancelZone }">
        <view v-if="!pvCancelZone" class="rec-wave">
          <view v-for="i in 5" :key="i" class="wbar" :style="{ animationDelay: (i * 0.12) + 's' }" />
        </view>
        <text v-else class="rec-cancel-ico">✕</text>
      </view>
      <text class="rec-tip" :class="{ cancel: pvCancelZone }">
        {{ pvCancelZone ? '松开手指，取消' : '正在聆听… 上滑取消' }}
      </text>
    </view>
    <!-- #endif -->
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getLongSentence, nextLongSentence, getComprehension, submitComprehension, submitTranslateCheck, getTransfer, submitTransfer, getVocabHits, getLsAudioUrl, favoriteLs, ttsSpeakUrl, type LSItem, type LSDetail, type LSAnalysis, type LSTier, type ComprehensionProbe, type ComprehensionResult, type TranslateCheckResult, type TransferItem, type TransferResult, type VocabHit } from '@/api/longSentence'
import { getWordProbes, submitWordProbe } from '@/api/vocabulary'
import { checkin, getCheckinStatus, getCheckinCalendar, type CheckinStatus, type CheckinCalendar } from '@/api/checkin'

// 颜色由后端按「成分类型」固定下发(segment.color/tint),前端按 idx 映射;缺省回退到调色板
const PALETTE = ['#8b5cf6', '#10b981', '#14b8a6', '#f59e0b', '#ef4444', '#3b82f6', '#6366f1', '#ec4899', '#0ea5e9']
const TINT = ['#f3effe', '#e7f7ef', '#e6f7f5', '#fef6e7', '#fdeceb', '#eaf1fe', '#eef0fe', '#fdeef6', '#e8f6fe']
const colorMap = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const s of (analysis.value?.segments || [])) if (s.color) m[s.idx] = s.color
  return m
})
const tintMap = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const s of (analysis.value?.segments || [])) if (s.tint) m[s.idx] = s.tint
  return m
})
const colorOf = (idx: number) => colorMap.value[idx] || PALETTE[(idx - 1) % PALETTE.length] || '#666'
const tintOf = (idx: number) => tintMap.value[idx] || TINT[(idx - 1) % TINT.length] || '#f5f5f5'
const TABS = [
  { key: 'struct', label: '句子结构' },
  { key: 'comp', label: '句子成分' },
  { key: 'words', label: '重点词汇' },
  { key: 'grammar', label: '语法点' },
]

const loading = ref(true)
const items = ref<LSItem[]>([])
const index = ref(0)
const detail = ref<LSDetail | null>(null)
const tab = ref('struct')
const showTranslate = ref(false)
const showStruct = ref(true)
const fontPx = ref(32)        // 原句字号(rpx),可调
const eyeMode = ref(false)    // 护眼模式
function incFont() { fontPx.value = Math.min(46, fontPx.value + 4) }
function decFont() { fontPx.value = Math.max(26, fontPx.value - 4) }

const SRC_LABEL: Record<string, string> = { platform_real: '真题', textbook: '教材', uploaded: '上传' }
const srcLabel = computed(() => SRC_LABEL[detail.value?.source_kind || ''] || '')
const difficulty = computed<number | null>(() => {
  const d = analysis.value?.difficulty
  return typeof d === 'number' ? d : null
})
const diffLevel = computed(() => {
  const d = difficulty.value ?? 0
  if (d >= 80) return { label: '高', cls: 'hard' }
  if (d >= 60) return { label: '中', cls: 'mid' }
  return { label: '低', cls: 'easy' }
})

const analysis = computed<LSAnalysis | null>(() => detail.value?.analysis || null)
const pct = computed(() => Math.min(100, learnedCount.value * 10))   // 今日进度(目标≈10句/天,以「学会」计)
const recTarget = ref(0)        // 推荐匹配的难度档(θ+5)
const recing = ref(false)       // 正在取推荐
const tier = ref<LSTier>('intro')   // 脚手架档:看懂/划结构/输出
const isReview = ref(false)         // 当前是否为「间隔重现」复习句

// 理解检测(过关才算学;θ 实测为主、自评为辅)
const learnedCount = ref(0)         // 今日「检测通过」的句数
const checking = ref(false)         // 检测面板已展开
const probes = ref<ComprehensionProbe[]>([])
const probeAnswers = ref<Record<string, string>>({})
const selfRating = ref<'easy' | 'ok' | 'hard' | ''>('')
const result = ref<ComprehensionResult | null>(null)
const submitting = ref(false)
const allAnswered = computed(() => probes.value.length > 0 && probes.value.every(p => !!probeAnswers.value[p.key]))
// 短翻译产出项(进阶·检验输出)
const transOpen = ref(false)
const transAnswer = ref('')
const transResult = ref<TranslateCheckResult | null>(null)
const transSubmitting = ref(false)
// 迁移项(同结构新句,区分「记住题 vs 会技能」)
const tfItem = ref<TransferItem | null>(null)
const tfShared = ref<string[]>([])
const tfProbes = ref<ComprehensionProbe[]>([])
const tfAnswers = ref<Record<string, string>>({})
const tfResult = ref<TransferResult | null>(null)
const tfLoading = ref(false)
const tfSubmitting = ref(false)
const tfStarted = ref(false)
const tfAllAnswered = computed(() => tfProbes.value.length > 0 && tfProbes.value.every(p => !!tfAnswers.value[p.key]))
const PROBE_LABEL: Record<string, string> = { main_clause: '点主干', paraphrase: '句意理解', cloze: '逻辑连接', struct_type: '句法点' }
function probeLabel(k: string) { return PROBE_LABEL[k] || '理解' }
const SCAFFOLD: Record<LSTier, { struct: boolean; translate: boolean; ic: string; label: string; tip: string }> = {
  intro:     { struct: true,  translate: true,  ic: 'ic-eye',    label: '入门·看懂',   tip: '已给出结构与译文,听读理解这句' },
  build:     { struct: false, translate: false, ic: 'ic-edit',   label: '进阶·划结构', tip: '先自己划主干和从句,再点「显示结构」核对' },
  challenge: { struct: false, translate: false, ic: 'ic-target', label: '挑战·输出',   tip: '试着翻译/复述这句,再展开结构与解析' },
}
const scaffold = computed(() => SCAFFOLD[tier.value])
const segments = computed(() => (analysis.value?.segments || []).slice().sort((a, b) => a.idx - b.idx).map(s => {
  const toks = (s.text || '').trim().split(/\s+/)
  return { ...s, first: toks[0] || '', rest: toks.slice(1).join(' ') }
}))

// 图例:本句实际用到的颜色去重,标签去掉「连词/第N分句」等后缀只留成分名
const legend = computed(() => {
  const seen = new Set<string>()
  const out: { color: string; label: string }[] = []
  for (const s of segments.value) {
    const c = (s as any).color as string | undefined
    if (!c || seen.has(c)) continue
    seen.add(c)
    const label = (s.type || '').replace(/(连词|关联词|第[一二三四五六七八九十]+分句|分句|部分)$/, '') || s.type || '成分'
    out.push({ color: c, label })
  }
  return out
})

// 句子结构:主干(主谓宾)+ 从句/修饰成分(其余段),供「主干→从句」紧凑树
const TRUNK_RE = /主干|主句|主语|谓语|宾语|表语/
const trunkText = computed(() => {
  const a = analysis.value
  if (a?.main_clause) return a.main_clause
  const t = segments.value.filter(s => TRUNK_RE.test(s.type || '')).map(s => s.text).join(' ')
  if (t) return t
  const c = a?.components || {}
  return [c.subject, c.predicate, c.object].filter(Boolean).join(' ')
})
const clauseSegs = computed(() => segments.value.filter(s => !TRUNK_RE.test(s.type || '')))

const compRows = computed(() => {
  const c = analysis.value?.components || {}
  const labelMap: Record<string, string> = { subject: '主语', predicate: '谓语', object: '宾语', complement: '补语', attributive: '定语', adverbial: '状语' }
  return Object.entries(c).filter(([, v]) => v).map(([k, v]) => ({ label: labelMap[k] || k, val: v as string }))
})

// 语法点按「语法族」上色(与句子成分配色呼应)
const _FAM: [RegExp, string, string][] = [
  [/并列/, '#e0529c', '#fce9f3'],
  [/名词性|宾语从句|主语从句|表语从句|同位语/, '#8a5cf0', '#f0ebfe'],
  [/定语/, '#1f9d6b', '#e6f6ef'],
  [/状语/, '#e08a2f', '#fcf0e2'],
  [/非谓语|不定式|分词|动名词/, '#0e9aa7', '#e3f5f6'],
  [/介词/, '#2f9fc4', '#e5f3f9'],
  [/主语|谓语|宾语|表语|主干|主句/, '#3b6fe0', '#eaf0fd'],
]
function famColor(name?: string): { color: string; tint: string } {
  for (const [re, color, tint] of _FAM) if (re.test(name || '')) return { color, tint }
  return { color: '#6b7688', tint: '#eef0f4' }
}
const gpList = computed(() => (analysis.value?.grammar_points || []).map(g => ({ ...g, ...famColor(g.name) })))

function soon(name: string) { uni.showToast({ title: name + '·敬请期待', icon: 'none' }) }
function go(url: string) { uni.navigateTo({ url }) }

/* ── 收藏 ── */
const favorited = ref(false)
async function toggleFav() {
  const id = items.value[index.value]?.id
  if (!id) return
  const target = !favorited.value
  favorited.value = target  // 乐观更新
  try {
    const r = await favoriteLs(id, target)
    favorited.value = r.favorited
    const it = items.value[index.value]; if (it) it.favorited = r.favorited
  } catch {
    favorited.value = !target
    uni.showToast({ title: '操作失败', icon: 'none' })
  }
}

/* ── 更多:自定义底部弹层 ── */
const moreOpen = ref(false)
function onMore() { moreOpen.value = true }
function moreToggleStruct() { showStruct.value = !showStruct.value; moreOpen.value = false }
function moreCopy() {
  moreOpen.value = false
  uni.setClipboardData({ data: detail.value?.text || '', success: () => uni.showToast({ title: '已复制', icon: 'success' }) })
}
function moreDiff() {
  moreOpen.value = false
  const c = analysis.value?.complexity
  const content = c
    ? `难度 ${difficulty.value ?? '—'} · ${diffLevel.value.label}\n从句 ${c.clause_count ?? '—'} · 树深 ${c.tree_depth ?? '—'} · 依存距离 ${c.mdd ?? '—'} · 词数 ${c.word_count ?? '—'}`
    : `难度 ${difficulty.value ?? '暂无'}`
  uni.showModal({ title: '难度说明', content, showCancel: false })
}
function moreKp() { moreOpen.value = false; openKpDetail() }

/* ── 语法点详解:跳关联考点内容页 ── */
function openKpDetail() {
  const node = detail.value?.nodes?.[0]
  if (!node) { uni.showToast({ title: '本句暂无关联语法点', icon: 'none' }); return }
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${node.node_id}` })
}

/* ── 打卡日历 ── */
const checkinStatus = ref<CheckinStatus | null>(null)
const cal = ref<CheckinCalendar | null>(null)
const calOpen = ref(false)
const calCells = computed(() => {
  const c = cal.value
  if (!c) return [] as { day: number; checked?: boolean; today?: boolean }[]
  const checked = new Set((c.days || []).map(d => d.date))
  const first = new Date(c.year, c.month - 1, 1).getDay()  // 0=周日
  const dim = new Date(c.year, c.month, 0).getDate()
  const now = new Date()
  const curMonth = now.getFullYear() === c.year && now.getMonth() + 1 === c.month
  const cells: { day: number; checked?: boolean; today?: boolean }[] = []
  for (let i = 0; i < first; i++) cells.push({ day: 0 })
  for (let d = 1; d <= dim; d++) {
    const ds = `${c.year}-${String(c.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({ day: d, checked: checked.has(ds), today: curMonth && now.getDate() === d })
  }
  return cells
})
async function openCalendar() {
  calOpen.value = true
  try { cal.value = await getCheckinCalendar() } catch { /* ignore */ }
  try { checkinStatus.value = await getCheckinStatus() } catch { /* ignore */ }
}
async function doCheckin() {
  if (checkinStatus.value?.checked_in_today) return
  try {
    checkinStatus.value = await checkin()
    cal.value = await getCheckinCalendar()
  } catch { uni.showToast({ title: '打卡失败', icon: 'none' }) }
}

/* ── 听原句:首次合成存 COS+回填库,再次直接播库里链接;COS 未配置回退流式 ── */
let audioCtx: UniApp.InnerAudioContext | null = null
const playing = ref(false)
const loadingAudio = ref(false)
const audioUrl = ref<string>('')   // 本句已拿到的直链(库里或刚生成),避免重复请求
function ensureAudio() {
  if (audioCtx) return audioCtx
  audioCtx = uni.createInnerAudioContext()
  audioCtx.onPlay(() => { playing.value = true })
  audioCtx.onEnded(() => { playing.value = false })
  audioCtx.onStop(() => { playing.value = false })
  audioCtx.onError(() => { playing.value = false; uni.showToast({ title: '暂无音频', icon: 'none' }) })
  return audioCtx
}
async function listen() {
  const text = detail.value?.text
  if (!text) return
  const ctx = ensureAudio()
  if (playing.value) { ctx.stop(); return }
  // 1) 已有直链(库里或本次已生成)→ 直接播
  let src = audioUrl.value || detail.value?.audio_url || ''
  // 2) 没有 → 调生成端点(合成→COS→回填库),返回直链
  if (!src) {
    loadingAudio.value = true
    try {
      const r = await getLsAudioUrl(items.value[index.value].id)
      src = r.url || ''
    } catch { /* ignore,走回退 */ }
    finally { loadingAudio.value = false }
  }
  // 3) 仍无直链(COS dev 未配置)→ 回退流式合成接口
  if (src) audioUrl.value = src
  ctx.src = src || ttsSpeakUrl(text)
  ctx.play()
}

async function loadDetail() {
  const it = items.value[index.value]
  if (!it) return
  detail.value = null
  if (playing.value && audioCtx) audioCtx.stop()
  audioUrl.value = ''
  try { detail.value = await getLongSentence(it.id) } catch { /* ignore */ }
  favorited.value = !!(detail.value?.favorited ?? it.favorited)
  // 按脚手架档设默认呈现:看懂=给结构+译文;划结构/输出=先藏起来,学生自己来
  tab.value = 'struct'
  showStruct.value = scaffold.value.struct
  showTranslate.value = scaffold.value.translate
  // 重置理解检测态(每句独立检测)
  checking.value = false; probes.value = []; probeAnswers.value = {}; selfRating.value = ''; result.value = null; submitting.value = false
  transOpen.value = false; transAnswer.value = ''; transResult.value = null; transSubmitting.value = false
  tfStarted.value = false; tfItem.value = null; tfShared.value = []; tfProbes.value = []; tfAnswers.value = {}; tfResult.value = null; tfLoading.value = false; tfSubmitting.value = false
  // R9.4 生词复现:重置 + 拉本句命中词
  vocabHits.value = []; hitWord.value = null; hitProbe.value = null; hitPick.value = ''; hitResult.value = null
  loadVocabHits()
}

/* ── R9.4 生词复现:本句里你在学的未掌握词,顺势轻测 ── */
const vocabHits = ref<VocabHit[]>([])
const hitWord = ref<VocabHit | null>(null)
const hitProbe = ref<ComprehensionProbe | null>(null)
const hitPick = ref('')
const hitResult = ref<{ correct: boolean; correct_answer: string; misconception?: string | null } | null>(null)
async function loadVocabHits() {
  const id = items.value[index.value]?.id
  if (!id) return
  try { vocabHits.value = (await getVocabHits(id)).hits } catch { vocabHits.value = [] }
}
async function openHit(h: VocabHit) {
  hitWord.value = h; hitProbe.value = null; hitPick.value = ''; hitResult.value = null
  try {
    const r = await getWordProbes(h.word_id)
    hitProbe.value = (r.probes || []).find(p => p.kind === 'cloze') || (r.probes || [])[0] || null
    if (!hitProbe.value) uni.showToast({ title: '该词暂无快测', icon: 'none' })
  } catch { uni.showToast({ title: '加载失败', icon: 'none' }) }
}
async function submitHit() {
  if (!hitWord.value || !hitProbe.value || !hitPick.value || hitResult.value) return
  try {
    const r = await submitWordProbe(hitWord.value.word_id, hitProbe.value.key, hitPick.value)
    hitResult.value = { correct: r.correct, correct_answer: r.correct_answer, misconception: r.misconception }
    uni.showToast({ title: r.correct ? '认得出 ✓' : '再记记', icon: 'none' })
  } catch { uni.showToast({ title: '提交失败', icon: 'none' }) }
}
function closeHit() { hitWord.value = null; hitProbe.value = null; hitPick.value = ''; hitResult.value = null }

/* ── 理解检测:过关才算学;θ 实测为主、自评为辅 ── */
async function startCheck() {
  const id = items.value[index.value]?.id
  if (!id) return
  checking.value = true; probeAnswers.value = {}; result.value = null
  try {
    const r = await getComprehension(id)
    probes.value = r.probes || []
    if (!probes.value.length) { uni.showToast({ title: '本句暂不支持检测,可直接学下一句', icon: 'none' }); checking.value = false }
  } catch { probes.value = []; checking.value = false; uni.showToast({ title: '加载检测失败', icon: 'none' }) }
}
function pickProbe(key: string, opt: string) { probeAnswers.value = { ...probeAnswers.value, [key]: opt } }
function toggleSelf(r: 'easy' | 'ok' | 'hard') { selfRating.value = selfRating.value === r ? '' : r }
async function submitCheck() {
  if (!allAnswered.value || submitting.value) return
  const id = items.value[index.value]?.id
  if (!id) return
  submitting.value = true
  try {
    const res = await submitComprehension(id, probeAnswers.value, selfRating.value || undefined)
    result.value = res; recTarget.value = res.target; tier.value = res.tier
    if (res.passed) {
      learnedCount.value++
      uni.showToast({ title: '理解通过,这句学会了 ✓', icon: 'none' })
    } else {
      // 没全懂 → 展开结构+译文帮助理解,稍后复习
      showStruct.value = true; showTranslate.value = true
      uni.showToast({ title: '已加入复习,稍后再帮你巩固', icon: 'none' })
    }
  } catch { uni.showToast({ title: '判分失败', icon: 'none' }) }
  finally { submitting.value = false }
}

/* ── 进阶·短翻译产出项 ── */
function openTrans() { transOpen.value = true; transResult.value = null }
function redoTrans() { transResult.value = null; transAnswer.value = ''; transOpen.value = true }
async function submitTrans() {
  const id = items.value[index.value]?.id
  if (!id || !transAnswer.value.trim() || transSubmitting.value) return
  transSubmitting.value = true
  try {
    const res = await submitTranslateCheck(id, transAnswer.value.trim())
    transResult.value = res; recTarget.value = res.target; tier.value = res.tier
    uni.showToast({ title: res.passed ? '输出达标,水平已加分 ✓' : '已给出逐维点评', icon: 'none' })
  } catch { uni.showToast({ title: '评分失败', icon: 'none' }) }
  finally { transSubmitting.value = false }
}

// ── 试译·语音输入(微信同声传译插件,仅微信端;默认语音,可切键盘,识别中文)────────
const pvMode = ref<'voice' | 'text'>('text')
const pvRecording = ref(false)
const pvCancelZone = ref(false)
// #ifdef MP-WEIXIN
pvMode.value = 'voice'   // 微信端默认语音
function togglePvMode() { pvMode.value = pvMode.value === 'voice' ? 'text' : 'voice' }
let _pvMgr: any = null
let _pvStartAt = 0
let _pvStartY = 0
let _pvBusy = false
let _pvCanceled = false
const PV_CANCEL_DY = 80
function getPvMgr() {
  if (_pvMgr) return _pvMgr
  try {
    const plugin: any = requirePlugin('WechatSI')
    _pvMgr = plugin.getRecordRecognitionManager()
    _pvMgr.onRecognize = () => { /* 中间结果忽略 */ }
    _pvMgr.onStop = (res: any) => {
      pvRecording.value = false; _pvBusy = false
      if (_pvCanceled) { _pvCanceled = false; return }
      const text = ((res && res.result) || '').trim()
      if (!text) { uni.showToast({ title: '没听清,再说一次或打字', icon: 'none' }); return }
      transAnswer.value = transAnswer.value ? `${transAnswer.value}${text}` : text
    }
    _pvMgr.onError = (res: any) => {
      pvRecording.value = false; _pvBusy = false
      if (_pvCanceled) { _pvCanceled = false; return }
      const raw = (res && (res.msg || res.errMsg)) || ''
      uni.showToast({ title: /finish|忙|wait/i.test(raw) ? '识别还在处理,请稍候' : '语音识别失败,请打字', icon: 'none', duration: 2000 })
    }
    return _pvMgr
  } catch (e) { console.warn('[WechatSI requirePlugin 失败]', e); return null }
}
function pvStart(e: any) {
  if (_pvBusy) { uni.showToast({ title: '上一句还在识别,请稍候', icon: 'none' }); return }
  const mgr = getPvMgr()
  if (!mgr) { uni.showToast({ title: '未启用语音插件,请打字', icon: 'none' }); return }
  _pvStartY = e?.touches?.[0]?.clientY ?? e?.changedTouches?.[0]?.clientY ?? 0
  pvCancelZone.value = false; _pvCanceled = false
  pvRecording.value = true; _pvStartAt = Date.now()
  try { mgr.start({ lang: 'zh_CN', duration: 30000 }) }
  catch (e2) { pvRecording.value = false; console.warn('[WechatSI start 失败]', e2); uni.showToast({ title: '无法开始录音,请打字', icon: 'none' }) }
}
function pvMove(e: any) {
  if (!pvRecording.value) return
  const y = e?.touches?.[0]?.clientY ?? 0
  pvCancelZone.value = (_pvStartY - y) > PV_CANCEL_DY
}
function pvEnd() {
  if (!pvRecording.value) return
  pvRecording.value = false
  const wasCancel = pvCancelZone.value
  pvCancelZone.value = false
  if (Date.now() - _pvStartAt < 400) {
    _pvCanceled = true
    try { getPvMgr()?.stop() } catch { /* ignore */ }
    uni.showToast({ title: '按住说话时间太短', icon: 'none' }); return
  }
  if (wasCancel) {
    _pvCanceled = true
    try { getPvMgr()?.stop() } catch { /* ignore */ }
    uni.showToast({ title: '已取消', icon: 'none' }); return
  }
  _pvBusy = true
  const mgr = getPvMgr()
  if (mgr) mgr.stop()
}
// #endif

/* ── 迁移挑战:同结构新句,区分「记住题 vs 会技能」 ── */
async function startTransfer() {
  const id = items.value[index.value]?.id
  if (!id) return
  tfStarted.value = true; tfLoading.value = true; tfResult.value = null; tfAnswers.value = {}
  try {
    const r = await getTransfer(id, items.value.map(i => i.id))
    tfItem.value = r.item; tfShared.value = r.shared || []; tfProbes.value = r.probes || []
  } catch { tfItem.value = null; uni.showToast({ title: '加载迁移句失败', icon: 'none' }) }
  finally { tfLoading.value = false }
}
function pickTf(key: string, opt: string) { tfAnswers.value = { ...tfAnswers.value, [key]: opt } }
async function submitTf() {
  const originId = items.value[index.value]?.id
  if (!originId || !tfItem.value || !tfAllAnswered.value || tfSubmitting.value) return
  tfSubmitting.value = true
  try {
    const res = await submitTransfer(originId, tfItem.value.id, tfAnswers.value)
    tfResult.value = res; recTarget.value = res.target; tier.value = res.tier
    uni.showToast({ title: res.verdict === 'transferred' ? '迁移成功,真掌握 ✓' : '换句卡住了,已加入复习', icon: 'none' })
  } catch { uni.showToast({ title: '判分失败', icon: 'none' }) }
  finally { tfSubmitting.value = false }
}

function prev() { if (index.value > 0) { index.value--; loadDetail() } }

// 自适应:历史里还有就前进;到末尾就按学生水平拉新推荐
async function next() {
  // 过关才算学:当前句须先完成理解检测(通过或未过都可继续,未过的已入复习)
  if (!result.value) {
    uni.showToast({ title: '先做「检测理解」再学下一句哦', icon: 'none' })
    if (!checking.value) startCheck()
    return
  }
  if (index.value < items.value.length - 1) { index.value++; loadDetail(); return }
  if (recing.value) return
  recing.value = true
  try {
    const r = await nextLongSentence(items.value.map(i => i.id))
    if (r.item) {
      items.value.push(r.item); index.value = items.value.length - 1
      recTarget.value = r.target; tier.value = r.tier; isReview.value = r.review; loadDetail()
    } else {
      uni.showToast({ title: '今日推荐已学完,休息一下~', icon: 'none' })
    }
  } catch { uni.showToast({ title: '推荐失败', icon: 'none' }) }
  finally { recing.value = false }
}

onLoad(async () => {
  try {
    const r = await nextLongSentence([])
    if (r.item) { items.value = [r.item]; index.value = 0; recTarget.value = r.target; tier.value = r.tier; isReview.value = r.review; await loadDetail() }
  } finally { loading.value = false }
  try { checkinStatus.value = await getCheckinStatus() } catch { /* ignore */ }
})
</script>

<style scoped>
.ls-page { min-height: 100vh; background: #f4f6fa; }
.center-tip { text-align: center; color: #999; padding-top: 200rpx; }
.scroll { padding: 20rpx 20rpx 0; }

/* 顶部进度 */
.header { display: flex; align-items: center; gap: 18rpx; margin-bottom: 20rpx; }
.prog { flex: 1; }
.prog-label { font-size: 26rpx; color: #666; }
.prog-hint { font-size: 22rpx; color: var(--c-primary); }

/* 脚手架引导条 */
.scaffold { display: flex; align-items: center; gap: 12rpx; padding: 14rpx 16rpx; border-radius: 14rpx; margin-bottom: 16rpx; }
.scaffold.intro { background: #e9f7ef; }
.scaffold.build { background: var(--c-primary-faint); }
.scaffold.challenge { background: #fdf2e3; }
.sc-ic { width: 32rpx; height: 32rpx; flex-shrink: 0; }
.sc-body { flex: 1; display: flex; flex-direction: column; }
.sc-label { font-size: 24rpx; font-weight: 700; }
.scaffold.intro .sc-label { color: #1f9d6b; }
.scaffold.build .sc-label { color: var(--c-primary); }
.scaffold.challenge .sc-label { color: #d0860f; }
.sc-tip { font-size: 22rpx; color: #6b7178; margin-top: 2rpx; }
.sc-act { flex-shrink: 0; font-size: 22rpx; color: var(--c-primary); background: #fff; border-radius: 18rpx; padding: 6rpx 16rpx; }

/* 理解检测:过关才算学 */
.check { margin-top: 18rpx; padding-top: 16rpx; border-top: 1rpx solid #f0f2f5; }
.check-cta { display: flex; align-items: center; justify-content: center; gap: 10rpx; background: var(--c-primary-faint); color: var(--c-primary); border-radius: 16rpx; padding: 18rpx 0; font-size: 27rpx; font-weight: 600; }
.check-cta:active { opacity: .8; }
.check-cta-ic.ic { width: 34rpx; height: 34rpx; }
/* 检测题 */
.probe { margin-bottom: 18rpx; }
.probe-q { display: block; font-size: 25rpx; color: #2a3138; font-weight: 600; line-height: 1.5; margin-bottom: 12rpx; }
.probe-opts { display: flex; flex-direction: column; gap: 10rpx; }
.probe-opt { font-size: 24rpx; color: #4a5057; background: #f5f7fa; border: 2rpx solid transparent; border-radius: 12rpx; padding: 14rpx 18rpx; line-height: 1.5; font-family: Georgia, 'Times New Roman', serif; }
.probe-opt.on { background: var(--c-primary-faint); border-color: var(--c-primary); color: var(--c-primary); }
.probe-opt:active { opacity: .8; }
/* 可选自评(辅) */
.self { display: flex; align-items: center; flex-wrap: wrap; gap: 10rpx; margin: 6rpx 0 16rpx; }
.self-q { font-size: 22rpx; color: #9aa3b0; }
.self-btn { font-size: 23rpx; padding: 6rpx 18rpx; border-radius: 20rpx; background: #f3f5f8; color: #8a93a3; }
.self-btn.easy.on { color: #1f9d6b; background: #e9f7ef; }
.self-btn.ok.on { color: var(--c-primary); background: var(--c-primary-faint); }
.self-btn.hard.on { color: #e2504a; background: #fdecea; }
/* 提交 */
.check-submit { text-align: center; background: var(--g-primary); color: var(--c-on-primary); font-size: 28rpx; font-weight: 700; padding: 18rpx 0; border-radius: 32rpx; box-shadow: var(--shadow-primary); }
.check-submit.dis { background: #d7dde6; color: #fff; box-shadow: none; }
.check-submit:active { opacity: .9; }
/* 结果 */
.check-result { border-radius: 16rpx; padding: 18rpx; }
.check-result.pass { background: #e9f7ef; }
.check-result.fail { background: #fdf2e3; }
.cr-head { display: flex; align-items: center; gap: 10rpx; margin-bottom: 12rpx; }
.cr-ic.ic { width: 34rpx; height: 34rpx; flex-shrink: 0; }
.cr-title { font-size: 25rpx; font-weight: 700; }
.check-result.pass .cr-title { color: #1f9d6b; }
.check-result.fail .cr-title { color: #d0860f; }
.cr-probe { display: flex; gap: 10rpx; padding: 10rpx 0; }
.cr-tag { flex-shrink: 0; font-size: 24rpx; font-weight: 700; color: #e2504a; width: 28rpx; text-align: center; }
.cr-probe.ok .cr-tag { color: #1f9d6b; }
.cr-body { flex: 1; display: flex; flex-direction: column; gap: 3rpx; }
.cr-label { font-size: 23rpx; font-weight: 600; color: #3a414a; }
.cr-ans { font-size: 22rpx; color: #6b7178; line-height: 1.5; font-family: Georgia, 'Times New Roman', serif; }
.cr-mis { font-size: 22rpx; color: #c0792a; line-height: 1.55; }
/* 进阶·短翻译产出项 */
.prod { margin-top: 14rpx; padding-top: 14rpx; border-top: 1rpx dashed #e6e9ef; }
.prod-cta { display: flex; align-items: center; justify-content: center; gap: 8rpx; background: #fdf2e3; color: #d0860f; border-radius: 14rpx; padding: 14rpx 0; font-size: 24rpx; font-weight: 600; }
.prod-cta:active { opacity: .8; }
.prod-cta-ic.ic { width: 30rpx; height: 30rpx; }
.prod-input { width: 100%; box-sizing: border-box; min-height: 120rpx; background: #f7f9fc; border-radius: 12rpx; padding: 16rpx; font-size: 25rpx; color: #2a3138; line-height: 1.6; }
/* 试译·语音输入(微信端) */
.pv-row { display: flex; align-items: flex-start; gap: 12rpx; }
.pv-toggle { flex-shrink: 0; width: 72rpx; height: 72rpx; border-radius: 50%; background: var(--c-bg-soft, #eef2f7); display: flex; align-items: center; justify-content: center; }
.pv-hold { flex: 1; height: 96rpx; line-height: 96rpx; text-align: center; border-radius: 48rpx; background: #fff; border: 2rpx solid var(--c-border, #dfe5ee); font-size: 28rpx; font-weight: 700; color: #2a3138; }
.pv-hold.holding { background: var(--c-primary-faint, #e8f1ff); border-color: var(--c-primary, #3d8bf5); color: var(--c-primary-deep, #2f6fd6); }
.pv-grow { flex: 1; min-height: 96rpx; }
.rec-mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 28rpx; z-index: 60; }
.rec-panel { width: 240rpx; height: 240rpx; border-radius: 36rpx; background: rgba(40,44,52,.92); display: flex; align-items: center; justify-content: center; box-shadow: 0 12rpx 48rpx rgba(0,0,0,.3); }
.rec-panel.cancel { background: rgba(214,69,69,.95); }
.rec-wave { display: flex; align-items: center; gap: 10rpx; height: 90rpx; }
.wbar { width: 12rpx; height: 28rpx; border-radius: 6rpx; background: #7ee0a8; animation: wave .8s ease-in-out infinite; }
@keyframes wave { 0%,100% { height: 24rpx; opacity:.6 } 50% { height: 84rpx; opacity:1 } }
.rec-cancel-ico { color: #fff; font-size: 96rpx; font-weight: 800; }
.rec-tip { font-size: 26rpx; color: #fff; background: rgba(0,0,0,.4); padding: 10rpx 28rpx; border-radius: 30rpx; }
.rec-tip.cancel { background: rgba(214,69,69,.9); }
.prod-submit { margin-top: 12rpx; text-align: center; background: var(--g-primary); color: var(--c-on-primary); font-size: 26rpx; font-weight: 700; padding: 16rpx 0; border-radius: 30rpx; box-shadow: var(--shadow-primary); }
.prod-submit.dis { background: #d7dde6; color: #fff; box-shadow: none; }
.prod-result { background: #f7f9fc; border-radius: 14rpx; padding: 16rpx; }
.pr-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 12rpx; }
.pr-score { font-size: 34rpx; font-weight: 800; color: #d0860f; }
.pr-score.pass { color: #1f9d6b; }
.pr-verdict { font-size: 24rpx; font-weight: 700; color: #d0860f; }
.pr-verdict.pass { color: #1f9d6b; }
.pr-redo { margin-left: auto; font-size: 22rpx; color: var(--c-primary); background: var(--c-primary-faint); border-radius: 18rpx; padding: 6rpx 18rpx; }
.pr-dim { padding: 8rpx 0; }
.pr-dim-top { display: flex; align-items: center; justify-content: space-between; }
.pr-dim-label { font-size: 24rpx; color: #3a414a; font-weight: 600; }
.pr-dots { display: flex; gap: 6rpx; }
.pr-dot { width: 18rpx; height: 18rpx; border-radius: 50%; background: #e2e6ee; }
.pr-dot.on { background: #1f9d6b; }
.pr-dim-note { display: block; font-size: 21rpx; color: #8a93a3; line-height: 1.5; margin-top: 3rpx; }
.pr-fb { margin-top: 10rpx; padding: 12rpx 14rpx; background: #fff; border-radius: 10rpx; font-size: 23rpx; color: #6b7178; line-height: 1.6; }
.pr-fb-lb { font-size: 20rpx; color: #fff; background: #a7b0c0; border-radius: 8rpx; padding: 3rpx 12rpx; margin-right: 10rpx; }
/* 迁移挑战 */
.tf { margin-top: 14rpx; padding-top: 14rpx; border-top: 1rpx dashed #e6e9ef; }
.tf-cta { display: flex; align-items: center; justify-content: center; gap: 8rpx; background: #eef0fe; color: #5a5cf0; border-radius: 14rpx; padding: 14rpx 0; font-size: 24rpx; font-weight: 600; }
.tf-cta:active { opacity: .8; }
.tf-cta-ic.ic { width: 30rpx; height: 30rpx; }
.tf-loading, .tf-empty { text-align: center; color: #9aa3b0; font-size: 24rpx; padding: 16rpx 0; }
.tf-card { background: #f7f8fe; border-radius: 14rpx; padding: 16rpx; }
.tf-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8rpx; margin-bottom: 12rpx; }
.tf-badge { font-size: 21rpx; color: #fff; background: #6366f1; border-radius: 8rpx; padding: 4rpx 14rpx; font-weight: 600; }
.tf-tag { font-size: 21rpx; color: #5a5cf0; background: #e6e7fd; border-radius: 8rpx; padding: 4rpx 14rpx; }
.tf-sent { display: block; font-size: 30rpx; line-height: 1.7; color: #2a3138; font-family: Georgia, 'Times New Roman', serif; margin-bottom: 14rpx; }
.tf-result { border-radius: 12rpx; padding: 14rpx; }
.tf-result.transferred { background: #e9f7ef; }
.tf-result.memorized { background: #fdf2e3; }
.tf-rhead { display: flex; align-items: center; gap: 10rpx; margin-bottom: 8rpx; }
.tf-ric.ic { width: 34rpx; height: 34rpx; flex-shrink: 0; }
.tf-rtitle { font-size: 25rpx; font-weight: 700; }
.tf-result.transferred .tf-rtitle { color: #1f9d6b; }
.tf-result.memorized .tf-rtitle { color: #d0860f; }
.tf-rdesc { display: block; font-size: 22rpx; color: #6b7178; line-height: 1.6; margin-bottom: 8rpx; }
.prog-num { color: var(--c-primary); font-weight: 700; }
.prog-bar { height: 10rpx; background: #e5e9f0; border-radius: 8rpx; margin-top: 12rpx; overflow: hidden; }
.prog-fill { height: 100%; background: var(--c-primary); border-radius: 8rpx; transition: width .3s; }
.streak { display: flex; align-items: center; gap: 6rpx; background: #fff; border: 1rpx solid #e8ebf1; border-radius: 28rpx; padding: 8rpx 20rpx; font-size: 23rpx; color: #666; }
.streak-ic.ic { width: 28rpx; height: 28rpx; margin-right: 4rpx; }

.card { background: #fff; border-radius: 24rpx; padding: 28rpx; margin-bottom: 20rpx; box-shadow: 0 2rpx 16rpx rgba(0,0,0,.05); }

/* 句子卡头:翻页 + 来源 + 难度环 */
.sc-top { display: flex; align-items: center; gap: 14rpx; margin-bottom: 20rpx; }
.nav { display: flex; align-items: center; gap: 6rpx; }
.nav-btn { width: 44rpx; height: 44rpx; line-height: 40rpx; text-align: center; border: 1rpx solid #e3e7ee; border-radius: 50%; color: #555; font-size: 32rpx; }
.nav-btn.dis { opacity: .35; }
.nav-cur { font-size: 24rpx; color: #444; min-width: 110rpx; text-align: center; }
.src-tag { background: #f0f2f6; color: #777; font-size: 22rpx; padding: 5rpx 16rpx; border-radius: 24rpx; }
.review-tag { background: #fdf2e3; color: #d0860f; font-size: 22rpx; padding: 5rpx 16rpx; border-radius: 24rpx; }
.sc-spacer { flex: 1; }
.diff-ring { display: flex; flex-direction: column; align-items: center; gap: 2rpx; }
.dr-num { width: 78rpx; height: 78rpx; line-height: 72rpx; text-align: center; border-radius: 50%; border: 5rpx solid; font-size: 34rpx; font-weight: 700; }
.dr-lb { font-size: 20rpx; color: #999; }
.diff-ring.hard .dr-num { border-color: #e2504a; color: #e2504a; }
.diff-ring.mid .dr-num { border-color: #e89a1f; color: #d0860f; }
.diff-ring.easy .dr-num { border-color: #1f9d6b; color: #1f9d6b; }

/* 原句:连续流式段落(行内文本自然排满换行);序号锚在每段首词下方(保持原设计) */
.sentence { font-family: Georgia, 'Times New Roman', 'Songti SC', serif; font-size: 32rpx; line-height: 3; transition: background .2s; }
.sentence.eye { background: #f3f0e3; border-radius: 14rpx; padding: 16rpx 20rpx; }
.seg { border-bottom: 2rpx dashed; padding-bottom: 6rpx; }
.fw { position: relative; }
.badge { position: absolute; left: 50%; top: 130%; transform: translateX(-50%); width: 32rpx; height: 32rpx; line-height: 32rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 18rpx; }
.plain { font-size: 32rpx; line-height: 1.9; }
.trans { margin: 16rpx 0 0; padding: 18rpx; background: #f7f9fc; border-radius: 14rpx; font-size: 28rpx; color: #555; line-height: 1.7; }

/* 颜色图例(内联) */
.legend { margin-top: 18rpx; padding-top: 16rpx; border-top: 1rpx solid #f0f2f5; display: flex; flex-wrap: wrap; gap: 12rpx 22rpx; }
.lg-item { display: flex; align-items: center; gap: 8rpx; }
.lg-dot { width: 18rpx; height: 18rpx; border-radius: 5rpx; flex-shrink: 0; }
.lg-tx { font-size: 23rpx; color: #777; }

/* 图标见全局 styles/icons.scss;此处仅放页面专属尺寸覆盖 */
.stype-ic.ic { width: 30rpx; height: 30rpx; }

/* 工具栏:一排图标按钮 */
.toolbar { display: flex; gap: 8rpx; margin-top: 20rpx; }
.tb { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8rpx; padding: 14rpx 0; background: #f5f7fa; border-radius: 16rpx; }
.tb-ic.ic { width: 38rpx; height: 38rpx; }
.tb-az { font-size: 30rpx; font-weight: 600; color: var(--c-primary); line-height: 38rpx; }
.tb-tx { font-size: 20rpx; color: #888; }
.tb.on { background: var(--c-primary-faint); }
.tb.on .tb-tx { color: var(--c-primary); }

/* Tabs:分段控件 */
.seg-tabs { display: flex; gap: 6rpx; background: #eef1f6; border-radius: 16rpx; padding: 6rpx; margin-bottom: 24rpx; }
.seg-tab { flex: 1; text-align: center; font-size: 26rpx; color: #888; padding: 16rpx 0; border-radius: 12rpx; }
.seg-tab.on { background: #fff; color: var(--c-primary); font-weight: 700; box-shadow: 0 1rpx 6rpx rgba(0,0,0,.06); }
.tab-body { min-height: 80rpx; }

/* 句子结构:主干 → 从句 紧凑树 */
.st { display: flex; flex-direction: column; align-items: center; padding: 6rpx 0 4rpx; }
.st-trunk { background: var(--c-primary-faint); color: var(--c-primary); font-size: 25rpx; font-weight: 600; padding: 14rpx 22rpx; border-radius: 14rpx; max-width: 100%; box-sizing: border-box; text-align: center; line-height: 1.5; }
.st-arrow { color: #c2c8d2; font-size: 30rpx; line-height: 1; margin: 10rpx 0; }
.st-children { display: flex; flex-wrap: wrap; justify-content: center; gap: 16rpx; width: 100%; }
.st-clause { flex: 1 1 44%; min-width: 240rpx; border: 1rpx solid; border-radius: 14rpx; padding: 14rpx 16rpx; box-sizing: border-box; }
.st-chead { display: flex; align-items: center; gap: 10rpx; margin-bottom: 6rpx; }
.st-cno { width: 28rpx; height: 28rpx; line-height: 28rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 18rpx; flex-shrink: 0; }
.st-ctype { font-size: 23rpx; font-weight: 700; }
.st-ctext { font-size: 23rpx; color: #6b7178; line-height: 1.5; }

/* 句子成分:标签 chip + 值 */
.comp-row { display: flex; align-items: flex-start; gap: 12rpx; padding: 14rpx 16rpx; background: #f7f9fc; border-radius: 12rpx; margin-bottom: 10rpx; }
.comp-label { flex-shrink: 0; font-size: 21rpx; color: var(--c-primary); background: var(--c-primary-faint); border-radius: 8rpx; padding: 5rpx 14rpx; }
.comp-val { flex: 1; font-size: 24rpx; color: #4a5057; line-height: 1.55; font-family: Georgia, 'Times New Roman', serif; }
/* 重点词汇:卡片 */
.word-row { padding: 14rpx 16rpx; background: #f7f9fc; border-radius: 12rpx; margin-bottom: 10rpx; }
.word-head { display: flex; align-items: baseline; gap: 12rpx; }
.word { font-size: 27rpx; font-weight: 700; color: #333; font-family: Georgia, 'Times New Roman', serif; }
.word-pos { font-size: 20rpx; color: #8a93a3; background: #e9edf3; border-radius: 6rpx; padding: 2rpx 10rpx; }
.word-mean { display: block; font-size: 23rpx; color: #6b7178; margin-top: 6rpx; line-height: 1.55; }
/* 语法点:按语法族上色的浅底卡 + 同色标题 */
.gp-row { padding: 16rpx 18rpx; border-radius: 14rpx; margin-bottom: 10rpx; }
.gp-name { display: block; font-size: 25rpx; font-weight: 700; }
.gp-exp { display: block; font-size: 23rpx; color: #6b7178; margin-top: 6rpx; line-height: 1.6; }
.empty { color: #bbb; font-size: 26rpx; }

/* 结构解析 */
.sec-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.sec-title { font-size: 30rpx; font-weight: 700; border-left: 6rpx solid var(--c-primary); padding-left: 14rpx; }
.link { font-size: 24rpx; color: var(--c-primary); background: var(--c-primary-faint); padding: 8rpx 18rpx; border-radius: 24rpx; }
.stype { display: flex; align-items: center; gap: 8rpx; background: var(--c-primary-faint); border-radius: 12rpx; padding: 12rpx 16rpx; margin-bottom: 18rpx; }
.stype-ic { font-size: 24rpx; }
.stype-tx { font-size: 25rpx; font-weight: 600; color: var(--c-primary); }
/* 逐条解析:时间线 */
.tl { padding: 2rpx 0; }
.tl-row { display: flex; gap: 14rpx; position: relative; padding-bottom: 20rpx; }
.tl-rail { position: relative; flex-shrink: 0; width: 32rpx; display: flex; justify-content: center; }
.tl-dot { width: 30rpx; height: 30rpx; line-height: 30rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 18rpx; }
.tl-row:not(:last-child) .tl-rail::before { content: ''; position: absolute; top: 32rpx; bottom: -14rpx; left: 50%; transform: translateX(-50%); width: 2rpx; background: #e9ecf2; }
.tl-text { flex: 1; font-size: 24rpx; color: #6b7178; line-height: 1.65; padding-top: 3rpx; }
.summary { display: block; margin-top: 6rpx; padding: 14rpx 16rpx; background: #f7f9fc; border-radius: 12rpx; font-size: 24rpx; color: #6b7178; line-height: 1.7; }
.summary-lb { font-size: 20rpx; color: #fff; background: #a7b0c0; border-radius: 8rpx; padding: 3rpx 12rpx; margin-right: 10rpx; }
.footer-space { height: 140rpx; }

/* 更多:底部弹层 */
/* R9.4 生词复现 chip + 快测弹层 */
.vhits { display: flex; align-items: center; flex-wrap: wrap; gap: 10rpx; margin-top: 16rpx; padding-top: 14rpx; border-top: 1rpx solid #f0f2f5; }
.vhits-lb { font-size: 22rpx; color: #9aa3b0; }
.vhit-chip { font-size: 24rpx; color: #5a5cf0; background: #eef0fe; border-radius: 20rpx; padding: 6rpx 18rpx; font-family: Georgia, 'Times New Roman', serif; }
.vhit-chip:active { opacity: .8; }
.hit-sheet { width: 100%; background: #fff; border-radius: 28rpx 28rpx 0 0; padding: 24rpx 28rpx calc(24rpx + env(safe-area-inset-bottom)); }
.hit-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14rpx; }
.hit-word { font-size: 36rpx; font-weight: 800; font-family: Georgia, 'Times New Roman', serif; }
.hit-close { font-size: 32rpx; color: #999; padding: 0 10rpx; }
.hit-tip { color: #9aa3b0; font-size: 24rpx; padding: 14rpx 0; }
.hit-fb { margin-top: 12rpx; font-size: 24rpx; line-height: 1.6; }
.hit-fb.ok { color: #1f9d6b; }
.hit-fb.no { color: #e2504a; }
.more-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 99; display: flex; align-items: flex-end; }
.more-sheet { width: 100%; background: #fff; border-radius: 28rpx 28rpx 0 0; padding: 12rpx 0 calc(12rpx + env(safe-area-inset-bottom)); }
.more-grab { width: 64rpx; height: 8rpx; background: #e2e6ee; border-radius: 8rpx; margin: 8rpx auto 14rpx; }
.more-item { display: flex; align-items: center; gap: 18rpx; padding: 26rpx 36rpx; }
.more-item:active { background: #f5f7fa; }
.mi-ic.ic { width: 38rpx; height: 38rpx; }
.mi-tx { flex: 1; font-size: 28rpx; color: #2a3138; }
.mi-arrow { color: #c2c8d2; font-size: 30rpx; }
.more-cancel { margin-top: 10rpx; border-top: 12rpx solid #f4f6fa; padding: 28rpx 0; text-align: center; font-size: 28rpx; color: #888; }
.more-cancel:active { background: #f5f7fa; }

/* 打卡日历弹层 */
.cal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 99; }
.cal-card { width: 600rpx; background: #fff; border-radius: 24rpx; padding: 30rpx; }
.cal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20rpx; }
.cal-title { font-size: 32rpx; font-weight: 800; display: flex; align-items: center; }
.cal-title-ic.ic { width: 32rpx; height: 32rpx; margin-right: 8rpx; }
.cal-close { font-size: 32rpx; color: #999; padding: 0 10rpx; }
.cal-stats { display: flex; justify-content: space-around; margin-bottom: 24rpx; }
.cal-stat { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.cs-num { font-size: 44rpx; font-weight: 800; color: var(--c-primary); }
.cs-lb { font-size: 22rpx; color: #888; }
.cal-grid { display: flex; flex-wrap: wrap; }
.cal-wd { width: 14.28%; text-align: center; font-size: 22rpx; color: #aaa; padding: 8rpx 0; }
.cal-cell { width: 14.28%; height: 64rpx; display: flex; align-items: center; justify-content: center; font-size: 24rpx; color: #555; }
.cal-cell.blank { visibility: hidden; }
.cal-cell.checked { color: #fff; }
.cal-cell.checked text { background: var(--c-primary); width: 48rpx; height: 48rpx; line-height: 48rpx; text-align: center; border-radius: 50%; }
.cal-cell.today text { box-shadow: 0 0 0 2rpx var(--c-gold); border-radius: 50%; }
.cal-foot { margin-top: 24rpx; }
.cal-btn { display: block; text-align: center; background: var(--g-primary); color: #fff; font-size: 30rpx; font-weight: 700; padding: 22rpx 0; border-radius: 44rpx; box-shadow: var(--shadow-primary); }
.cal-btn.done { background: #e8eef6; color: #9aa6b6; box-shadow: none; }

/* 底部固定 */
.footer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; display: flex; align-items: center; gap: 20rpx; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: #fff; box-shadow: 0 -2rpx 14rpx rgba(0,0,0,.05); }
.foot-side { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.fs-ic.ic { width: 42rpx; height: 42rpx; }
.fs-tx { font-size: 22rpx; color: #666; }
.foot-main { flex: 1; background: var(--g-primary); color: var(--c-on-primary); text-align: center; font-size: 32rpx; font-weight: 700; padding: 22rpx 0; border-radius: 44rpx; box-shadow: var(--shadow-primary); }
</style>
