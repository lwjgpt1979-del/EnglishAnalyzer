<!-- src/pages/vocabulary/index.vue 词力通背词 -->
<template>
  <view class="vocab-page">
    <view v-if="loading" class="center-tip">加载今日任务…</view>

    <view v-else-if="phase === 'empty'">
      <view v-if="cal" class="checkin-panel">
        <view class="cp-summary">连续 {{ cal.current_streak }} 天 · 最高 {{ cal.longest_streak }} 天</view>
        <view class="cp-badges">
          <text v-for="b in cal.badges" :key="b.level" class="cp-badge" :class="{ on: b.unlocked }">
            {{ b.level === 'bronze' ? '🥉' : b.level === 'silver' ? '🥈' : '🥇' }}{{ b.name }}
          </text>
        </view>
        <view class="cp-grid">
          <view v-for="(c, i) in calCells" :key="i" class="cp-cell"
                :class="{ checked: c.checked, missable: c.missable, blank: !c.day }"
                @tap="c.missable ? onMakeUp(c.date) : null">
            <text v-if="c.day">{{ c.checked ? '🔥' : c.day }}</text>
            <text v-if="c.wrong > 0" class="cell-wrong">{{ c.wrong }}</text>
          </view>
        </view>
        <view class="cp-hint">点亮灰色日期可补签</view>
      </view>
      <view class="center-tip">🎉 暂时没有待学/待复习的单词
        <view class="done-set">每组 {{ wordsPerGroup }} 词 · 每组 {{ repsPerGroup }} 遍 <view class="gear-inline" @tap="openSettings" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-settings" style="width:26rpx;height:26rpx" /><text>设置</text></view><view class="gear-inline" @tap="openAddWord" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-plus" style="width:26rpx;height:26rpx" /><text>添加生词</text></view></view>
      </view>
    </view>

    <!-- 学习/复习阶段：词卡（图左+词右，例句/短语，跟读·发音一行）-->
    <view v-else-if="phase === 'study' || phase === 'review'" class="card">
      <view class="study-hd">
        <text class="progress-hint">{{ isReview ? '复习词' : '学新词' }} {{ cardIdx + 1 }} / {{ cardList.length }}<text v-if="repsPerGroup > 1" class="rep-tag"> · 第{{ currentRep }}/{{ repsPerGroup }}遍</text></text>
        <view class="hd-right">
          <view class="seq-toggle" :class="{ on: readSeq }" @tap="readSeq = !readSeq" style="display:flex;align-items:center;gap:6rpx">
            <view class="ic ic-volume" style="width:28rpx;height:28rpx" /><text>连读</text>
          </view>
          <view class="gear" @tap="openSettings" style="display:flex;align-items:center"><view class="ic ic-settings" style="width:32rpx;height:32rpx" /></view>
        </view>
      </view>

      <!-- 图左 + 词/音标/释义右 -->
      <view class="wc-top">
        <image v-if="firstImage(curStudy)" class="wc-img" :src="firstImage(curStudy)!" mode="aspectFit" />
        <view v-else class="wc-img wc-img-empty"><text>🖼️</text></view>
        <view class="wc-info">
          <text class="wc-word">{{ curStudy.word }}</text>
          <text v-if="curStudy.phonetic" class="wc-phon">/{{ cleanPhon(curStudy.phonetic) }}/</text>
          <text v-for="(d, i) in defList(curStudy)" :key="i" class="wc-mean">{{ d }}</text>
        </view>
      </view>

      <!-- 例句 -->
      <view v-if="firstExample(curStudy)" class="wc-row">
        <text class="wc-tag">例句</text>
        <view class="wc-rowtext">
          <text class="wc-en">{{ firstExample(curStudy)!.en }}</text>
          <text v-if="firstExample(curStudy)!.zh" class="wc-zh">{{ firstExample(curStudy)!.zh }}</text>
        </view>
      </view>
      <!-- 短语 -->
      <view v-if="firstPhrase(curStudy)" class="wc-row">
        <text class="wc-tag">短语</text>
        <view class="wc-rowtext">
          <text class="wc-en">{{ firstPhrase(curStudy)!.en }}</text>
          <text v-if="firstPhrase(curStudy)!.zh" class="wc-zh">{{ firstPhrase(curStudy)!.zh }}</text>
        </view>
      </view>

      <!-- 单词发音 + 跟读：同一行 -->
      <view class="wc-btns">
        <view class="wc-btn" @tap="playCard(curStudy)" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-volume" style="width:30rpx;height:30rpx" /><text>单词发音</text></view>
        <view class="wc-btn primary" @tap="openShadow(firstExample(curStudy)?.en || curStudy.word)" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-mic" style="width:30rpx;height:30rpx;filter:brightness(0) invert(1)" /><text>跟读</text><view v-if="!ent.can('vocab.shadow')" class="ic ic-lock" style="width:28rpx;height:28rpx;filter:brightness(0) invert(1)" /></view>
      </view>

      <!-- R9.1 理解检测·语境填空(接收:语境里认得出吗)-->
      <view class="probe-box">
        <view v-if="!probeOpen" class="probe-cta" @tap="openProbe">
          <view class="ic ic-brain" style="width:30rpx;height:30rpx" /><text>检测理解 · 语境里认得出吗</text>
        </view>
        <view v-else>
          <view v-if="probeLoading" class="probe-tip">加载中…</view>
          <view v-else-if="!probes.length" class="probe-tip">该词暂无语境检测</view>
          <view v-else>
            <view v-for="p in probes" :key="p.key" class="probe-item">
              <text class="probe-q">{{ p.prompt }}</text>
              <view class="probe-opts">
                <text v-for="(o, i) in p.options" :key="i" class="probe-opt"
                  :class="{ on: probePick[p.key] === o,
                            ok: probeResults[p.key] && o === probeResults[p.key].correct_answer,
                            no: probeResults[p.key] && probePick[p.key] === o && o !== probeResults[p.key].correct_answer }"
                  @tap="pickProbe(p.key, o)">{{ o }}</text>
              </view>
              <view v-if="!probeResults[p.key]" class="probe-submit" :class="{ dis: !probePick[p.key] }" @tap="submitProbe(p.key)">提交</view>
              <view v-else class="probe-fb" :class="probeResults[p.key].correct ? 'ok' : 'no'">
                <text>{{ probeResults[p.key].correct ? '✓ 理解正确' : ('✗ 正确:' + probeResults[p.key].correct_answer) }}</text>
                <text v-if="probeResults[p.key].misconception" class="probe-mis">{{ probeResults[p.key].misconception }}</text>
              </view>
            </view>
            <!-- 产出·造句(检验「会输出」)-->
            <view v-if="produceTask" class="produce-box">
              <text class="produce-q">✍️ {{ produceTask.prompt }}</text>
              <template v-if="!produceResult">
                <textarea v-model="produceInput" class="produce-input" :maxlength="120"
                  placeholder="用这个词写一句英文" auto-height />
                <view class="probe-submit" :class="{ dis: !produceInput.trim() || produceSubmitting }" @tap="submitProduce">{{ produceSubmitting ? '评分中…' : '提交造句' }}</view>
              </template>
              <view v-else class="produce-result" :class="produceResult.passed ? 'ok' : 'no'">
                <view class="pr-head">
                  <text class="pr-score" :class="{ ok: produceResult.passed }">{{ produceResult.total }}/{{ produceResult.max }}</text>
                  <text class="pr-verdict" :class="{ ok: produceResult.passed }">{{ produceResult.passed ? '输出达标 ✓' : '再打磨' }}</text>
                  <text class="pr-redo" @tap="redoProduce">重写</text>
                </view>
                <view v-for="d in produceResult.dimensions" :key="d.key" class="pr-dim">
                  <text class="pr-dim-label">{{ d.label }}</text>
                  <view class="pr-dots"><text v-for="n in d.max" :key="n" class="pr-dot" :class="{ on: n <= d.score }" /></view>
                  <text v-if="d.note" class="pr-dim-note">{{ d.note }}</text>
                </view>
                <text v-if="produceResult.feedback" class="pr-fb">{{ produceResult.feedback }}</text>
              </view>
            </view>

            <view class="probe-recep">
              <text>接收 {{ Math.round(recep * 100) }}% · 产出 {{ Math.round(prod * 100) }}%</text>
              <text v-if="mastered" class="probe-mastered">已掌握 ✓</text>
            </view>
          </view>
        </view>
      </view>

      <button class="btn-primary" @tap="nextStudy">{{ studyBtnLabel }}</button>
    </view>

    <!-- 测试阶段：4 选 1 -->
    <view v-else-if="phase === 'quiz'" class="card">
      <view class="progress-hint">测试 {{ quizIndex + 1 }} / {{ quizQueue.length }} · 正确 {{ correctCount }}</view>
      <view class="quiz-type">{{ quizTypeLabel }}</view>
      <view class="quiz-prompt">
        <text>{{ curQuiz.prompt }}</text>
        <view v-if="curQuiz.mode !== 'm2w'" class="qp-play" @tap="playWordAudio(curQuiz.prompt)"><view class="ic ic-volume" style="width:36rpx;height:36rpx" /></view>
      </view>

      <!-- 看图选词：4 张图选 1 -->
      <view v-if="curQuiz.mode === 'pic'" class="pic-grid">
        <view
          v-for="(opt, i) in curQuiz.options"
          :key="i"
          class="pic-option"
          :class="optionClass(i)"
          @tap="choose(i)"
        >
          <image :src="opt" mode="aspectFill" class="pic-option-img" />
        </view>
      </view>
      <!-- 文本选项 -->
      <view
        v-else
        v-for="(opt, i) in curQuiz.options"
        :key="i"
        class="option"
        :class="optionClass(i)"
        @tap="choose(i)"
      >
        <text class="opt-text">{{ opt }}</text>
        <view v-if="curQuiz.mode === 'm2w'" class="opt-play" @tap.stop="playWordAudio(opt)"><view class="ic ic-volume" style="width:32rpx;height:32rpx" /></view>
      </view>

      <!-- 答题反馈：对错 + 正确单词(音标/释义/发音) -->
      <view v-if="answered" class="quiz-fb" :class="lastCorrect ? 'ok' : 'no'">
        <view v-if="lastCorrect" class="qfb-ok" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-sparkle" style="width:32rpx;height:32rpx" /><text>答对了！</text></view>
        <view v-else class="qfb-wrong">
          <text class="qfb-label">正确答案</text>
          <text class="qfb-word">{{ quizCard?.word }}</text>
          <text v-if="quizCard?.phonetic" class="qfb-phon">/{{ cleanPhon(quizCard?.phonetic) }}/</text>
          <text class="qfb-mean">{{ quizCard ? primaryMeaning(quizCard) : '' }}</text>
          <view class="qfb-play" @tap="playWordAudio(quizCard?.word)"><view class="ic ic-volume" style="width:34rpx;height:34rpx" /></view>
        </view>
      </view>

      <button v-if="answered" class="btn-primary" @tap="nextQuiz">下一题</button>
    </view>

    <!-- 完成 -->
    <view v-else-if="phase === 'done'" class="card done">
      <view class="done-emoji" style="display:flex;justify-content:center"><view class="ic ic-check-circle" style="width:80rpx;height:80rpx" /></view>
      <view class="done-title">今日完成！</view>
      <view class="done-stat">新学 {{ newCards.length }} 词 · 复习 {{ reviewCards.length }} 词</view>
      <view class="done-stat">答对率 {{ quizQueue.length ? Math.round((correctCount / quizQueue.length) * 100) : 0 }}%</view>
      <view v-if="checkinDone" class="done-streak">今日已记录学习 · 连续 {{ streakDays }} 天 🔥</view>

      <!-- 跟读发音报告（本次有跟读评测才显示）-->
      <view v-if="shadowReport" class="vrep">
        <view class="vrep-hd">
          <view class="vrep-t" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-mic" style="width:32rpx;height:32rpx" /><text>发音报告</text></view>
          <text class="vrep-trend" :class="shadowReport.trend">{{ trendText(shadowReport.trend) }}</text>
        </view>
        <view class="vrep-top">
          <view class="vrep-avg">
            <text class="vrep-avg-n">{{ shadowReport.avg ?? '-' }}</text>
            <text class="vrep-avg-u">平均分</text>
          </view>
          <view class="vrep-dims">
            <text class="vrep-dim">跟读 {{ shadowReport.count }} 句</text>
            <text v-if="shadowReport.accuracy != null" class="vrep-dim">准确 {{ shadowReport.accuracy }} · 流利 {{ shadowReport.fluency }} · 完整 {{ shadowReport.completion }}</text>
            <text class="vrep-dim">最佳：{{ shadowReport.best.word }} {{ shadowReport.best.score }}分</text>
          </view>
        </view>
        <view v-if="shadowReport.bars.length" class="vrep-bars">
          <view v-for="(b, i) in shadowReport.bars" :key="i" class="vrep-bar"
            :class="barLevel(b)" :style="{ height: Math.max(8, b * 0.6) + 'rpx' }" />
        </view>
        <view v-if="shadowReport.weakWords.length" class="vrep-weak">
          <text class="vrep-weak-t">需加强：</text>
          <text v-for="(w, i) in shadowReport.weakWords" :key="i" class="vrep-weak-w">{{ w }}</text>
        </view>
      </view>
      <view v-if="cal" class="checkin-panel">
        <view class="cp-badges">
          <text v-for="b in cal.badges" :key="b.level" class="cp-badge" :class="{ on: b.unlocked }">
            {{ b.level === 'bronze' ? '🥉' : b.level === 'silver' ? '🥈' : '🥇' }}{{ b.name }}
          </text>
        </view>
        <view class="cp-grid">
          <view v-for="(c, i) in calCells" :key="i" class="cp-cell"
                :class="{ checked: c.checked, missable: c.missable, blank: !c.day }"
                @tap="c.missable ? onMakeUp(c.date) : null">
            <text v-if="c.day">{{ c.checked ? '🔥' : c.day }}</text>
            <text v-if="c.wrong > 0" class="cell-wrong">{{ c.wrong }}</text>
          </view>
        </view>
        <view class="cp-hint">点亮灰色日期可补签</view>
      </view>
      <view v-if="carryWords.length" class="carry-tip" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-refresh" style="width:28rpx;height:28rpx" /><text>本组错的 {{ carryWords.length }} 个词将带入下一组继续考察</text></view>
      <view class="done-set">每组 {{ wordsPerGroup }} 词 · 每组 {{ repsPerGroup }} 遍 <view class="gear-inline" @tap="openSettings" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-settings" style="width:26rpx;height:26rpx" /><text>设置</text></view><view class="gear-inline" @tap="openAddWord" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-plus" style="width:26rpx;height:26rpx" /><text>添加生词</text></view></view>
      <button class="btn-primary" @tap="reload">再来一组</button>
      <view class="done-links">
        <view class="done-link" @tap="() => uni.navigateTo({ url: '/pages/vocabulary/report' })" style="display:flex;align-items:center;gap:6rpx"><view class="ic ic-chart" style="width:30rpx;height:30rpx" /><text>学情报表</text></view>
        <view class="done-link" @tap="() => uni.navigateTo({ url: '/pages/vocabulary/wrong-book' })" style="display:flex;align-items:center;gap:6rpx"><view class="ic ic-book" style="width:30rpx;height:30rpx" /><text>错词本</text></view>
      </view>
    </view>

    <!-- 跟读评分弹窗 -->
    <view v-if="shadow.open" class="shadow-modal" @tap.self="closeShadow">
      <view class="shadow-card">
        <view class="shadow-title" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-mic" style="width:32rpx;height:32rpx" /><text>跟读练习</text></view>
        <text class="shadow-sentence">{{ shadow.text }}</text>

        <view class="shadow-tools">
          <view class="shadow-demo" @tap="playShadowDemo" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-volume" style="width:28rpx;height:28rpx" /><text>示范</text></view>
        </view>

        <!-- 录音 / 评分态 -->
        <view v-if="!shadow.result" class="shadow-rec-area">
          <button
            class="shadow-rec-btn"
            :class="{ recording: shadow.recording }"
            :disabled="shadow.scoring"
            @tap="shadow.recording ? stopAndScore() : startShadowRecord()"
          >
            {{ shadow.scoring ? '评分中…' : (shadow.recording ? '● 录音中，点击结束' : '开始跟读') }}
          </button>
          <text class="shadow-hint">点击开始，朗读上面的句子</text>
        </view>

        <!-- 评分结果 -->
        <view v-else class="shadow-result">
          <view class="shadow-score" :class="`lv-${shadow.result.level}`">
            <text class="ss-num">{{ shadow.result.overall }}</text>
            <text class="ss-unit">分 · {{ levelLabel(shadow.result.level) }}</text>
          </view>
          <view v-if="shadow.result.accuracy != null" class="shadow-dims">
            <text class="sd">准确度 {{ shadow.result.accuracy }}</text>
            <text class="sd">流利度 {{ shadow.result.fluency }}</text>
            <text class="sd">完整度 {{ shadow.result.completion }}</text>
          </view>
          <view class="shadow-words">
            <text
              v-for="(w, i) in shadow.result.words" :key="i"
              class="sw-chip" :class="{ weak: w.score < 80 }"
            >{{ w.word }} <text class="sw-score">{{ w.score }}</text></text>
          </view>
          <view class="shadow-tip" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-idea" style="width:30rpx;height:30rpx;flex-shrink:0" /><text>{{ shadow.result.tip }}</text></view>
          <view class="shadow-actions">
            <button v-if="shadow.recordPath" class="btn-ghost half" @tap="playMyRecord">▶ 我的录音</button>
            <button class="btn-primary half" @tap="retryShadow" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-refresh" style="width:30rpx;height:30rpx;filter:brightness(0) invert(1)" /><text>重跟</text></button>
          </view>
        </view>

        <text class="shadow-close" @tap="closeShadow">关闭</text>
      </view>
    </view>

    <!-- 学习设置弹窗 -->
    <view v-if="showSettings" class="shadow-modal" @tap.self="showSettings = false">
      <view class="set-card">
        <view class="set-title" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-settings" style="width:32rpx;height:32rpx" /><text>学习设置</text></view>
        <view class="set-row">
          <text class="set-label">每组词数</text>
          <view class="stepper">
            <text class="step-btn" @tap="adjustWPG(-1)">−</text>
            <text class="step-val">{{ settingDraft.words_per_group }}</text>
            <text class="step-btn" @tap="adjustWPG(1)">＋</text>
          </view>
        </view>
        <view class="set-row">
          <text class="set-label">每组遍数</text>
          <view class="stepper">
            <text class="step-btn" @tap="adjustRep(-1)">−</text>
            <text class="step-val">{{ settingDraft.reps_per_group }}</text>
            <text class="step-btn" @tap="adjustRep(1)">＋</text>
          </view>
        </view>
        <view class="set-row">
          <text class="set-label">错几次带入下组</text>
          <view class="stepper">
            <text class="step-btn" @tap="adjustThr(-1)">−</text>
            <text class="step-val">{{ settingDraft.wrong_carry_threshold }}</text>
            <text class="step-btn" @tap="adjustThr(1)">＋</text>
          </view>
        </view>
        <text class="set-hint">每组学几个词、重复学几遍由你定；学完可一直「再来一组」。一个词在本组错够「带入下组」的次数，就会自动滚入下一组继续考察（不超过遍数）。</text>
        <button class="btn-primary" @tap="saveSettings">保存</button>
        <text class="paywall-close" @tap="showSettings = false">取消</text>
      </view>
    </view>

    <!-- 添加生词弹窗 -->
    <view v-if="showAddWord" class="shadow-modal" @tap.self="showAddWord = false">
      <view class="set-card">
        <view class="set-title" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-plus" style="width:30rpx;height:30rpx" /><text>添加生词</text></view>
        <input class="addword-input" v-model="addWordInput" type="text" placeholder="输入英文单词"
          confirm-type="done" @confirm="submitAddWord" />
        <text class="set-hint">仅支持词典已收录的词；加入后会进入你的词单，之后学习会学到。</text>
        <button class="btn-primary" :disabled="!addWordInput.trim() || addingWord" @tap="submitAddWord">加入词单</button>
        <text class="paywall-close" @tap="showAddWord = false">完成</text>
      </view>
    </view>

    <!-- 跟读会员引导（统一会员墙）-->
    <Paywall :open="showPaywall" :feature="ent.feature('vocab.shadow')" emoji="🎤"
      title="跟读评测是会员专享" @close="showPaywall = false" />
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { getDailyTask, submitVocabAnswer, checkin, getCheckinCalendar, makeUpCheckin, shadowScore, getVocabSettings, setVocabSettings, addVocabWord, getWordProbes, submitWordProbe, submitWordProduce } from '@/api/vocabulary'
import type { ShadowScoreResult, WordProbe, WordProbeResult, WordProduceTask, WordProduceResult } from '@/api/vocabulary'
import type { VocabStudentCalendar } from '@/types/api'
import { resolveSpeakUrl } from '@/utils/tts'
import { useAuthStore } from '@/stores/auth'
import { useEntitlementsStore } from '@/stores/entitlements'
import Paywall from '@/components/Paywall.vue'
import type { VocabWordCard } from '@/types/api'

interface Quiz {
  word_id: string
  mode: 'w2m' | 'm2w' | 'pic'   // 看词选义 / 看义选词 / 看图选词
  prompt: string
  options: string[]   // 文本选项；mode==='pic' 时为图片 URL
  answerIndex: number
}

const auth = useAuthStore()
const loading = ref(true)
const phase = ref<'empty' | 'study' | 'review' | 'quiz' | 'done'>('study')
const readSeq = ref(true)   // 词卡出现时连读 单词+例句+短语
const ent = useEntitlementsStore()
const showPaywall = ref(false)    // 跟读会员引导弹窗
// 学习设置（用户自定，不绑会员档位）
const wordsPerGroup = ref(5)
const repsPerGroup = ref(1)
const wrongCarryThreshold = ref(2)
const showSettings = ref(false)
const settingDraft = reactive({ words_per_group: 5, reps_per_group: 1, wrong_carry_threshold: 2 })
const showAddWord = ref(false)
const addWordInput = ref('')
const addingWord = ref(false)
// 每组遍数循环 + 错词滚入
const currentRep = ref(1)                                  // 当前组的第几遍
const carryWords = ref<VocabWordCard[]>([])                // 上一组错得多、滚入本组的词
const groupWrong = reactive(new Map<string, number>())     // 本组各词错次数

const newCards = ref<VocabWordCard[]>([])
const reviewCards = ref<VocabWordCard[]>([])
const pool = ref<VocabWordCard[]>([])   // 全部词，用于生成干扰项

const studyIndex = ref(0)
const reviewIndex = ref(0)
const quizIndex = ref(0)
type ShadowLogItem = { word: string; overall: number; accuracy: number | null; fluency: number | null; completion: number | null; weak: string[] }
const shadowLog = ref<ShadowLogItem[]>([])   // 本次跟读发音评测（完成页发音报告）
const correctCount = ref(0)
const answered = ref(false)
const chosenIndex = ref(-1)
const quizQueue = ref<Quiz[]>([])
const streakDays = ref(0)
const checkinDone = ref(false)
const gapHint = ref('')
const cal = ref<VocabStudentCalendar | null>(null)
type CalCell = { day: number; date: string; checked: boolean; missable: boolean; wrong: number }
const calCells = computed(() => {
  if (!cal.value) return [] as CalCell[]
  const { year, month } = cal.value
  const wrongMap = new Map(cal.value.days.map(d => [d.date, (d as { wrong_count?: number }).wrong_count || 0]))
  const checkedSet = new Set(cal.value.days.map(d => d.date))
  const first = new Date(year, month - 1, 1).getDay()
  const daysIn = new Date(year, month, 0).getDate()
  const todayStr = new Date().toISOString().slice(0, 10)
  const arr: CalCell[] = []
  for (let i = 0; i < first; i++) arr.push({ day: 0, date: '', checked: false, missable: false, wrong: 0 })
  for (let d = 1; d <= daysIn; d++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const checked = checkedSet.has(date)
    arr.push({ day: d, date, checked, missable: !checked && date < todayStr, wrong: wrongMap.get(date) || 0 })
  }
  return arr
})
async function loadCalendar() {
  try { cal.value = await getCheckinCalendar() } catch { /* 不阻塞 */ }
}
async function onMakeUp(date: string) {
  try {
    await makeUpCheckin(date)
    await loadCalendar()
    uni.showToast({ title: '补签成功', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}

const isReview = computed(() => phase.value === 'review')
const cardList = computed(() => (isReview.value ? reviewCards.value : newCards.value))
const cardIdx = computed(() => (isReview.value ? reviewIndex.value : studyIndex.value))
const curStudy = computed(() => cardList.value[cardIdx.value] || ({} as VocabWordCard))

// R9.1 理解检测·语境填空(接收探针)
const probeOpen = ref(false)
const probeLoading = ref(false)
const probeCtx = ref<{ text: string; source: string } | null>(null)
const probes = ref<WordProbe[]>([])
const probePick = ref<Record<string, string>>({})
const probeResults = ref<Record<string, WordProbeResult>>({})
const recep = ref(0)
const prod = ref(0)
const mastered = ref(false)
// 产出·造句
const produceTask = ref<WordProduceTask | null>(null)
const produceInput = ref('')
const produceResult = ref<WordProduceResult | null>(null)
const produceSubmitting = ref(false)
function resetProbe() {
  probeOpen.value = false; probeLoading.value = false; probeCtx.value = null
  probes.value = []; probePick.value = {}; probeResults.value = {}; recep.value = 0; prod.value = 0; mastered.value = false
  produceTask.value = null; produceInput.value = ''; produceResult.value = null; produceSubmitting.value = false
}
watch(() => curStudy.value.word_id, resetProbe)   // 换词即重置检测
async function openProbe() {
  const id = curStudy.value.word_id
  if (!id) return
  probeOpen.value = true; probes.value = []; probePick.value = {}; probeResults.value = {}; probeLoading.value = true
  try {
    const r = await getWordProbes(id)
    probeCtx.value = r.context; probes.value = r.probes; recep.value = r.recep
    prod.value = r.prod; mastered.value = r.mastered; produceTask.value = r.produce
    if (!r.probes.length && !r.produce) uni.showToast({ title: '该词暂无语境检测', icon: 'none' })
  } catch { uni.showToast({ title: '加载检测失败', icon: 'none' }) }
  finally { probeLoading.value = false }
}
function pickProbe(key: string, opt: string) {
  if (probeResults.value[key]) return
  probePick.value = { ...probePick.value, [key]: opt }
}
async function submitProbe(key: string) {
  const id = curStudy.value.word_id
  const ans = probePick.value[key]
  if (!id || !ans) return
  try {
    const r = await submitWordProbe(id, key, ans)
    probeResults.value = { ...probeResults.value, [key]: r }
    recep.value = r.recep; prod.value = r.prod; mastered.value = r.mastered
    uni.showToast({ title: r.correct ? '答对了！' : '再看看语境', icon: 'none' })
  } catch { uni.showToast({ title: '提交失败', icon: 'none' }) }
}
async function submitProduce() {
  const id = curStudy.value.word_id
  const s = produceInput.value.trim()
  if (!id || !s || produceSubmitting.value) return
  produceSubmitting.value = true
  try {
    const r = await submitWordProduce(id, s)
    produceResult.value = r; prod.value = r.prod; mastered.value = r.mastered
    uni.showToast({ title: r.passed ? '输出达标 ✓' : '再打磨一下', icon: 'none' })
  } catch { uni.showToast({ title: '评分失败', icon: 'none' }) }
  finally { produceSubmitting.value = false }
}
function redoProduce() { produceResult.value = null }
const studyBtnLabel = computed(() => {
  if (isReview.value) {
    return reviewIndex.value >= reviewCards.value.length - 1 ? '开始测试 →' : '记住了，下一个'
  }
  if (studyIndex.value >= newCards.value.length - 1) {
    return reviewCards.value.length > 0 ? '开始复习 →' : '开始测试 →'
  }
  return '记住了，下一个'
})
const curQuiz = computed(() => quizQueue.value[quizIndex.value] || ({} as Quiz))
const quizCard = computed(() => pool.value.find((c) => c.word_id === curQuiz.value.word_id) || null)
const lastCorrect = ref(false)

// 完成页发音报告：聚合本次跟读评测（均分/三维/薄弱词/趋势/柱状）
const shadowReport = computed(() => {
  const items = shadowLog.value.filter((it) => it.overall != null)
  if (!items.length) return null
  const avg = (arr: (number | null)[]) => {
    const v = arr.filter((x): x is number => x != null)
    return v.length ? Math.round(v.reduce((a, b) => a + b, 0) / v.length) : null
  }
  const bars = items.map((i) => i.overall)
  const best = items.reduce((a, b) => (b.overall > a.overall ? b : a))
  const wc = new Map<string, number>()
  items.forEach((it) => it.weak.forEach((w) => wc.set(w, (wc.get(w) || 0) + 1)))
  const weakWords = [...wc.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map((e) => e[0])
  let trend: 'up' | 'flat' | 'down' = 'flat'
  if (bars.length >= 2) {
    const mid = Math.floor(bars.length / 2)
    const f = avg(bars.slice(0, mid)) || 0
    const s = avg(bars.slice(mid)) || 0
    trend = s - f >= 5 ? 'up' : f - s >= 5 ? 'down' : 'flat'
  }
  return {
    count: items.length,
    avg: avg(bars),
    accuracy: avg(items.map((i) => i.accuracy)),
    fluency: avg(items.map((i) => i.fluency)),
    completion: avg(items.map((i) => i.completion)),
    best: { word: best.word, score: best.overall },
    weakWords, trend, bars: bars.slice(-12),
  }
})
function trendText(t: string) {
  return t === 'up' ? '📈 越练越好' : t === 'down' ? '📉 略有起伏' : '➡️ 稳定发挥'
}
function barLevel(b: number) {
  return b >= 90 ? 'excellent' : b >= 80 ? 'good' : b >= 60 ? 'fair' : 'poor'
}
const quizTypeLabel = computed(() => {
  const m = curQuiz.value.mode
  return m === 'w2m' ? '看词选义' : m === 'm2w' ? '看义选词' : '看图选词'
})

function defList(card: VocabWordCard): string[] {
  const d = card.definitions
  if (Array.isArray(d)) return d.map((x: any) => `${x.pos ? x.pos + ' ' : ''}${x.meaning}`)
  return []
}
function primaryMeaning(card: VocabWordCard): string {
  const d = card.definitions
  if (Array.isArray(d) && d.length) return (d[0] as any).meaning
  return ''
}
type EnZh = { en: string; zh?: string; audio?: string }
function _firstEnZh(list: unknown): EnZh | null {
  if (Array.isArray(list) && list.length && list[0] && typeof list[0] === 'object') {
    const o = list[0] as Record<string, unknown>
    const en = String(o.en ?? '').trim()
    if (en) return { en, zh: String(o.zh ?? '').trim(), audio: String(o.audio ?? '').trim() }
  }
  return null
}
function firstExample(card: VocabWordCard): EnZh | null { return _firstEnZh(card.examples) }
function firstPhrase(card: VocabWordCard): EnZh | null { return _firstEnZh(card.phrases) }
function cleanPhon(p?: string | null): string {
  return (p || '').trim().replace(/^\/+|\/+$/g, '')   // 去掉首尾斜杠，避免 //ˈæpl//
}

function shuffle<T>(arr: T[]): T[] {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function firstImage(w: VocabWordCard): string | null {
  return w.image_urls && w.image_urls.length ? w.image_urls[0] : null
}

function buildQuiz(card: VocabWordCard, mode: 'w2m' | 'm2w' | 'pic'): Quiz {
  const others = pool.value.filter((w) => w.word_id !== card.word_id)
  if (mode === 'pic') {
    // 看图选词：本词图 + 3 干扰词图，4 选 1（需本词有图 + ≥3 个有图干扰词，否则回退看词选义）
    const correctImg = firstImage(card)
    const imgOthers = shuffle(others.filter((w) => firstImage(w)))
    if (correctImg && imgOthers.length >= 3) {
      const opts = shuffle([correctImg, ...imgOthers.slice(0, 3).map((w) => firstImage(w) as string)])
      return { word_id: card.word_id, mode: 'pic', prompt: card.word, options: opts, answerIndex: opts.indexOf(correctImg) }
    }
    mode = 'w2m'
  }
  const distractors = shuffle(others).slice(0, 3)
  if (mode === 'w2m') {
    const correct = primaryMeaning(card)
    const opts = shuffle([correct, ...distractors.map((w) => primaryMeaning(w))])
    return { word_id: card.word_id, mode: 'w2m', prompt: card.word, options: opts, answerIndex: opts.indexOf(correct) }
  }
  const correct = card.word
  const opts = shuffle([correct, ...distractors.map((w) => w.word)])
  return { word_id: card.word_id, mode: 'm2w', prompt: primaryMeaning(card), options: opts, answerIndex: opts.indexOf(correct) }
}

function startQuiz() {
  const all = [...newCards.value, ...reviewCards.value]
  const modes: Array<'w2m' | 'm2w' | 'pic'> = ['w2m', 'm2w', 'pic']
  quizQueue.value = all.map((card, i) => buildQuiz(card, modes[i % 3]))
  quizIndex.value = 0
  correctCount.value = 0
  answered.value = false
  chosenIndex.value = -1
  if (quizQueue.value.length) {
    phase.value = 'quiz'
    nextTick(announceQuiz)
  } else {
    finishSession()
  }
}

async function finishSession() {
  phase.value = 'done'
  try {
    // 日历=学习日志：完成一组即记入当日 + 累加本组错题数（多错统计）
    const groupWrongTotal = [...groupWrong.values()].reduce((a, b) => a + b, 0)
    const r = await checkin(groupWrongTotal)
    checkinDone.value = true
    streakDays.value = r.streak_days ?? streakDays.value
    requestCheckinSubscribe()
  } catch {
    // 记录失败不阻塞完成页展示
  }
  await loadCalendar()
}

/**
 * 请求微信订阅消息授权（打卡提醒）。
 * template_id 通过环境变量 VITE_WX_SUBSCRIBE_TEMPLATE_CHECKIN 注入；
 * dev 模式（空字符串）时静默跳过，不弹授权框。
 */
function requestCheckinSubscribe() {
  const tmplId = import.meta.env.VITE_WX_SUBSCRIBE_TEMPLATE_CHECKIN as string | undefined
  if (!tmplId) return  // dev 模式或未配置，跳过

  uni.requestSubscribeMessage({
    tmplIds: [tmplId],
    success() {
      // 用户选择（accept/reject/ban），结果记录在微信侧
      // 后端 cron 下次发送时微信会自动过滤未授权用户
    },
    fail() {
      // 用户拒绝或环境不支持（如开发工具），静默忽略
    },
  })
}

function nextStudy() {
  if (phase.value === 'review') {
    if (reviewIndex.value < reviewCards.value.length - 1) {
      reviewIndex.value++
      nextTick(() => playCard(curStudy.value))
    } else {
      startQuiz()
    }
    return
  }
  // 学新词阶段
  if (studyIndex.value < newCards.value.length - 1) {
    studyIndex.value++
    nextTick(() => playCard(curStudy.value))   // 新词卡出现自动发声
  } else if (reviewCards.value.length > 0) {
    enterReview()                              // 新词学完 → 复习词词卡
  } else {
    startQuiz()
  }
}

function enterReview() {
  phase.value = 'review'
  reviewIndex.value = 0
  nextTick(() => playCard(curStudy.value))
}

async function choose(i: number) {
  if (answered.value) return
  answered.value = true
  chosenIndex.value = i
  const correct = i === curQuiz.value.answerIndex
  lastCorrect.value = correct
  if (correct) correctCount.value++
  else {
    const wid = curQuiz.value.word_id
    groupWrong.set(wid, (groupWrong.get(wid) || 0) + 1)   // 本组错词计数 → 滚入下一组
  }
  // 答题反馈：读出正确单词发音（答错时尤其重要，立即订正）
  playWordAudio(quizCard.value?.word)
  try {
    await submitVocabAnswer(curQuiz.value.word_id, correct, false)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}

function nextQuiz() {
  if (quizIndex.value < quizQueue.value.length - 1) {
    quizIndex.value++
    answered.value = false
    chosenIndex.value = -1
    nextTick(announceQuiz)
  } else if (currentRep.value < repsPerGroup.value) {
    // 本组还没学够遍数 → 同一组再来一遍（重新过词卡 + 测试）
    currentRep.value++
    uni.showToast({ title: `第 ${currentRep.value}/${repsPerGroup.value} 遍`, icon: 'none' })
    restartGroupPass()
  } else {
    finalizeGroup()
  }
}

// 同一组再过一遍：回到词卡（有新词从新词，否则复习），过完再测
function restartGroupPass() {
  studyIndex.value = 0
  reviewIndex.value = 0
  if (newCards.value.length > 0) {
    phase.value = 'study'
    nextTick(() => playCard(curStudy.value))
  } else if (reviewCards.value.length > 0) {
    enterReview()
  } else {
    startQuiz()
  }
}

// 本组学完所有遍数：把错得「比较多」的词存为「滚入下一组」，进完成页
function finalizeGroup() {
  // 阈值：错≥设定次数才滚入；但不超过本组遍数（遍数=1 时退化为错1次即滚入）
  const thr = Math.max(1, Math.min(wrongCarryThreshold.value, repsPerGroup.value))
  const carried: VocabWordCard[] = []
  pool.value.forEach((c) => {
    if ((groupWrong.get(c.word_id) || 0) >= thr) carried.push(c)
  })
  carryWords.value = carried
  finishSession()
}

function optionClass(i: number): string {
  if (!answered.value) return ''
  if (i === curQuiz.value.answerIndex) return 'opt-correct'
  if (i === chosenIndex.value) return 'opt-wrong'
  return ''
}

async function load(fromReload = false) {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  ent.ensure()
  getVocabSettings().then((s) => {
    wordsPerGroup.value = s.words_per_group; repsPerGroup.value = s.reps_per_group
    wrongCarryThreshold.value = s.wrong_carry_threshold ?? 2
    settingDraft.words_per_group = s.words_per_group; settingDraft.reps_per_group = s.reps_per_group
    settingDraft.wrong_carry_threshold = s.wrong_carry_threshold ?? 2
  }).catch(() => { /* 用默认 */ })
  try {
    const task = await getDailyTask()
    // 错词滚入：把上一组错得多的词并入本组复习（去重，且不与本组新词重复）
    const carried = carryWords.value; carryWords.value = []
    const newIds = new Set(task.new_words.map((w) => w.word_id))
    const reviewIds = new Set(task.review_words.map((w) => w.word_id))
    const extra = carried.filter((w) => !newIds.has(w.word_id) && !reviewIds.has(w.word_id))
    newCards.value = task.new_words
    reviewCards.value = [...task.review_words, ...extra]
    pool.value = [...newCards.value, ...reviewCards.value]
    studyIndex.value = 0
    reviewIndex.value = 0
    shadowLog.value = []
    currentRep.value = 1
    groupWrong.clear()
    if (newCards.value.length === 0 && reviewCards.value.length === 0) {
      // 「再来一组」时已无可练的词：友好提示并停留在完成页，不跳日历
      if (fromReload) {
        uni.showToast({ title: '今天的词都练完啦 🎉', icon: 'none' })
        return
      }
      phase.value = 'empty'
      loadCalendar()
    } else if (newCards.value.length > 0) {
      phase.value = 'study'
      nextTick(() => playCard(curStudy.value))   // 首张词卡自动发声
    } else {
      enterReview()                              // 只有复习词：先过带图词卡再测
    }
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

let _audioCtx: UniApp.InnerAudioContext | null = null
let _queue: string[] = []
function _ensureCtx() {
  if (!_audioCtx) {
    _audioCtx = uni.createInnerAudioContext()
    _audioCtx.onEnded(() => {
      _queue.shift()
      if (_queue.length && _audioCtx) { _audioCtx.src = _queue[0]; _audioCtx.play() }
    })
    _audioCtx.onError(() => { _queue = [] })
  }
  return _audioCtx
}
function playAudio(src?: string | null) {
  if (!src) return
  _queue = [src]
  _ensureCtx()
  _audioCtx!.src = src
  _audioCtx!.play()
}
function _playUrls(urls: string[]) {
  _queue = urls.filter(Boolean)
  if (!_queue.length) return
  _ensureCtx()
  _audioCtx!.src = _queue[0]
  _audioCtx!.play()
}

/** 播放一段文本的火山 TTS 音频（优先 COS 持久化直链，否则流式）。 */
async function playTTS(text?: string | null) {
  if (!text) return
  const url = await resolveSpeakUrl(text)
  playAudio(url)
}

/** 词卡发声：单词（开关开时连读例句/短语），优先预生成音频，缺失再 TTS。 */
async function playCard(card?: VocabWordCard | null) {
  if (!card || !card.word) return
  const urls: string[] = [card.word_audio_url || await resolveSpeakUrl(card.word)]
  if (readSeq.value) {
    const ex = firstExample(card)
    const ph = firstPhrase(card)
    if (ex?.en) urls.push(ex.audio || await resolveSpeakUrl(ex.en))
    if (ph?.en) urls.push(ph.audio || await resolveSpeakUrl(ph.en))
  }
  _playUrls(urls)
}

/** 播放某个单词的发音（优先该词预生成音频，缺失再 TTS）。 */
function cardByWord(w: string): VocabWordCard | null {
  return pool.value.find((c) => c.word === w) || null
}
async function playWordAudio(word?: string | null) {
  if (!word) return
  const c = cardByWord(word)
  const url = (c && c.word_audio_url) || await resolveSpeakUrl(word)
  playAudio(url)
}
/** 看词选义 / 看图选词：题干是单词 → 出题即自动发音。 */
function announceQuiz() {
  const q = curQuiz.value
  if (q && (q.mode === 'w2m' || q.mode === 'pic') && q.prompt) playWordAudio(q.prompt)
}

function reload() {
  load(true)   // 「再来一组」：没词时不跳日历
}

// ── 学习设置 ──
function openSettings() {
  settingDraft.words_per_group = wordsPerGroup.value
  settingDraft.reps_per_group = repsPerGroup.value
  settingDraft.wrong_carry_threshold = wrongCarryThreshold.value
  showSettings.value = true
}
function adjustWPG(d: number) {
  settingDraft.words_per_group = Math.max(1, Math.min(50, settingDraft.words_per_group + d))
}
function adjustRep(d: number) {
  settingDraft.reps_per_group = Math.max(1, Math.min(5, settingDraft.reps_per_group + d))
}
function adjustThr(d: number) {
  settingDraft.wrong_carry_threshold = Math.max(1, Math.min(5, settingDraft.wrong_carry_threshold + d))
}
async function saveSettings() {
  try {
    const s = await setVocabSettings({
      words_per_group: settingDraft.words_per_group, reps_per_group: settingDraft.reps_per_group,
      wrong_carry_threshold: settingDraft.wrong_carry_threshold })
    wordsPerGroup.value = s.words_per_group
    repsPerGroup.value = s.reps_per_group
    wrongCarryThreshold.value = s.wrong_carry_threshold ?? 2
    showSettings.value = false
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '保存失败', icon: 'none' })
  }
}

// ── 添加生词（仅词典已有）──
function openAddWord() { addWordInput.value = ''; showAddWord.value = true }
async function submitAddWord() {
  const w = addWordInput.value.trim()
  if (!w || addingWord.value) return
  addingWord.value = true
  try {
    const r = await addVocabWord(w)
    if (!r.found) {
      uni.showToast({ title: r.message || '词典暂未收录', icon: 'none' })
    } else if (r.already) {
      uni.showToast({ title: `「${r.word}」已在词单中`, icon: 'none' })
      addWordInput.value = ''
    } else {
      uni.showToast({ title: `已加入「${r.word}」`, icon: 'success' })
      addWordInput.value = ''
    }
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '添加失败', icon: 'none' })
  } finally {
    addingWord.value = false
  }
}

// ── 跟读评分（听力跟读·嵌入例句）──────────────────────────────────────────
const shadow = reactive({
  open: false,
  text: '',
  recording: false,
  scoring: false,
  result: null as ShadowScoreResult | null,
  recordPath: '',
})

function levelLabel(lv: string) {
  return ({ excellent: '优秀', good: '良好', fair: '及格', poor: '待加强' } as Record<string, string>)[lv] || lv
}

function openShadow(text: string) {
  if (!ent.can('vocab.shadow')) { showPaywall.value = true; return }   // 跟读为会员专享
  Object.assign(shadow, { open: true, text, recording: false, scoring: false, result: null, recordPath: '' })
}

function closeShadow() {
  // #ifdef MP-WEIXIN
  if (shadow.recording) { try { _recorder?.stop() } catch { /* ignore */ } }
  // #endif
  shadow.open = false
  shadow.recording = false
}

function playShadowDemo() {
  // 火山 TTS 实时合成整句示范音频
  playTTS(shadow.text)
}

let _recorder: UniApp.RecorderManager | null = null
let _recorderBound = false
function ensureRecorder(): UniApp.RecorderManager {
  if (!_recorder) _recorder = uni.getRecorderManager()
  if (!_recorderBound) {
    // 录音结束 → 读文件为 base64 → 送评测（onStop 异步，必须在这里取路径）
    _recorder.onStop((res) => { readAndScore((res as { tempFilePath?: string }).tempFilePath || '') })
    _recorderBound = true
  }
  return _recorder
}

function startShadowRecord() {
  shadow.result = null
  shadow.recordPath = ''
  // #ifdef MP-WEIXIN
  try {
    ensureRecorder().start({ format: 'mp3', sampleRate: 16000, numberOfChannels: 1, encodeBitRate: 48000, duration: 60000 })
    shadow.recording = true
    return
  } catch { /* 不支持则退回直接评分 */ }
  // #endif
  shadow.recording = true
}

function stopAndScore() {
  shadow.recording = false
  shadow.scoring = true
  // #ifdef MP-WEIXIN
  try { _recorder?.stop(); return } catch { /* ignore */ }
  // #endif
  // H5 / 不支持录音：直接走 dev-mock（无音频）
  readAndScore('')
}

async function readAndScore(path: string) {
  let audio = ''
  if (path) {
    audio = await new Promise<string>((resolve) => {
      try {
        uni.getFileSystemManager().readFile({
          filePath: path, encoding: 'base64',
          success: (r) => resolve((r.data as string) || ''),
          fail: () => resolve(''),
        })
      } catch { resolve('') }
    })
  }
  try {
    shadow.result = await shadowScore(shadow.text, audio, 'mp3')
    if (shadow.result) {
      const r = shadow.result as unknown as { overall: number; accuracy?: number; fluency?: number; completion?: number; words?: { word: string; score: number }[] }
      shadowLog.value.push({
        word: curStudy.value.word || '',
        overall: r.overall,
        accuracy: r.accuracy ?? null,
        fluency: r.fluency ?? null,
        completion: r.completion ?? null,
        weak: (r.words || []).filter((w) => w.score < 80).map((w) => w.word),
      })
    }
  } catch (e) {
    if ((e as { code?: number }).code === 402) {   // 会员专享：引导开通
      closeShadow()
      showPaywall.value = true
    } else {
      uni.showToast({ title: (e as Error).message || '评分失败', icon: 'none' })
    }
  } finally {
    shadow.scoring = false
  }
}

function retryShadow() {
  shadow.result = null
  shadow.recordPath = ''
}

function playMyRecord() {
  if (shadow.recordPath) playAudio(shadow.recordPath)
}

onMounted(load)
</script>

<style scoped>
.vocab-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 40rpx; color: var(--c-text-hint); line-height: 1.8; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 40rpx 32rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,0.04); }
.progress-hint { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 24rpx; }
/* 学新词词卡（图左+词右）*/
.study-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.study-hd .progress-hint { margin-bottom: 0; }
.seq-toggle { font-size: 24rpx; color: var(--c-text-hint); }
.seq-toggle.on { color: var(--c-primary-deep); font-weight: 600; }
.wc-top { display: flex; gap: 20rpx; padding-bottom: 20rpx; border-bottom: 1rpx solid var(--c-bg-soft); }
.wc-img { width: 300rpx; height: 280rpx; border-radius: 16rpx; flex-shrink: 0; background: var(--c-bg-soft); }
.wc-img-empty { display: flex; align-items: center; justify-content: center; font-size: 80rpx; opacity: .5; }
.wc-info { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 10rpx; min-width: 0; }
.wc-word { font-size: 52rpx; font-weight: 900; color: var(--c-ink); }
.wc-phon { font-size: 28rpx; color: var(--c-text-second); }
.wc-mean { font-size: 32rpx; color: var(--c-text-body); font-weight: 600; }
.wc-row { display: flex; gap: 16rpx; padding: 18rpx 0; border-bottom: 1rpx solid var(--c-bg-soft); }
.wc-tag { flex-shrink: 0; font-size: 22rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 5rpx 16rpx; border-radius: var(--r-pill); height: 34rpx; line-height: 34rpx; }
.wc-rowtext { flex: 1; display: flex; flex-direction: column; gap: 4rpx; min-width: 0; }
.wc-en { font-size: 30rpx; color: var(--c-text-body); line-height: 1.5; }
.wc-zh { font-size: 24rpx; color: var(--c-text-hint); }
.wc-btns { display: flex; gap: 18rpx; margin: 24rpx 0; }
.wc-btn { flex: 1; text-align: center; font-size: 28rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 16rpx 0; border-radius: var(--r-pill); }
.wc-btn.primary { background: var(--c-primary); color: var(--c-on-primary); }
.word { font-size: 60rpx; font-weight: 800; color: var(--c-ink); text-align: center; }
.phonetic { font-size: 30rpx; color: var(--c-text-second); text-align: center; margin-top: 8rpx; }
.defs { margin-top: 32rpx; }
.def-line { display: block; font-size: 32rpx; color: var(--c-text-body); line-height: 1.8; }
.img-row { white-space: nowrap; margin: 20rpx 0; }
.word-img { width: 220rpx; height: 160rpx; border-radius: var(--r-md); margin-right: 16rpx; display: inline-block; background: var(--c-bg-soft); }
.en-desc { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; margin: 16rpx 0; }
.en-desc-text { font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }
.audio-row { display: flex; gap: 24rpx; margin-bottom: 8rpx; }
.audio-btn { font-size: 28rpx; color: var(--c-gold); font-weight: 600; }
.examples { margin-top: 24rpx; padding-top: 20rpx; border-top: 1rpx solid var(--c-bg-soft); }
.ex-title { font-size: 24rpx; color: var(--c-text-hint); display: block; margin-bottom: 8rpx; }
.ex-row { display: flex; align-items: center; gap: 12rpx; margin-bottom: 6rpx; }
.ex-line { flex: 1; font-size: 28rpx; color: var(--c-text-second); line-height: 1.7; }
.ex-shadow-btn { flex-shrink: 0; font-size: 22rpx; font-weight: 600; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 6rpx 16rpx; border-radius: var(--r-pill); }
.quiz-type { font-size: 24rpx; color: var(--c-gold); font-weight: 600; }
.quiz-prompt { font-size: 44rpx; font-weight: 700; color: var(--c-ink); text-align: center; margin: 32rpx 0 40rpx; }
.option { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 28rpx 24rpx; font-size: 30rpx; color: var(--c-text-body); margin-bottom: 20rpx; }
.opt-text { flex: 1; }
.opt-play { flex-shrink: 0; font-size: 32rpx; color: var(--c-gold); padding: 0 8rpx; }
.qp-play { margin-left: 16rpx; font-size: 36rpx; color: var(--c-gold); vertical-align: middle; }
/* 答题反馈 */
.quiz-fb { margin: 8rpx 0 24rpx; padding: 20rpx 22rpx; border-radius: var(--r-md); }
.quiz-fb.ok { background: #d8f3dc; }
.quiz-fb.no { background: #fff3e0; }
.qfb-ok { font-size: 30rpx; font-weight: 800; color: #1b7a3d; }
.qfb-wrong { display: flex; align-items: center; flex-wrap: wrap; gap: 12rpx; }
.qfb-label { font-size: 24rpx; color: #b06a2a; }
.qfb-word { font-size: 34rpx; font-weight: 800; color: var(--c-ink); }
.qfb-phon { font-size: 26rpx; color: var(--c-text-second); }
.qfb-mean { font-size: 28rpx; color: var(--c-text-body); }
.qfb-play { font-size: 34rpx; color: var(--c-gold); margin-left: auto; }
/* 跟读发音报告 */
.vrep { width: 100%; box-sizing: border-box; background: linear-gradient(160deg, #eef6ff, #f7fbff); border: 2rpx solid #d6e6ff; border-radius: 16rpx; padding: 18rpx 20rpx; margin-top: 24rpx; display: flex; flex-direction: column; gap: 12rpx; text-align: left; }
.vrep-hd { display: flex; align-items: center; justify-content: space-between; }
.vrep-t { font-size: 28rpx; font-weight: 800; color: #2f6fd6; }
.vrep-trend { font-size: 22rpx; font-weight: 700; padding: 3rpx 14rpx; border-radius: var(--r-pill); background: #fff; }
.vrep-trend.up { color: #34c759; }
.vrep-trend.down { color: #ff9500; }
.vrep-trend.flat { color: #5aa9f8; }
.vrep-top { display: flex; align-items: center; gap: 18rpx; }
.vrep-avg { flex-shrink: 0; display: flex; flex-direction: column; align-items: center; background: #fff; border-radius: 14rpx; padding: 10rpx 22rpx; }
.vrep-avg-n { font-size: 48rpx; font-weight: 900; color: #2f6fd6; line-height: 1.1; }
.vrep-avg-u { font-size: 20rpx; color: var(--c-text-hint); }
.vrep-dims { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.vrep-dim { font-size: 23rpx; color: var(--c-text-body); }
.vrep-bars { display: flex; align-items: flex-end; gap: 6rpx; height: 64rpx; padding: 4rpx 0; }
.vrep-bar { flex: 1; min-width: 8rpx; border-radius: 4rpx; background: #5aa9f8; }
.vrep-bar.excellent { background: #34c759; }
.vrep-bar.good { background: #5aa9f8; }
.vrep-bar.fair { background: #ffab40; }
.vrep-bar.poor { background: #ff6b6b; }
.vrep-weak { display: flex; flex-wrap: wrap; align-items: center; gap: 8rpx; }
.vrep-weak-t { font-size: 23rpx; color: var(--c-text-hint); }
.vrep-weak-w { font-size: 22rpx; font-weight: 700; color: #d6457e; background: #fff0f5; border-radius: var(--r-pill); padding: 3rpx 14rpx; }
.opt-correct { background: #d8f3dc; color: #1b7a3d; }
.opt-wrong { background: #fdecea; color: var(--c-danger); }
/* 看图选词 2×2 */
.pic-grid { display: flex; flex-wrap: wrap; justify-content: space-between; }
.pic-option { width: 48%; height: 220rpx; border-radius: var(--r-md); overflow: hidden; margin-bottom: 16rpx; border: 4rpx solid transparent; background: var(--c-bg-soft); }
.pic-option.opt-correct { border-color: #1b7a3d; }
.pic-option.opt-wrong { border-color: var(--c-danger); }
.pic-option-img { width: 100%; height: 100%; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; margin-top: 24rpx; }
/* R9.1 理解检测·语境填空 */
.probe-box { margin-top: 22rpx; padding-top: 18rpx; border-top: 1rpx solid #f0f2f5; }
.probe-cta { display: flex; align-items: center; justify-content: center; gap: 10rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border-radius: var(--r-pill); padding: 16rpx 0; font-size: 26rpx; font-weight: 700; }
.probe-cta:active { opacity: .85; }
.probe-tip { text-align: center; color: #9aa3b0; font-size: 24rpx; padding: 14rpx 0; }
.probe-item { margin-bottom: 14rpx; }
.probe-q { display: block; font-size: 26rpx; color: #2a3138; font-weight: 600; line-height: 1.6; margin-bottom: 12rpx; }
.probe-opts { display: flex; flex-direction: column; gap: 10rpx; }
.probe-opt { font-size: 26rpx; color: #4a5057; background: #f5f7fa; border: 2rpx solid transparent; border-radius: 14rpx; padding: 14rpx 18rpx; font-family: Georgia, 'Times New Roman', serif; }
.probe-opt.on { background: var(--c-primary-faint); border-color: var(--c-primary); color: var(--c-primary-deep); }
.probe-opt.ok { background: #e9f7ef; border-color: #1f9d6b; color: #1f9d6b; }
.probe-opt.no { background: #fdecea; border-color: #e2504a; color: #e2504a; }
.probe-submit { margin-top: 12rpx; text-align: center; background: var(--c-primary); color: var(--c-on-primary); font-size: 26rpx; font-weight: 700; padding: 14rpx 0; border-radius: var(--r-pill); }
.probe-submit.dis { background: #d7dde6; }
.probe-fb { margin-top: 10rpx; font-size: 24rpx; display: flex; flex-direction: column; gap: 4rpx; }
.probe-fb.ok { color: #1f9d6b; }
.probe-fb.no { color: #e2504a; }
.probe-mis { color: #c0792a; font-size: 22rpx; line-height: 1.5; }
.probe-recep { display: flex; align-items: center; justify-content: flex-end; gap: 12rpx; font-size: 22rpx; color: #8a93a3; margin-top: 10rpx; }
.probe-mastered { color: #1f9d6b; font-weight: 700; }
/* 产出·造句 */
.produce-box { margin-top: 16rpx; padding-top: 14rpx; border-top: 1rpx dashed #e6e9ef; }
.produce-q { display: block; font-size: 25rpx; color: #2a3138; font-weight: 600; line-height: 1.6; margin-bottom: 10rpx; }
.produce-input { width: 100%; box-sizing: border-box; min-height: 96rpx; background: #f5f7fa; border-radius: 14rpx; padding: 14rpx 16rpx; font-size: 26rpx; line-height: 1.6; font-family: Georgia, 'Times New Roman', serif; }
.produce-result { background: #f7f9fc; border-radius: 14rpx; padding: 14rpx; margin-top: 6rpx; }
.pr-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 8rpx; }
.pr-score { font-size: 30rpx; font-weight: 800; color: #d0860f; }
.pr-score.ok { color: #1f9d6b; }
.pr-verdict { font-size: 24rpx; font-weight: 700; color: #d0860f; }
.pr-verdict.ok { color: #1f9d6b; }
.pr-redo { margin-left: auto; font-size: 22rpx; color: var(--c-primary-deep); background: var(--c-primary-faint); border-radius: var(--r-pill); padding: 4rpx 18rpx; }
.pr-dim { display: flex; align-items: center; gap: 10rpx; flex-wrap: wrap; padding: 5rpx 0; }
.pr-dim-label { font-size: 23rpx; color: #3a414a; font-weight: 600; }
.pr-dots { display: flex; gap: 6rpx; }
.pr-dot { width: 16rpx; height: 16rpx; border-radius: 50%; background: #e2e6ee; }
.pr-dot.on { background: #1f9d6b; }
.pr-dim-note { flex-basis: 100%; font-size: 21rpx; color: #8a93a3; line-height: 1.5; }
.pr-fb { display: block; margin-top: 8rpx; font-size: 22rpx; color: #6b7178; line-height: 1.6; }
.done { text-align: center; }
.done-emoji { font-size: 80rpx; }
.done-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); margin: 16rpx 0; }
.done-stat { font-size: 30rpx; color: var(--c-text-second); line-height: 1.9; }
.done-streak { margin-top: 20rpx; font-size: 34rpx; font-weight: 700; color: var(--c-primary); }
.done-gap { margin-top: 20rpx; font-size: 28rpx; color: var(--c-text-second); }
.checkin-panel { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin: 20rpx 0; }
.cp-summary { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.cp-badges { display: flex; gap: 12rpx; margin: 12rpx 0; flex-wrap: wrap; }
.cp-badge { font-size: 22rpx; color: var(--c-text-hint); opacity: .45; }
.cp-badge.on { color: var(--c-gold); opacity: 1; font-weight: 700; }
.cp-grid { display: flex; flex-wrap: wrap; }
.cp-cell { position: relative; width: 14.28%; height: 60rpx; display: flex; align-items: center; justify-content: center; font-size: 22rpx; color: var(--c-text-body); }
.cell-wrong { position: absolute; top: 2rpx; right: 8rpx; font-size: 16rpx; line-height: 1; color: #fff; background: #ff6b6b; border-radius: 16rpx; padding: 1rpx 6rpx; }
.cp-cell.checked { color: var(--c-gold); font-weight: 700; }
.cp-cell.missable { color: var(--c-text-hint); border: 1rpx dashed var(--c-border); border-radius: 8rpx; }
.cp-cell.blank { visibility: hidden; }
.cp-hint { font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.btn-ghost { background: var(--c-bg-soft); color: var(--c-text-body); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; margin-top: 16rpx; text-align: center; }

/* ── 跟读评分弹窗 ── */
.shadow-modal { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 999; }
/* 跟读会员引导 */
.paywall-card { width: 560rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 40rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; }
.paywall-emoji { font-size: 72rpx; }
.paywall-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); }
.paywall-desc { font-size: 26rpx; color: var(--c-text-second); text-align: center; line-height: 1.6; }
.paywall-card .btn-primary { width: 100%; margin-top: 8rpx; }
.paywall-close { font-size: 26rpx; color: var(--c-text-hint); padding: 8rpx; }
/* 学习设置 */
.hd-right { display: flex; align-items: center; gap: 16rpx; }
.gear { font-size: 32rpx; }
.rep-tag { color: var(--c-primary-deep); font-weight: 700; }
.set-card { width: 580rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 36rpx 32rpx; display: flex; flex-direction: column; gap: 22rpx; }
.set-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); text-align: center; }
.set-row { display: flex; align-items: center; justify-content: space-between; }
.set-label { font-size: 30rpx; color: var(--c-text-body); font-weight: 600; }
.stepper { display: flex; align-items: center; gap: 0; background: var(--c-bg-soft); border-radius: var(--r-pill); overflow: hidden; }
.step-btn { width: 72rpx; height: 64rpx; line-height: 64rpx; text-align: center; font-size: 40rpx; color: var(--c-primary-deep); }
.step-val { width: 88rpx; text-align: center; font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.set-hint { font-size: 22rpx; color: var(--c-text-hint); line-height: 1.6; }
.carry-tip { font-size: 24rpx; color: #d6457e; background: #fff0f5; border-radius: var(--r-md); padding: 12rpx 18rpx; margin-top: 12rpx; }
.done-set { font-size: 24rpx; color: var(--c-text-hint); margin-top: 14rpx; }
.gear-inline { color: var(--c-primary-deep); font-weight: 700; margin-left: 12rpx; }
.addword-input { width: 100%; box-sizing: border-box; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 22rpx 24rpx; font-size: 32rpx; color: var(--c-ink); }
.done-links { display: flex; justify-content: center; gap: 40rpx; margin-top: 16rpx; }
.done-link { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); }
.shadow-card { background: var(--c-bg-card); border-radius: var(--r-xl); padding: 40rpx 36rpx; width: 84%; max-width: 640rpx; display: flex; flex-direction: column; align-items: center; }
.shadow-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); margin-bottom: 20rpx; }
.shadow-sentence { font-size: 32rpx; font-weight: 600; color: var(--c-ink); line-height: 1.6; text-align: center; }
.shadow-tools { margin: 20rpx 0; }
.shadow-demo { font-size: 26rpx; font-weight: 600; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 10rpx 28rpx; border-radius: var(--r-pill); }
.shadow-rec-area { display: flex; flex-direction: column; align-items: center; gap: 12rpx; margin-top: 12rpx; width: 100%; }
.shadow-rec-btn { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); font-size: 30rpx; font-weight: 700; padding: 22rpx 0; width: 100%; }
.shadow-rec-btn.recording { background: var(--c-danger); }
.shadow-rec-btn[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.shadow-hint { font-size: 22rpx; color: var(--c-text-hint); }
.shadow-result { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 18rpx; margin-top: 8rpx; }
.shadow-score { display: flex; align-items: baseline; gap: 10rpx; }
.ss-num { font-size: 80rpx; font-weight: 900; line-height: 1; }
.ss-unit { font-size: 26rpx; color: var(--c-text-second); }
.shadow-score.lv-excellent .ss-num, .shadow-score.lv-good .ss-num { color: #18a058; }
.shadow-score.lv-fair .ss-num { color: var(--c-gold); }
.shadow-score.lv-poor .ss-num { color: var(--c-danger); }
.shadow-dims { display: flex; justify-content: center; gap: 18rpx; margin: 8rpx 0 14rpx; }
.sd { font-size: 22rpx; color: var(--c-text-second); background: var(--c-bg-soft); padding: 4rpx 16rpx; border-radius: var(--r-pill); }
.shadow-words { display: flex; flex-wrap: wrap; gap: 12rpx; justify-content: center; }
.sw-chip { font-size: 24rpx; color: var(--c-text-body); background: var(--c-bg-soft); padding: 6rpx 16rpx; border-radius: var(--r-pill); }
.sw-chip.weak { background: var(--c-danger-bg); color: var(--c-danger); font-weight: 600; }
.sw-score { font-size: 20rpx; opacity: .8; }
.shadow-tip { font-size: 26rpx; color: var(--c-text-second); line-height: 1.6; text-align: center; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx 20rpx; width: 100%; box-sizing: border-box; }
.shadow-actions { display: flex; gap: 16rpx; width: 100%; }
.shadow-actions .half { flex: 1; margin-top: 0; }
.shadow-close { margin-top: 24rpx; font-size: 26rpx; color: var(--c-text-hint); }
</style>
