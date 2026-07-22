<!-- src/pages/vocabulary/index.vue 词力通背词 -->
<template>
  <view class="vocab-page">
    <view v-if="loading" class="center-tip">加载今日任务…</view>

    <!-- 考试模式首屏:打卡 + 两轨 + 频档闯关(词力通=中考/高考考纲词+短语)-->
    <view v-else-if="phase === 'home'" class="exam-home">
      <view class="eh-top">
        <text class="eh-title">词力通</text>
        <text v-if="cal" class="eh-streak">连续 {{ cal.current_streak }} 天</text>
        <view class="eh-gear ic ic-settings" @tap="openSettings" />
      </view>
      <view class="eh-target">
        <text class="eh-target-l">考试目标：<text class="eh-target-v">{{ examOverview?.exam_label || '中考' }}</text></text>
      </view>

      <view v-if="examOverview && !examOverview.available" class="eh-empty">
        该{{ examOverview.exam_label }}考纲词库尚未上架，请联系运营后再来
      </view>

      <template v-else-if="examOverview">
        <!-- 两轨卡 -->
        <view class="eh-tracks">
          <view v-for="t in examOverview.tracks" :key="t.type" class="eh-track" :class="{ on: examTrackSel === t.type }" @tap="examTrackSel = t.type">
            <view class="eh-track-ic" :class="t.type === 'word' ? 'mic-word' : 'mic-phrase'" />
            <text class="eh-track-t">{{ t.title }}</text>
            <text class="eh-track-s">{{ t.studied }} / {{ t.total }}</text>
          </view>
        </view>

        <!-- 频档闯关 -->
        <view class="eh-band-head">
          <text>{{ examOverview.exam_label }}{{ examTrack?.title }} · 按考频闯关</text>
          <text class="eh-band-hint">高频优先</text>
        </view>
        <view class="eh-bands">
          <view v-for="b in (examTrack?.bands || [])" :key="b.band" class="eh-band"
                :class="{ active: isActiveBand(b), done: b.total > 0 && b.studied >= b.total, empty: b.total === 0 }"
                @tap="b.total ? loadExamBand(examTrackSel, b.band) : null">
            <view class="eh-band-fill" :style="{ width: (b.total ? b.studied / b.total * 100 : 0) + '%' }" />
            <view class="eh-band-inner">
              <text class="eh-dots" :class="'d-' + b.band">{{ b.band === 'high' ? '●●●' : b.band === 'mid' ? '●●' : b.band === 'low' ? '●' : '◯' }}</text>
              <view class="eh-band-text">
                <text class="eh-band-t">{{ b.label }}{{ examTrack?.title }}<text v-if="isActiveBand(b)" class="eh-tag"> · 进行中</text></text>
                <text class="eh-band-n">{{ b.total ? (b.studied + ' / ' + b.total) : '暂无词条' }}</text>
              </view>
              <text v-if="b.total === 0 || b.studied >= b.total" class="eh-band-act off">{{ b.total === 0 ? '—' : '已学完' }}</text>
              <text v-else class="eh-band-act" :class="{ primary: isActiveBand(b) }">{{ b.studied > 0 ? '继续' : '去背' }}</text>
            </view>
          </view>
        </view>
      </template>
      <view v-else class="center-tip">加载中…</view>
    </view>

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
        <view class="done-set">每组 {{ wordsPerGroup }} 词 · 每组 {{ repsPerGroup }} 遍 <view class="gear-inline" @tap="openSettings" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-settings" style="width:26rpx;height:26rpx" /><text>设置</text></view><view class="gear-inline" @tap="openAddWord" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-plus" style="width:26rpx;height:26rpx" /><text>添加生词</text></view><view class="gear-inline" @tap="openPins" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-pin" style="width:26rpx;height:26rpx" /><text>优先学</text></view></view>
      </view>
    </view>

    <!-- 学习/复习阶段：词卡（图左+词右，例句/短语，跟读·发音一行）-->
    <view v-else-if="phase === 'study' || phase === 'review'" class="card">
      <!-- 长难句「重点词·本句」语境条 -->
      <view v-if="sentenceCtx" class="kw-ctx"><text class="kw-ctx-lb">来自本句</text><text class="kw-ctx-s">{{ sentenceCtx }}</text></view>
      <view class="study-hd">
        <text class="progress-hint">{{ sentenceCtx ? '本句重点词' : (isReview ? '复习词' : '学新词') }} {{ cardIdx + 1 }} / {{ cardList.length }}<text v-if="repsPerGroup > 1" class="rep-tag"> · 第{{ currentRep }}/{{ repsPerGroup }}遍</text></text>
        <view class="hd-right">
          <view class="seq-toggle" :class="{ on: readSeq }" @tap="readSeq = !readSeq" style="display:flex;align-items:center;gap:6rpx">
            <view class="ic ic-volume" style="width:28rpx;height:28rpx" /><text>连读</text>
          </view>
          <view class="gear" @tap="openPins" style="display:flex;align-items:center"><view class="ic ic-pin" style="width:30rpx;height:30rpx" /></view>
          <view class="gear" @tap="openSettings" style="display:flex;align-items:center"><view class="ic ic-settings" style="width:32rpx;height:32rpx" /></view>
        </view>
      </view>

      <!-- 三关 stepper(A:形→义→用)-->
      <view class="gate-steps">
        <text class="gate-step" :class="{ on: displayGate === 'form', done: displayGate !== 'form' }">形</text>
        <view class="gate-line" :class="{ done: displayGate !== 'form' }" />
        <text class="gate-step" :class="{ on: displayGate === 'meaning', done: displayGate === 'use' }">义</text>
        <view class="gate-line" :class="{ done: displayGate === 'use' }" />
        <text class="gate-step" :class="{ on: displayGate === 'use' }">用</text>
      </view>

      <!-- 图左 + 词/音标/释义右(形关先遮义)-->
      <view class="wc-top">
        <image v-if="firstImage(curStudy)" class="wc-img" :src="firstImage(curStudy)!" mode="aspectFit" />
        <view v-else-if="curStudy.word_id && mediaGen.has(curStudy.word_id)" class="wc-img wc-img-gen"><text>配图生成中…</text></view>
        <view v-else class="wc-img wc-img-mean"><text class="wcm-aa">{{ curStudy.word ? curStudy.word.charAt(0).toUpperCase() : 'A' }}</text></view>
        <view class="wc-info">
          <text class="wc-word">{{ curStudy.word }}</text>
          <text v-if="curStudy.phonetic" class="wc-phon">/{{ cleanPhon(curStudy.phonetic) }}/</text>
          <block v-if="gateStep !== 'form'">
            <text v-for="(d, i) in defList(curStudy)" :key="i" class="wc-mean">{{ d }}</text>
          </block>
          <text v-else class="wc-mean-hidden">先记形音,点下方翻出词义</text>
        </view>
      </view>

      <!-- 例句 / 短语(义关起显示)-->
      <view v-if="gateStep !== 'form' && firstExample(curStudy)" class="wc-row">
        <text class="wc-tag">例句</text>
        <view class="wc-rowtext">
          <text class="wc-en">{{ firstExample(curStudy)!.en }}</text>
          <text v-if="firstExample(curStudy)!.zh" class="wc-zh">{{ firstExample(curStudy)!.zh }}</text>
        </view>
      </view>
      <view v-if="gateStep !== 'form' && firstPhrase(curStudy)" class="wc-row">
        <text class="wc-tag">短语</text>
        <view class="wc-rowtext">
          <text class="wc-en">{{ firstPhrase(curStudy)!.en }}</text>
          <text v-if="firstPhrase(curStudy)!.zh" class="wc-zh">{{ firstPhrase(curStudy)!.zh }}</text>
        </view>
      </view>

      <!-- 单词发音 + 跟读：同一行(上移到考点拓展之前)-->
      <view class="wc-btns">
        <view class="wc-btn" @tap="playCard(curStudy)" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-volume" style="width:30rpx;height:30rpx" /><text>单词发音</text></view>
        <view class="wc-btn primary" @tap="openShadow(firstExample(curStudy)?.en || curStudy.word)" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-mic" style="width:30rpx;height:30rpx;filter:brightness(0) invert(1)" /><text>跟读</text><view v-if="!ent.can('vocab.shadow')" class="ic ic-lock" style="width:28rpx;height:28rpx;filter:brightness(0) invert(1)" /></view>
      </view>

      <!-- 形关推进:翻出词义(A:形→义)-->
      <button v-if="gateStep === 'form'" class="btn-primary gate-next" @tap="toMeaning">认了形音 → 学词义</button>

      <!-- 考点拓展(脑图 + 维度Tab + 词条列表 + 考点扩展测试,下移;点脑图叶子联动列表)-->
      <WordKpExplore v-if="gateStep !== 'form' && kpHasContent"
        :word-kp="wordKp!" :center-text="curStudy.word" :center-zh="wordKp?.gloss || ''"
        :reported="kpReported" :test-loading="kpTestLoading"
        @report="reportKp" @test="openKpTest" />

      <button v-if="gateStep !== 'form'" class="btn-primary" @tap="nextStudy">{{ studyBtnLabel }}</button>
    </view>

    <!-- 成组混合检测(R9.5 防经验主义)：N 句挖空 + 共享词库，答案逐句不同 -->
    <view v-else-if="phase === 'grecep'" class="card">
      <view v-if="grecepLoading" class="grecep-tip">出题中…</view>

      <!-- 逐句即判(闯关) -->
      <template v-else-if="grecepSub === 'quiz'">
        <view class="gg-progress">
          <view v-for="(g, gi) in grecepGroups" :key="gi" class="gg-seg" :class="{ done: gi < grecepGIdx, cur: gi === grecepGIdx }" />
        </view>
        <view class="gg-head">
          <text class="gg-grp">第 {{ grecepGIdx + 1 }} / {{ grecepGroups.length }} 组 · 把词填进句子</text>
          <view class="gg-dots">
            <view v-for="(it, si) in grecepCurGroup" :key="it.word_id" class="gg-dot"
              :class="{ ok: grecepPick[it.word_id] && grecepJudged[it.word_id],
                        no: grecepPick[it.word_id] && !grecepJudged[it.word_id],
                        cur: si === grecepSIdx && !grecepPick[it.word_id] }" />
          </view>
        </view>
        <text class="gg-sent">{{ grecepCurItem && grecepCurItem.sentence }}</text>
        <view class="gg-opts">
          <view v-for="o in grecepCurOpts" :key="o" class="gg-opt"
            :class="{ ok: grecepCurItem && grecepPick[grecepCurItem.word_id] && o === grecepWordText[grecepCurItem.word_id],
                      no: grecepCurItem && grecepPick[grecepCurItem.word_id] === o && o !== grecepWordText[grecepCurItem.word_id] }"
            @tap="grecepPickAnswer(o)">
            <text class="gg-opt-t">{{ o }}</text>
            <text v-if="grecepCurItem && grecepPick[grecepCurItem.word_id] && o === grecepWordText[grecepCurItem.word_id]" class="gg-bdg ok">✓</text>
            <text v-else-if="grecepCurItem && grecepPick[grecepCurItem.word_id] === o" class="gg-bdg no">✗</text>
          </view>
        </view>
        <button v-if="grecepCurItem && grecepPick[grecepCurItem.word_id]" class="btn-primary" @tap="grecepNext">{{ grecepSIdx < grecepCurGroup.length - 1 ? '下一句' : '本组小结 →' }}</button>
      </template>

      <!-- 组小结 -->
      <template v-else-if="grecepSub === 'groupsummary'">
        <view class="gsum">
          <text class="gsum-t">第 {{ grecepGIdx + 1 }} 组完成</text>
          <text class="gsum-score">{{ grecepGroupCorrect }}<text class="gsum-tot">/{{ grecepCurGroup.length }}</text></text>
          <view class="gg-dots big">
            <view v-for="it in grecepCurGroup" :key="it.word_id" class="gg-dot" :class="{ ok: grecepJudged[it.word_id], no: !grecepJudged[it.word_id] }" />
          </view>
        </view>
        <view v-for="it in grecepWrongItems(grecepCurGroup)" :key="it.word_id" class="gsum-wrong">✗ {{ it.sentence }} → <text class="gsum-ans">{{ grecepWordText[it.word_id] }}</text></view>
        <button class="btn-primary" @tap="grecepNextGroup">{{ grecepGIdx < grecepGroups.length - 1 ? ('开始第 ' + (grecepGIdx + 2) + ' 组 →') : '看总结果 →' }}</button>
      </template>

      <!-- 总结果 -->
      <template v-else>
        <view class="gsum">
          <text class="gsum-score">{{ grecepTotalCorrect }}<text class="gsum-tot">/{{ grecepTotal }}</text></text>
          <text class="gsum-t">{{ grecepGroups.length }} 组闯关完成</text>
        </view>
        <view v-for="(g, gi) in grecepGroups" :key="gi" class="gfin-row">
          <text class="gfin-lb">组{{ gi + 1 }}</text>
          <view class="gfin-bars"><view v-for="it in g" :key="it.word_id" class="gfin-bar" :class="{ ok: grecepJudged[it.word_id], no: !grecepJudged[it.word_id] }" /></view>
          <text class="gfin-n">{{ g.filter(it => grecepJudged[it.word_id]).length }}/{{ g.length }}</text>
        </view>
        <button class="btn-primary" @tap="startQuiz">完成 · 进测试</button>
      </template>
    </view>

    <!-- 测试阶段：4 选 1 -->
    <view v-else-if="phase === 'quiz'" class="card">
      <view class="progress-hint">测试 {{ quizIndex + 1 }} / {{ quizQueue.length }} · 正确 {{ correctCount }}</view>
      <view class="quiz-type">{{ quizTypeLabel }}</view>
      <view class="quiz-prompt">
        <text>{{ curQuiz.prompt }}</text>
        <view v-if="curQuiz.mode !== 'm2w' && curQuiz.mode !== 'mcq'" class="qp-play" @tap="playWordAudio(curQuiz.prompt)"><view class="ic ic-volume" style="width:36rpx;height:36rpx" /></view>
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

      <view v-if="answered && curQuiz.explanation" class="quiz-expl">{{ curQuiz.explanation }}</view>
      <button v-if="answered" class="btn-primary" @tap="nextQuiz">下一题</button>
    </view>

    <!-- 完成 -->
    <view v-else-if="phase === 'done'" class="card done">
      <view class="done-emoji" style="display:flex;justify-content:center"><view class="ic ic-check-circle" style="width:80rpx;height:80rpx" /></view>
      <view class="done-title">今日完成！</view>
      <view class="done-stat">新学 {{ newCards.length }} 词 · 复习 {{ reviewCards.length }} 词</view>
      <view v-if="gateUseWords.size" class="done-stat">用关通过(考点测试) {{ gateUseWords.size }}</view>
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
      <view class="done-set">每组 {{ wordsPerGroup }} 词 · 每组 {{ repsPerGroup }} 遍 <view class="gear-inline" @tap="openSettings" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-settings" style="width:26rpx;height:26rpx" /><text>设置</text></view><view class="gear-inline" @tap="openAddWord" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-plus" style="width:26rpx;height:26rpx" /><text>添加生词</text></view><view class="gear-inline" @tap="openPins" style="display:inline-flex;align-items:center;gap:4rpx"><view class="ic ic-pin" style="width:26rpx;height:26rpx" /><text>优先学</text></view></view>
      <button class="btn-primary" @tap="reload">再来一组</button>
      <view class="done-links">
        <view v-if="examBand" class="done-link" @tap="enterHome" style="display:flex;align-items:center;gap:6rpx"><view class="ic ic-book" style="width:30rpx;height:30rpx" /><text>返回词力通</text></view>
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
        <view class="set-row" style="flex-direction:column;align-items:stretch;gap:14rpx">
          <text class="set-label">考试目标（词力通按此出考纲词/短语）</text>
          <view class="exam-seg">
            <text class="exam-seg-btn" :class="{ on: examTargetDraft === 'junior' }" @tap="examTargetDraft = 'junior'">中考</text>
            <text class="exam-seg-btn" :class="{ on: examTargetDraft === 'senior' }" @tap="examTargetDraft = 'senior'">高考</text>
          </view>
        </view>
        <view class="set-row">
          <text class="set-label">每组词数</text>
          <view class="stepper">
            <text class="step-btn" @tap="adjustWPG(-1)">−</text>
            <text class="step-val">{{ settingDraft.words_per_group }}</text>
            <text class="step-btn" @tap="adjustWPG(1)">＋</text>
          </view>
        </view>
        <view class="set-more" @tap="showAdvanced = !showAdvanced">
          <text>高级设置</text><text class="set-more-ar">{{ showAdvanced ? '▴' : '▾' }}</text>
        </view>
        <block v-if="showAdvanced">
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
          <text class="set-hint">同一组重复学几遍加深记忆(默认 1);一个词在本组错够「带入下组」次数,就自动滚入下一组继续考察。</text>
        </block>
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

    <!-- R9.6 优先学清单 + 拍照加词 -->
    <view v-if="pinPanel.open" class="shadow-modal" @tap.self="pinPanel.open = false">
      <view class="pin-card">
        <view class="set-title" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-pin" style="width:30rpx;height:30rpx" /><text>优先学</text></view>
        <view class="pin-tabs">
          <text class="pin-tab" :class="{ on: pinPanel.tab === 'list' }" @tap="switchPinTab('list')">我的优先学</text>
          <text class="pin-tab" :class="{ on: pinPanel.tab === 'pick' }" @tap="switchPinTab('pick')">从词库挑选</text>
        </view>

        <!-- 我的优先学 -->
        <scroll-view v-if="pinPanel.tab === 'list'" scroll-y class="pin-scroll">
          <view v-if="pinPanel.loading" class="pin-empty">加载中…</view>
          <view v-else-if="!pins.length" class="pin-empty">还没有优先学的词。挑选或拍照加入后，会排在最前面学。</view>
          <view v-for="p in pins" :key="p.word_id" class="pin-row">
            <view class="pin-info">
              <text class="pin-word">{{ p.word }}</text>
              <text v-if="p.phonetic" class="pin-ph">/{{ p.phonetic }}/</text>
              <text class="pin-src">{{ p.source === 'photo' ? '拍照' : '挑选' }}</text>
            </view>
            <view class="pin-ops">
              <text class="pin-lv">L{{ p.priority }}</text>
              <view class="pin-step" @tap="bumpPin(p, 1)"><view class="ic ic-plus" style="width:24rpx;height:24rpx" /></view>
              <view class="pin-step" @tap="bumpPin(p, -1)"><view class="ic ic-minus" style="width:24rpx;height:24rpx" /></view>
              <view class="pin-step pin-del" @tap="removePinUI(p)"><view class="ic ic-trash" style="width:24rpx;height:24rpx" /></view>
            </view>
          </view>
        </scroll-view>

        <!-- 从词库挑选 -->
        <scroll-view v-else scroll-y class="pin-scroll">
          <view v-if="pinPanel.loading" class="pin-empty">加载中…</view>
          <view v-else-if="!pinnable.length" class="pin-empty">暂无可挑选的词（作业/试卷/错题与当前学期教材词）。</view>
          <view v-for="w in pinnable" :key="w.word_id" class="pin-row pick"
                :class="{ sel: pickSel.has(w.word_id), done: w.pinned }"
                @tap="!w.pinned && togglePick(w.word_id)">
            <view class="pin-info">
              <text class="pin-word">{{ w.word }}</text>
              <text class="pin-src">{{ ({ paper: '试卷', homework: '作业', wrong: '错题', textbook: '教材' } as Record<string,string>)[w.origin] || w.origin }}</text>
            </view>
            <text v-if="w.pinned" class="pin-flag">已加入</text>
            <view v-else class="pin-check" :class="{ on: pickSel.has(w.word_id) }" />
          </view>
        </scroll-view>

        <view class="pin-actions">
          <button v-if="pinPanel.tab === 'pick'" class="btn-primary" :disabled="!pickSel.size" @tap="confirmPick">加入 {{ pickSel.size || '' }} 词</button>
          <button class="btn-ghost" :disabled="pinPanel.uploading" @tap="doPinFromPhoto">
            <view class="ic ic-camera" style="width:30rpx;height:30rpx;margin-right:6rpx" />拍照加词
          </button>
        </view>
        <text class="set-hint">优先学的词会排在所有来源之前优先学到；级别(L1–L5)越高越靠前。</text>
        <text class="paywall-close" @tap="pinPanel.open = false">关闭</text>
      </view>
    </view>


    <!-- 跟读会员引导（统一会员墙）-->
    <Paywall :open="showPaywall" :feature="ent.feature('vocab.shadow')" emoji="🎤"
      title="跟读评测是会员专享" @close="showPaywall = false" />

    <!-- 考点扩展测试(PracticeQuiz 逐题即时判分,本地按 answer 判,纯练习不进 BKT;完成即过用关) -->
    <PracticeQuiz v-if="kpTestOpen" kp="考点扩展" :questions="kpTestQs" :swapper="kpSwapper" @finish="onKpTestFinish" @finishDetail="onKpDetail" @close="kpTestOpen = false" />
  </view>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { getDailyTask, getCourseIntensiveTask, getHomeworkIntensiveTask, getSentenceKeywordsTask, submitVocabAnswer, checkin, getCheckinCalendar, makeUpCheckin, shadowScore, getVocabSettings, setVocabSettings, addVocabWord, groupRecepProbes, submitGroupRecep, getPins, getPinnable, addPins, setPinPriority, removePin, pinFromPhoto, getExamOverview, getExamDaily, getWordKp, getKpTest, swapKpMcq, reportRelation, recordKpPractice, getQuizMcqs, ensureWordMedia, prewarmWords } from '@/api/vocabulary'
import type { ExamOverview, WordKp, KpTestQuestion, QuizMcq, KpItem } from '@/api/vocabulary'
import { onLoad } from '@dcloudio/uni-app'
import type { ShadowScoreResult, GroupRecepItem, GroupRecepResult, VocabPin, PinnableWord } from '@/api/vocabulary'
import { uploadOneImage } from '@/composables/useUpload'
import type { VocabStudentCalendar } from '@/types/api'
import { resolveSpeakUrl } from '@/utils/tts'
import { useAuthStore } from '@/stores/auth'
import { updateProfile } from '@/api/auth'
import { useEntitlementsStore } from '@/stores/entitlements'
import Paywall from '@/components/Paywall.vue'
import PracticeQuiz from '@/components/PracticeQuiz.vue'
import WordKpExplore from '@/components/WordKpExplore.vue'
import type { VocabWordCard } from '@/types/api'

interface Quiz {
  word_id: string
  mode: 'w2m' | 'm2w' | 'pic' | 'mcq'   // 看词选义 / 看义选词 / 看图选词 / LLM题库选择题
  prompt: string
  options: string[]   // 文本选项；mode==='pic' 时为图片 URL
  answerIndex: number
  explanation?: string   // mcq 模式的解析
}

const auth = useAuthStore()
const loading = ref(true)
const phase = ref<'home' | 'empty' | 'study' | 'review' | 'grecep' | 'quiz' | 'done'>('study')
// 考试模式(词力通首屏两轨×频档;非 scope 进入时)
const examOverview = ref<ExamOverview | null>(null)
const examTrackSel = ref<'word' | 'phrase'>('word')
const examBand = ref<{ type: 'word' | 'phrase'; band: 'high' | 'mid' | 'low' | 'none' } | null>(null)
const examTrack = computed(() =>
  examOverview.value?.tracks.find(t => t.type === examTrackSel.value) || null)
// 进行中的档 = 高→低 第一个「有词且未学完」的档(高频优先)
function isActiveBand(b: { band: string }): boolean {
  const t = examTrack.value
  if (!t) return false
  const first = t.bands.find(x => x.total > 0 && x.studied < x.total)
  return !!first && first.band === b.band
}
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
// 结算统计:本组通过「用关」(= 完成考点扩展测试)的词(去重)
const gateUseWords = reactive(new Set<string>())

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

// ── 三关(A):form(先形音,遮义) → learn(义+用,现有流程)。新词从 form 起;复习词直接 learn ──
const gateStep = ref<'form' | 'learn'>('learn')
// 考点深挖(义关折叠卡,含词族):进 learn 关即拉取(查看即生成),点开才展开
const wordKp = ref<WordKp | null>(null)
const kpOpen = ref(false)
async function loadKp() {
  const wid = curStudy.value?.word_id
  if (!wid) { wordKp.value = null; return }
  wordKp.value = null
  try { wordKp.value = await getWordKp(wid) } catch { wordKp.value = null }
}
const kpHasContent = computed(() => {
  const k = wordKp.value
  return !!k && Array.isArray(k.senses) && k.senses.some(s => s.dims && s.dims.length > 0)
})
// 点关联词(可链词维的项):已入库(有 word_id)的后端已随考点自动排入学习队列,轻提示即可
function learnRelated(it: { text: string; word_id: string | null }) {
  if (!it.word_id) return
  uni.showToast({ title: `${it.text} 已加入学习`, icon: 'none' })
}

// 考点扩展测试:取每维随机 1 道 → PracticeQuiz 逐题即时判分(纯练习,不进 BKT)
const kpTestOpen = ref(false)
const kpTestLoading = ref(false)
const kpTestQs = ref<Array<{ id: string; stem: string; options: string[]; answer: string; explanation: string }>>([])
// 考点扩展测试逐题维度映射(id→{dim,stem}),供做完把错误维回传成练习衍生错题
const kpDimMap = new Map<string, { dim: string; stem: string }>()
const kpTestWid = ref('')
async function openKpTest() {
  const wid = curStudy.value?.word_id
  if (!wid || kpTestLoading.value) return
  kpTestLoading.value = true
  try {
    const qs: KpTestQuestion[] = await getKpTest(wid)
    if (!qs.length) { uni.showToast({ title: '该词暂无考点题', icon: 'none' }); return }
    kpTestWid.value = wid
    kpDimMap.clear()
    qs.forEach(q => kpDimMap.set(q.id, { dim: q.dimension, stem: q.stem }))
    kpTestQs.value = qs.map(q => ({
      id: q.id, stem: `【${q.dimension_label}】${q.stem}`,
      options: q.options, answer: q.answer, explanation: q.explanation,
    }))
    kpTestOpen.value = true
  } catch {
    uni.showToast({ title: '出题失败,稍后重试', icon: 'none' })
  } finally {
    kpTestLoading.value = false
  }
}
// 换一题:报错该题 + 换同维度另一道
async function kpSwapper(q: { id: string }) {
  const nq = await swapKpMcq(q.id) as KpTestQuestion
  if (!nq || !nq.id) return null
  kpDimMap.set(nq.id, { dim: nq.dimension, stem: nq.stem })
  return { id: nq.id, stem: `【${nq.dimension_label}】${nq.stem}`, options: nq.options, answer: nq.answer, explanation: nq.explanation }
}
// 逐题结果回传:错误维 → 练习衍生错题(隔离,不进真实错题);对 → 连对+1达2掌握清除
async function onKpDetail(results: Array<{ id: string; correct: boolean }>) {
  const payload = results
    .map(r => ({ ...kpDimMap.get(r.id), correct: r.correct }))
    .filter((p): p is { dim: string; stem: string; correct: boolean } => !!p.dim)
    .map(p => ({ dim: p.dim, correct: p.correct, stem: p.stem }))
  if (payload.length && kpTestWid.value) {
    try { await recordKpPractice(kpTestWid.value, payload) } catch { /* 静默,不打断学习 */ }
  }
}
// 报错某条考点(点旗标 or 长按 chip):report_count++,即时灰掉,待后台复核/低峰 AI 修正
const kpReported = reactive<Record<string, boolean>>({})
async function reportKp(it: KpItem) {
  if (!it.id || kpReported[it.id]) return
  kpReported[it.id] = true
  try {
    await reportRelation(it.id)
    uni.showToast({ title: '已反馈,待复核', icon: 'none' })
  } catch {
    kpReported[it.id] = false
    uni.showToast({ title: '反馈失败,请重试', icon: 'none' })
  }
}
// 考点测试做完 → 该词过「用关」(纯练习粗判,记入结算统计)
function onKpTestFinish() {
  const wid = curStudy.value?.word_id
  if (wid) gateUseWords.add(wid)
}
watch(() => curStudy.value?.word_id, () => {
  const g: 'form' | 'learn' = curStudy.value?.gate === 'form' ? 'form' : 'learn'
  gateStep.value = g
  wordKp.value = null; kpOpen.value = false
  if (g === 'learn') loadKp()       // 复习词直接进 learn → 拉考点
  ensureCardMedia(curStudy.value)   // 查看即生成:无图则触发后端补图(可画的词)
}, { immediate: true })
// stepper 高亮:形(遮义) / 义(学词义·考点) / 用(考点扩展测试完成)
const displayGate = computed<'form' | 'meaning' | 'use'>(() =>
  gateStep.value === 'form' ? 'form'
    : (curStudy.value?.word_id && gateUseWords.has(curStudy.value.word_id) ? 'use' : 'meaning'))
function toMeaning() {
  gateStep.value = 'learn'
  loadKp()                                      // 形→义:拉考点
  if (readSeq.value) playCard(curStudy.value)   // 翻出词义时连读
}

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
  return m === 'w2m' ? '看词选义' : m === 'm2w' ? '看义选词' : m === 'pic' ? '看图选词' : '选择题'
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

// 查看即生成:进卡无图 → 触发后端生成;生成中/已补图分别用 mediaGen/mediaMap
const mediaMap = ref<Record<string, string>>({})   // word_id → 补生成的图
const mediaGen = ref<Set<string>>(new Set())       // 正在生成的 word_id
const mediaTried = new Set<string>()               // 本会话已试过(不出图=抽象词,不再重试)
function firstImage(w: VocabWordCard): string | null {
  if (w.word_id && mediaMap.value[w.word_id]) return mediaMap.value[w.word_id]
  return w.image_urls && w.image_urls.length ? w.image_urls[0] : null
}
async function ensureCardMedia(w?: VocabWordCard | null) {
  const id = w && w.word_id
  if (!id || firstImage(w!) || mediaTried.has(id)) return   // 有图 / 已试过 → 不动
  mediaTried.add(id)
  mediaGen.value = new Set([...mediaGen.value, id])          // 显示「配图生成中…」
  try {
    const m: any = await ensureWordMedia(id)
    const img = m && (m.image_url || (Array.isArray(m.image_urls) && m.image_urls[0]))
    if (img) mediaMap.value = { ...mediaMap.value, [id]: img }
  } catch { /* 抽象词/失败 → 保持无图,前端降级词义卡 */ }
  finally { const s = new Set(mediaGen.value); s.delete(id); mediaGen.value = s }
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

/* ── R9.5 成组混合接收检测(防经验主义,先于测试)── */
const grecepLoading = ref(false)
const grecepItems = ref<GroupRecepItem[]>([])
const grecepPick = ref<Record<string, string>>({})
// 闯关版(版本2):5 句一组 · 逐句即判 · 组小结 · 总结果
const grecepGroups = ref<GroupRecepItem[][]>([])        // 每 5 句一组
const grecepGroupOpts = ref<string[][]>([])             // 每组 5 词选项(打乱)
const grecepWordText = ref<Record<string, string>>({})  // word_id → 词文本(本地即判)
const grecepJudged = ref<Record<string, boolean>>({})   // word_id → 对错
const grecepGIdx = ref(0)                               // 当前组
const grecepSIdx = ref(0)                               // 组内当前句
const grecepSub = ref<'quiz' | 'groupsummary' | 'final'>('quiz')
const grecepCurGroup = computed(() => grecepGroups.value[grecepGIdx.value] || [])
const grecepCurItem = computed(() => grecepCurGroup.value[grecepSIdx.value] || null)
const grecepCurOpts = computed(() => grecepGroupOpts.value[grecepGIdx.value] || [])
const grecepGroupCorrect = computed(() => grecepCurGroup.value.filter(it => grecepJudged.value[it.word_id]).length)
const grecepTotalCorrect = computed(() => Object.values(grecepJudged.value).filter(Boolean).length)
const grecepTotal = computed(() => grecepItems.value.length)
function _shuffle<T>(a: T[]): T[] {
  const b = a.slice()
  for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]] }
  return b
}
async function startGrecep() {
  const ids = [...new Set([...newCards.value, ...reviewCards.value].map(c => c.word_id))]
  if (!ids.length) { startQuiz(); return }
  grecepLoading.value = true; grecepItems.value = []; grecepPick.value = {}; grecepJudged.value = {}
  grecepGroups.value = []; grecepGroupOpts.value = []; grecepGIdx.value = 0; grecepSIdx.value = 0; grecepSub.value = 'quiz'
  phase.value = 'grecep'
  try {
    const r = await groupRecepProbes(ids)
    grecepItems.value = r.items
    // 少于 2 题时词库会退化 → 直接跳过进测试(≥2 不同答案才防经验主义)
    if (r.items.length < 2) { startQuiz(); return }
    const map: Record<string, string> = {}
    for (const c of [...newCards.value, ...reviewCards.value]) map[c.word_id] = c.word
    grecepWordText.value = map
    // 5 句一组;每组选项 = 组内 5 词(去重打乱)
    const groups: GroupRecepItem[][] = []
    for (let i = 0; i < r.items.length; i += 5) groups.push(r.items.slice(i, i + 5))
    grecepGroups.value = groups
    grecepGroupOpts.value = groups.map(g => _shuffle([...new Set(g.map(it => map[it.word_id]).filter(Boolean))]))
  } catch { startQuiz() }
  finally { grecepLoading.value = false }
}
function grecepPickAnswer(opt: string) {
  const it = grecepCurItem.value
  if (!it || grecepPick.value[it.word_id]) return   // 已答不可改
  grecepPick.value = { ...grecepPick.value, [it.word_id]: opt }
  grecepJudged.value = { ...grecepJudged.value, [it.word_id]: opt === grecepWordText.value[it.word_id] }
}
function grecepNext() {   // 下一句 / 组末 → 组小结
  if (grecepSIdx.value < grecepCurGroup.value.length - 1) grecepSIdx.value++
  else grecepSub.value = 'groupsummary'
}
async function grecepNextGroup() {   // 组小结 → 下一组 / 最后组 → 提交(记 BKT)+ 总结果
  if (grecepGIdx.value < grecepGroups.value.length - 1) {
    grecepGIdx.value++; grecepSIdx.value = 0; grecepSub.value = 'quiz'
  } else {
    try { await submitGroupRecep(grecepPick.value) } catch { /* 记录失败不阻断结算 */ }
    grecepSub.value = 'final'
  }
}
function grecepWrongItems(g: GroupRecepItem[]) { return g.filter(it => !grecepJudged.value[it.word_id]) }

async function startQuiz() {
  const all = [...newCards.value, ...reviewCards.value]
  if (!all.length) { finishSession(); return }
  const modes: Array<'w2m' | 'm2w' | 'pic'> = ['w2m', 'm2w', 'pic']
  // 优先用后端 LLM 题库(每词随机 1 道,变异性好);未缓存的当次回退客户端模板题(下次即有)
  const mcqMap: Record<string, QuizMcq | null> = {}
  try {
    const res = await getQuizMcqs(all.map(c => c.word_id))
    for (const r of res) mcqMap[r.word_id] = r.mcq
  } catch { /* 全回退模板 */ }
  quizQueue.value = all.map((card, i) => {
    const m = mcqMap[card.word_id]
    if (m && m.options && m.options.length >= 2 && m.options.includes(m.answer)) {
      return { word_id: card.word_id, mode: 'mcq' as const, prompt: m.stem, options: m.options,
               answerIndex: m.options.indexOf(m.answer), explanation: m.explanation }
    }
    return buildQuiz(card, modes[i % 3])
  })
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
      startGrecep()
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
    startGrecep()
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

// 精讲「完整词力通流程」:query 带 source=course|homework|sentence → 词集限定单元/批次/本句重点词
const scope = ref<{ source: 'course' | 'homework' | 'sentence'; id: string } | null>(null)
onLoad((q: Record<string, string> = {}) => {
  if (q.source === 'course' && q.unit_id) scope.value = { source: 'course', id: q.unit_id }
  else if (q.source === 'homework' && q.paper_id) scope.value = { source: 'homework', id: q.paper_id }
  else if (q.source === 'sentence' && q.text) {   // 长难句「重点词·本句」:id 存句子文本
    scope.value = { source: 'sentence', id: decodeURIComponent(q.text) }
    uni.setNavigationBarTitle({ title: '重点词' })
  }
})
const sentenceCtx = computed(() => (scope.value?.source === 'sentence' ? scope.value.id : ''))

async function load(fromReload = false) {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  ent.ensure()
  _loadSettings()
  try {
    const task = scope.value
      ? (scope.value.source === 'course'
          ? await getCourseIntensiveTask(scope.value.id)
          : scope.value.source === 'sentence'
              ? await getSentenceKeywordsTask(scope.value.id)
              : await getHomeworkIntensiveTask(scope.value.id))
      : await getDailyTask()
    _applyTask(task, fromReload)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function _loadSettings() {
  getVocabSettings().then((s) => {
    wordsPerGroup.value = s.words_per_group; repsPerGroup.value = s.reps_per_group
    wrongCarryThreshold.value = s.wrong_carry_threshold ?? 2
    settingDraft.words_per_group = s.words_per_group; settingDraft.reps_per_group = s.reps_per_group
    settingDraft.wrong_carry_threshold = s.wrong_carry_threshold ?? 2
  }).catch(() => { /* 用默认 */ })
}

// 把一组任务铺进词卡流(load / 考试出词共用)
function _applyTask(task: { new_words: VocabWordCard[]; review_words: VocabWordCard[] }, fromReload: boolean) {
  // 错词滚入：把上一组错得多的词并入本组复习（去重，且不与本组新词重复）
  const carried = carryWords.value; carryWords.value = []
  const newIds = new Set(task.new_words.map((w) => w.word_id))
  const reviewIds = new Set(task.review_words.map((w) => w.word_id))
  const extra = carried.filter((w) => !newIds.has(w.word_id) && !reviewIds.has(w.word_id))
  newCards.value = task.new_words
  reviewCards.value = [...task.review_words, ...extra]
  pool.value = [...newCards.value, ...reviewCards.value]
  // 学习即预热:后台备好这组词的成组检测探针 + 测试题库(不阻塞,学完进检测/测试就秒出)
  const _pwIds = [...new Set(pool.value.map(c => c.word_id))]
  if (_pwIds.length) prewarmWords(_pwIds).catch(() => { /* 静默 */ })
  studyIndex.value = 0
  reviewIndex.value = 0
  shadowLog.value = []
  currentRep.value = 1
  groupWrong.clear()
  gateUseWords.clear()
  if (newCards.value.length === 0 && reviewCards.value.length === 0) {
    if (fromReload) { uni.showToast({ title: '这组词都练完啦 🎉', icon: 'none' }); return }
    if (examBand.value) { uni.showToast({ title: '这档暂时没有待学/待复习 🎉', icon: 'none' }); phase.value = 'home'; return }
    phase.value = 'empty'
    loadCalendar()
  } else if (newCards.value.length > 0) {
    phase.value = 'study'
    nextTick(() => playCard(curStudy.value))   // 首张词卡自动发声
  } else {
    enterReview()                              // 只有复习词：先过带图词卡再测
  }
}

// 考试模式首屏:两轨×频档概览
async function enterHome() {
  examBand.value = null
  phase.value = 'home'
  loading.value = true
  _loadSettings()
  try { examOverview.value = await getExamOverview() }
  catch { examOverview.value = null }
  finally { loading.value = false }
  loadCalendar()
}

// 学某轨×频档:限定考纲词集,进词卡流
async function loadExamBand(type: 'word' | 'phrase', band: 'high' | 'mid' | 'low' | 'none') {
  examBand.value = { type, band }
  loading.value = true
  try {
    _applyTask(await getExamDaily(type, band), false)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
    phase.value = 'home'
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
  // 考试模式:再来一组接着同轨同档;否则走原 daily/scoped
  if (examBand.value) { loadExamBand(examBand.value.type, examBand.value.band); return }
  load(true)   // 「再来一组」：没词时不跳日历
}

// ── 学习设置 ──
// 设置里的考试目标草稿(中考/高考)
const examTargetDraft = ref<'junior' | 'senior'>('junior')
const showAdvanced = ref(false)   // 高级设置(每组遍数/带入下组)默认收起
function openSettings() {
  showAdvanced.value = false
  settingDraft.words_per_group = wordsPerGroup.value
  settingDraft.reps_per_group = repsPerGroup.value
  settingDraft.wrong_carry_threshold = wrongCarryThreshold.value
  examTargetDraft.value = examOverview.value?.exam_target
    || ((auth.user as any)?.exam_target as 'junior' | 'senior') || 'junior'
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
    // 考试目标变更 → 落库偏好并刷新词力通首屏(换词库)
    const curTarget = examOverview.value?.exam_target || (auth.user as any)?.exam_target || 'junior'
    const targetChanged = examTargetDraft.value !== curTarget
    if (targetChanged) {
      await updateProfile({ exam_target: examTargetDraft.value })
      const u: any = auth.user; if (u) u.exam_target = examTargetDraft.value
    }
    showSettings.value = false
    uni.showToast({ title: '已保存', icon: 'success' })
    if (targetChanged && phase.value === 'home') { examTrackSel.value = 'word'; enterHome() }
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

// ── R9.6 优先学清单 + 拍照加词 ───────────────────────────────────────────
const pinPanel = reactive({
  open: false,
  tab: 'list' as 'list' | 'pick',   // 我的优先学 / 从词库挑选
  loading: false,
  uploading: false,
})
const pins = ref<VocabPin[]>([])
const pinnable = ref<PinnableWord[]>([])
const pickSel = ref<Set<string>>(new Set())

async function openPins() {
  pinPanel.open = true
  pinPanel.tab = 'list'
  await loadPins()
}
async function loadPins() {
  pinPanel.loading = true
  try {
    const r = await getPins()
    pins.value = r.pins || []
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally {
    pinPanel.loading = false
  }
}
async function loadPinnable() {
  pinPanel.loading = true
  try {
    const r = await getPinnable()
    pinnable.value = r.words || []
    pickSel.value = new Set()
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally {
    pinPanel.loading = false
  }
}
function switchPinTab(t: 'list' | 'pick') {
  pinPanel.tab = t
  if (t === 'pick' && !pinnable.value.length) loadPinnable()
}
function togglePick(wid: string) {
  const s = new Set(pickSel.value)
  s.has(wid) ? s.delete(wid) : s.add(wid)
  pickSel.value = s
}
async function confirmPick() {
  const ids = [...pickSel.value]
  if (!ids.length) { uni.showToast({ title: '请先选词', icon: 'none' }); return }
  try {
    const r = await addPins(ids)
    uni.showToast({ title: `已加入 ${r.pinned} 个`, icon: 'success' })
    await loadPins()
    await loadPinnable()
    pinPanel.tab = 'list'
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加入失败', icon: 'none' })
  }
}
async function bumpPin(p: VocabPin, delta: number) {
  const next = Math.max(1, Math.min(5, p.priority + delta))
  if (next === p.priority) return
  try {
    await setPinPriority(p.word_id, next)
    p.priority = next
    pins.value = [...pins.value].sort((a, b) => b.priority - a.priority)
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '调整失败', icon: 'none' })
  }
}
async function removePinUI(p: VocabPin) {
  try {
    await removePin(p.word_id)
    pins.value = pins.value.filter(x => x.word_id !== p.word_id)
    uni.showToast({ title: `已移出「${p.word}」`, icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '移除失败', icon: 'none' })
  }
}
function doPinFromPhoto() {
  uni.chooseImage({
    count: 1,
    success: async (res: any) => {
      const path = res.tempFilePaths?.[0]
      if (!path) return
      pinPanel.uploading = true
      uni.showLoading({ title: '识别中…', mask: true })
      try {
        const url = await uploadOneImage(path)
        const r = await pinFromPhoto(url)
        uni.hideLoading()
        if (!r.pinned.length) {
          uni.showToast({ title: r.recognized ? '未匹配到词典词' : '未识别到英文', icon: 'none' })
        } else {
          uni.showToast({ title: `加入 ${r.pinned.length} 个，${r.not_found.length} 个未收录`, icon: 'none' })
          await loadPins()
          pinPanel.tab = 'list'
        }
      } catch (e) {
        uni.hideLoading()
        uni.showToast({ title: (e as Error).message || '拍照加词失败', icon: 'none' })
      } finally {
        pinPanel.uploading = false
      }
    },
  })
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

// 从课程/作业精讲带 scope 进来 → 直接进对应词集学习;否则 → 考试两轨首屏
onMounted(() => { if (scope.value) load(); else enterHome() })
</script>

<style scoped>
.vocab-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 40rpx; color: var(--c-text-hint); line-height: 1.8; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 40rpx 32rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,0.04); }
.progress-hint { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 24rpx; }
/* 学新词词卡（图左+词右）*/
/* 长难句「重点词·本句」语境条 */
.kw-ctx { background: #e7effc; border: 1rpx solid #cfe0fa; border-radius: 12rpx; padding: 14rpx 18rpx; margin-bottom: 18rpx; }
.kw-ctx-lb { display: block; font-size: 20rpx; font-weight: 700; color: #3a6bc0; margin-bottom: 4rpx; }
.kw-ctx-s { font-size: 24rpx; color: var(--c-ink); line-height: 1.5; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.study-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
/* 三关 stepper(A) */
.gate-steps { display: flex; align-items: center; justify-content: center; gap: 10rpx; margin-bottom: 22rpx; }
.gate-step { width: 46rpx; height: 46rpx; border-radius: 50%; text-align: center; line-height: 46rpx; font-size: 24rpx; font-weight: 700; color: #94a3b8; background: #F1F4F8; }
.gate-step.on { color: #fff; background: #3d8bf5; }
.gate-step.done { color: #185FA5; background: #E6F1FB; }
.gate-line { width: 44rpx; height: 4rpx; border-radius: 2rpx; background: #E3ECF7; }
.gate-line.done { background: #B5D4F4; }
.wc-mean-hidden { font-size: 26rpx; color: #94a3b8; }
.gate-next { margin-top: 8rpx; }
/* 词族(G) */
.kp-box { background: #EEF5FF; border: 1rpx solid #B5D4F4; border-radius: 16rpx; margin: 8rpx 0 20rpx; overflow: hidden; }
.kp-toggle { display: flex; align-items: center; gap: 8rpx; padding: 16rpx 18rpx; }
.kp-toggle-t { flex: 1; font-size: 26rpx; color: #185FA5; font-weight: 600; }
.kp-arrow { font-size: 24rpx; color: #6A9BD8; transition: transform .2s; }
.kp-arrow.open { transform: rotate(180deg); }
.kp-body { padding: 0 18rpx 16rpx; }
.kp-sense + .kp-sense { margin-top: 16rpx; border-top: 2rpx solid #C9DEF7; padding-top: 14rpx; }
.kp-sense-h { display: flex; align-items: baseline; gap: 10rpx; padding-top: 6rpx; }
.kp-sense-gloss { font-size: 26rpx; font-weight: 700; color: #0C447C; }
.kp-sense-pos { font-size: 20rpx; color: #185FA5; background: #E6F1FB; padding: 2rpx 12rpx; border-radius: 8rpx; }
.kp-sec { padding-top: 14rpx; margin-top: 14rpx; border-top: 1rpx solid #DCEAFB; }
.kp-sec:first-child { border-top: none; margin-top: 0; padding-top: 4rpx; }
.kp-sec-h { display: block; font-size: 22rpx; color: #6A8CB5; margin-bottom: 8rpx; }
.kp-line { display: flex; align-items: baseline; gap: 12rpx; margin: 4rpx 0; }
.kp-en { font-size: 26rpx; color: #0C447C; font-weight: 500; }
.kp-zh { flex: 1; font-size: 24rpx; color: #4A6785; }
.kp-chips { display: flex; flex-wrap: wrap; gap: 10rpx; }
.kp-chip { font-size: 24rpx; color: #0C447C; background: #D6E6FA; padding: 6rpx 16rpx; border-radius: 10rpx; }
.kp-chip.low { background: #F1EFE8; color: #8a857c; }
.kp-low { font-size: 18rpx; color: #b0a99e; }
.kp-chip.link { background: #C3DEFA; border: 1rpx solid #8FBDEF; }
.kp-chip-zh { color: #4A6785; font-size: 22rpx; }
.kp-chip.reported { opacity: .4; text-decoration: line-through; }
.kp-line { display: flex; align-items: flex-start; justify-content: space-between; gap: 12rpx; }
.kp-line-body { flex: 1; min-width: 0; }
.kp-line.reported { opacity: .4; text-decoration: line-through; }
.kp-report.ic { width: 30rpx; height: 30rpx; flex-shrink: 0; margin-top: 4rpx; opacity: .5; }
.kp-report.ic.done { opacity: .25; }
.kp-en.link { color: #2F7BDB; text-decoration: underline; }
.kp-tips { display: block; font-size: 24rpx; color: #4A6785; line-height: 1.6; }
.study-hd .progress-hint { margin-bottom: 0; }
.seq-toggle { font-size: 24rpx; color: var(--c-text-hint); }
.seq-toggle.on { color: var(--c-primary-deep); font-weight: 600; }
.wc-top { display: flex; gap: 20rpx; padding-bottom: 20rpx; border-bottom: 1rpx solid var(--c-bg-soft); }
.wc-img { width: 300rpx; height: 280rpx; border-radius: 16rpx; flex-shrink: 0; background: var(--c-bg-soft); }
.wc-img-empty { display: flex; align-items: center; justify-content: center; font-size: 80rpx; opacity: .5; }
.wc-img-gen { display: flex; align-items: center; justify-content: center; font-size: 24rpx; color: #185FA5; background: #EEF5FF; }
.wc-img-mean { display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #EEF5FF, #E6F1FB); }
.wcm-aa { font-size: 96rpx; font-weight: 900; color: #B5D4F4; font-family: Georgia, 'Times New Roman', serif; }
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
.quiz-expl { font-size: 24rpx; color: #185FA5; background: #EEF5FF; border-radius: 12rpx; padding: 14rpx 18rpx; margin: 6rpx 0 14rpx; line-height: 1.6; }
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
/* R9.5 成组混合检测 */
.grecep-tip { text-align: center; color: #9aa3b0; font-size: 26rpx; padding: 30rpx 0; }
/* 成组检测·闯关版(版本2:5词/组 + 逐句即判 + 组小结 + 总结果) */
.gg-progress { display: flex; gap: 8rpx; margin-bottom: 12rpx; }
.gg-seg { flex: 1; height: 10rpx; border-radius: 5rpx; background: #E3ECF7; }
.gg-seg.cur { background: #3d8bf5; }
.gg-seg.done { background: #18a058; }
.gg-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 22rpx; }
.gg-grp { font-size: 24rpx; color: #94a3b8; }
.gg-dots { display: flex; gap: 12rpx; }
.gg-dot { width: 20rpx; height: 20rpx; border-radius: 50%; background: #dfe4ea; }
.gg-dot.cur { background: #3d8bf5; transform: scale(1.15); }
.gg-dot.ok { background: #18a058; }
.gg-dot.no { background: #e35b5b; }
.gg-dots.big .gg-dot { width: 28rpx; height: 28rpx; }
.gg-sent { display: block; font-size: 34rpx; color: #0C447C; line-height: 1.5; font-weight: 600; margin-bottom: 26rpx; }
.gg-opts { display: flex; flex-direction: column; gap: 14rpx; margin-bottom: 24rpx; }
.gg-opt { display: flex; align-items: center; justify-content: space-between; background: #fff; border: 2rpx solid #E6EEF7; border-radius: 16rpx; padding: 22rpx 26rpx; }
.gg-opt.ok { background: #E6F8EE; border-color: #18a058; }
.gg-opt.no { background: #FBEAEC; border-color: #e35b5b; }
.gg-opt-t { font-size: 30rpx; color: #0C447C; }
.gg-opt.ok .gg-opt-t { color: #0F6E56; font-weight: 700; }
.gg-opt.no .gg-opt-t { color: #c0392b; }
.gg-bdg { font-size: 30rpx; }
.gg-bdg.ok { color: #18a058; }
.gg-bdg.no { color: #e35b5b; }
/* 组小结 / 总结果 */
.gsum { text-align: center; margin: 20rpx 0 16rpx; }
.gsum-t { display: block; font-size: 30rpx; font-weight: 700; color: #0C447C; }
.gsum-score { display: block; font-size: 84rpx; font-weight: 900; color: #3d8bf5; line-height: 1.1; margin: 8rpx 0; }
.gsum-tot { font-size: 40rpx; color: #94a3b8; }
.gsum-wrong { font-size: 24rpx; color: #c0392b; background: #FBEAEC66; border-radius: 12rpx; padding: 12rpx 16rpx; margin-bottom: 10rpx; line-height: 1.5; }
.gsum-ans { font-weight: 700; }
.gfin-row { display: flex; align-items: center; gap: 14rpx; margin-bottom: 12rpx; }
.gfin-lb { font-size: 24rpx; color: #94a3b8; width: 56rpx; }
.gfin-bars { flex: 1; display: flex; gap: 6rpx; }
.gfin-bar { flex: 1; height: 14rpx; border-radius: 7rpx; background: #18a058; }
.gfin-bar.no { background: #e35b5b; }
.gfin-n { font-size: 24rpx; color: #0C447C; }
/* R9.1 理解检测·语境填空 */
.probe-box { margin-top: 22rpx; padding-top: 18rpx; border-top: 1rpx solid #f0f2f5; }
.probe-cta { display: flex; align-items: center; justify-content: center; gap: 10rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border-radius: var(--r-pill); padding: 16rpx 0; font-size: 26rpx; font-weight: 700; }
.probe-cta:active { opacity: .85; }
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
.set-more { display: flex; align-items: center; justify-content: center; gap: 6rpx; font-size: 24rpx; color: #185FA5; padding: 8rpx 0; }
.set-more-ar { font-size: 22rpx; }
.set-label { font-size: 30rpx; color: var(--c-text-body); font-weight: 600; }
.stepper { display: flex; align-items: center; gap: 0; background: var(--c-bg-soft); border-radius: var(--r-pill); overflow: hidden; }
.step-btn { width: 72rpx; height: 64rpx; line-height: 64rpx; text-align: center; font-size: 40rpx; color: var(--c-primary-deep); }
.step-val { width: 88rpx; text-align: center; font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.set-hint { font-size: 22rpx; color: var(--c-text-hint); line-height: 1.6; }
.carry-tip { font-size: 24rpx; color: #d6457e; background: #fff0f5; border-radius: var(--r-md); padding: 12rpx 18rpx; margin-top: 12rpx; }
.done-set { font-size: 24rpx; color: var(--c-text-hint); margin-top: 14rpx; }
.gear-inline { color: var(--c-primary-deep); font-weight: 700; margin-left: 12rpx; }
.addword-input { width: 100%; box-sizing: border-box; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 22rpx 24rpx; font-size: 32rpx; color: var(--c-ink); }
/* R9.6 优先学 */
.pin-card { width: 620rpx; max-height: 80vh; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 32rpx 28rpx; display: flex; flex-direction: column; gap: 20rpx; }
.pin-tabs { display: flex; background: var(--c-bg-soft); border-radius: var(--r-pill); padding: 6rpx; }
.pin-tab { flex: 1; text-align: center; font-size: 27rpx; font-weight: 700; color: var(--c-text-hint); padding: 14rpx 0; border-radius: var(--r-pill); }
.pin-tab.on { background: var(--c-bg-card); color: var(--c-primary-deep); box-shadow: 0 2rpx 8rpx rgba(61,139,245,.12); }
.pin-scroll { max-height: 46vh; }
.pin-empty { font-size: 26rpx; color: var(--c-text-hint); text-align: center; padding: 60rpx 20rpx; line-height: 1.7; }
.pin-row { display: flex; align-items: center; justify-content: space-between; padding: 18rpx 8rpx; border-bottom: 2rpx solid var(--c-bg-soft); }
.pin-info { display: flex; align-items: center; gap: 12rpx; flex: 1; min-width: 0; }
.pin-word { font-size: 32rpx; font-weight: 700; color: var(--c-ink); }
.pin-ph { font-size: 24rpx; color: var(--c-text-hint); }
.pin-src { font-size: 21rpx; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 4rpx 12rpx; border-radius: var(--r-pill); }
.pin-ops { display: flex; align-items: center; gap: 12rpx; }
.pin-lv { font-size: 24rpx; font-weight: 800; color: var(--c-primary-deep); min-width: 44rpx; text-align: center; }
.pin-step { width: 48rpx; height: 48rpx; display: flex; align-items: center; justify-content: center; background: var(--c-bg-soft); border-radius: var(--r-md); }
.pin-step.pin-del .ic { filter: none; }
.pin-row.pick { transition: background .15s; }
.pin-row.pick.sel { background: var(--c-primary-faint); border-radius: var(--r-md); }
.pin-row.pick.done { opacity: .55; }
.pin-flag { font-size: 22rpx; color: var(--c-text-hint); }
.pin-check { width: 36rpx; height: 36rpx; border: 3rpx solid var(--c-border); border-radius: 50%; }
.pin-check.on { background: var(--c-primary); border-color: var(--c-primary); }
.pin-actions { display: flex; flex-direction: column; gap: 0; }
.pin-actions .btn-primary { margin-top: 8rpx; }
.pin-actions .btn-ghost { display: flex; align-items: center; justify-content: center; }
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

/* ── 考试模式首屏(纯蓝:两轨 + 频档闯关)────────────────────────────────── */
.exam-home { padding: 8rpx 4rpx 24rpx; }
.eh-top { display: flex; align-items: center; margin-bottom: 16rpx; }
.eh-title { font-size: 38rpx; font-weight: 800; color: #0C447C; }
.eh-streak { margin-left: auto; font-size: 24rpx; font-weight: 600; color: #185FA5; background: #E6F1FB; padding: 6rpx 18rpx; border-radius: 999rpx; }
.eh-gear { width: 44rpx; height: 44rpx; margin-left: 16rpx; flex-shrink: 0; }
/* 考试目标段选(设置弹窗内) */
.exam-seg { display: flex; gap: 12rpx; }
.exam-seg-btn { flex: 1; text-align: center; font-size: 28rpx; font-weight: 600; color: #185FA5; background: #EEF5FF; padding: 16rpx 0; border-radius: 12rpx; }
.exam-seg-btn.on { color: #fff; background: var(--c-primary); }
.eh-target { display: flex; align-items: center; margin-bottom: 20rpx; font-size: 24rpx; color: #185FA5; }
.eh-target-v { color: #0C447C; font-weight: 700; }
.eh-empty { text-align: center; padding: 80rpx 40rpx; color: var(--c-text-hint); font-size: 26rpx; line-height: 1.8; }
/* 两轨卡 */
.eh-tracks { display: flex; gap: 20rpx; margin-bottom: 24rpx; }
.eh-track { flex: 1; background: var(--c-bg-card); border: 3rpx solid var(--c-border); border-radius: 26rpx; padding: 24rpx; display: flex; flex-direction: column; gap: 6rpx; }
.eh-track.on { background: #EEF5FF; border-color: var(--c-primary); }
.eh-track-ic { width: 46rpx; height: 46rpx; background-repeat: no-repeat; background-position: center; background-size: contain; }
.eh-track-t { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.eh-track.on .eh-track-t { color: #0C447C; }
.eh-track-s { font-size: 24rpx; color: var(--c-text-hint); }
.eh-track.on .eh-track-s { color: #185FA5; }
/* 频档闯关 */
.eh-band-head { display: flex; align-items: center; margin-bottom: 16rpx; font-size: 26rpx; font-weight: 700; color: #0C447C; }
.eh-band-hint { margin-left: auto; font-size: 22rpx; font-weight: 400; color: #185FA5; }
.eh-bands { display: flex; flex-direction: column; gap: 18rpx; }
.eh-band { position: relative; overflow: hidden; display: flex; align-items: center; background: var(--c-bg-card); border: 1rpx solid var(--c-border); border-radius: 24rpx; padding: 26rpx 24rpx; }
.eh-band.active { background: #EEF5FF; border: 3rpx solid var(--c-primary); }
.eh-band.empty { opacity: .6; }
.eh-band.done { opacity: .8; }
.eh-band-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: #B5D4F4; transition: width .3s; }
.eh-band.active .eh-band-fill { background: #B5D4F4; }
.eh-band:not(.active) .eh-band-fill { background: #E6F1FB; }
.eh-band-inner { position: relative; display: flex; align-items: center; gap: 20rpx; width: 100%; }
.eh-dots { font-size: 26rpx; letter-spacing: 3rpx; flex: none; }
.eh-dots.d-high { color: #2b6fd6; }
.eh-dots.d-mid { color: #5b8fd6; }
.eh-dots.d-low { color: #aab6c8; }
.eh-dots.d-none { color: #c4ccd6; }
.eh-band-text { flex: 1; display: flex; flex-direction: column; gap: 4rpx; min-width: 0; }
.eh-band-t { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.eh-band.active .eh-band-t { color: #0C447C; }
.eh-tag { font-size: 22rpx; color: #185FA5; font-weight: 600; }
.eh-band-n { font-size: 24rpx; color: var(--c-text-hint); }
.eh-band.active .eh-band-n { color: #185FA5; }
.eh-band-act { flex: none; font-size: 24rpx; color: #185FA5; }
.eh-band-act.primary { color: #fff; background: var(--c-primary); padding: 10rpx 28rpx; border-radius: 999rpx; font-weight: 600; }
.eh-band-act.off { color: var(--c-text-hint); }
/* 两轨图标(线性 SVG,主色蓝 #185FA5) */
.mic-word { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23185FA5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E%3C/svg%3E"); }
.mic-phrase { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23185FA5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'/%3E%3C/svg%3E"); }
</style>
