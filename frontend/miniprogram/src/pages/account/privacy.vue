<template>
  <scroll-view scroll-y class="page">

    <view class="section">
      <text class="h1">隐私政策</text>
      <text class="updated">版本 v1.0　更新日期：2026 年 5 月 29 日</text>
      <text class="notice">⚠️ 正式上线前须由法律专业人员审核并替换占位符。</text>
    </view>

    <view class="section">
      <text class="h2">一、引言</text>
      <text class="body">【运营方公司全称】（下称"我们"）非常重视您的隐私和个人信息安全。本隐私政策说明：我们收集哪些信息、为什么收集、如何使用/存储/共享，以及您的权利与控制方式。本政策适用于 engGramer 微信小程序（下称"本产品"）。请您仔细阅读并理解本政策内容。</text>
    </view>

    <view class="section">
      <text class="h2">二、我们收集哪些个人信息</text>
      <text class="body-bold">2.1 注册与账号信息</text>
      <text class="body">• 微信 OpenID：微信登录时，用于唯一标识您的账号（必需）{"\n"}• 昵称、头像：微信授权时可选提供，用于展示用户身份（可选）{"\n"}• 出生年份：完善资料时填写，用于年龄分层保护（必需）{"\n"}• 手机号：完善资料/注销/关键操作验证（可选）{"\n"}• 监护人手机号：14 岁以下注册时，用于监护人授权验证（14 岁以下必需）</text>
      <text class="body-bold">2.2 业务数据</text>
      <text class="body">• 错题图片：您上传时，用于 OCR+AI 分析、错题归档{"\n"}• 题目文字、答题内容：OCR 识别/您编辑，用于 AI 诊断分析{"\n"}• 教材版本、年级、学期：您填写，用于个性化题库匹配（可选）{"\n"}• AI 分析结果、练习记录：自动产生，用于学情报告</text>
      <text class="body-bold">2.3 设备与日志信息</text>
      <text class="body">• IP 地址：每次访问，用于防滥用、归属城市识别{"\n"}• 设备型号、操作系统：用于适配显示、问题排查{"\n"}• 操作日志：用于故障排查、安全审计（保留 6 个月）</text>
      <text class="body-bold">2.4 支付信息</text>
      <text class="body">• 订单金额、订单号、支付时间：用于订单管理（保留 5 年）{"\n"}• 微信支付交易号：用于财务核账{"\n"}我们不收集、不存储您的银行卡号、CVV、微信支付密码或余额——支付过程全部由微信官方完成。</text>
      <text class="body-bold">2.5 我们不收集的信息</text>
      <text class="body">位置（GPS/Wi-Fi/基站）、通讯录、相册（除您主动选择的错题图片）、麦克风/摄像头（除您主动调用扫码）、真实姓名/身份证号。</text>
    </view>

    <view class="section">
      <text class="h2">三、未成年人信息的特别保护</text>
      <text class="body">依据《未成年人网络保护条例》（2023 年 9 月 1 日）：{"\n"}• &lt;14 岁：必须填写监护人手机号，监护人通过验证后账号方可激活。监护人手机号仅用于授权验证+重要通知（如消费提醒），不用于营销。{"\n"}• 14-17 岁：首次购买会员需勾选"已告知监护人并获得同意"。{"\n"}• 全部未成年人：学情数据不传输至任何第三方；不对 14 岁以下用户推送商业促销；默认关闭排名等社交功能；单笔消费同步通知已绑定的亲人。</text>
    </view>

    <view class="section">
      <text class="h2">四、如何使用您的信息</text>
      <text class="body">核心服务：题目 OCR 识别（阿里云印刷体+腾讯云手写体）、AI 错题分析（DeepSeek）、个性化学情报告、题库练习、老师批注/班级管理、亲人查看学情+代付会员。{"\n"}{"\n"}安全与合规：反作弊、内容审核、防账号被盗、配合监管要求。{"\n"}{"\n"}改进与统计：脱敏聚合后的产品数据分析、AI 模型迭代训练（脱敏后）。我们承诺：脱敏聚合后的数据不可关联到具体个人。</text>
    </view>

    <view class="section">
      <text class="h2">五、信息存储与安全</text>
      <text class="body">• 服务器位于中华人民共和国境内（阿里云/腾讯云）{"\n"}• 错题图片存储在腾讯云 COS（私有桶，加密传输）{"\n"}• 数据库：加密存储敏感字段，访问受限{"\n"}{"\n"}存储期限：账号基础信息保留至您注销+30 天；错题数据注销后脱敏归档；订单与支付记录保留 5 年（财务合规）；操作日志保留 6 个月。{"\n"}{"\n"}安全措施：HTTPS 全链路加密、JWT 双 token 身份认证、行级数据隔离。如发生信息泄露，我们将在 72 小时内通知您并报告监管部门。</text>
    </view>

    <view class="section">
      <text class="h2">六、信息共享与对外提供</text>
      <text class="body">与第三方服务商共享（最小必要范围）：{"\n"}• 阿里云 OCR：错题图片，用于印刷体识别{"\n"}• 腾讯云 OCR：错题图片，用于手写体识别{"\n"}• 腾讯云 COS：错题图片存储{"\n"}• DeepSeek API：题目+作答文字，用于 AI 诊断{"\n"}• 微信支付：订单金额/订单号，用于支付处理{"\n"}• 短信服务商：手机号+验证码，用于 SMS 验证{"\n"}{"\n"}所有第三方服务商均与我们签订数据保护协议，承诺仅按我们指示处理数据、不再次共享、定期销毁。{"\n"}{"\n"}与老师/亲人共享（您授权后）：您主动绑定后，对方可查看您的错题/学情；您可随时解绑。{"\n"}{"\n"}我们不会将您的个人信息出售给任何第三方，不用于本政策未明示的其他目的。</text>
    </view>

    <view class="section">
      <text class="h2">七、您的权利</text>
      <text class="body">依据《个人信息保护法》第 44-50 条，您享有：{"\n"}• 知情权：阅读本政策；变更将公示至少 7 天{"\n"}• 决定权：您可选择是否提供可选信息{"\n"}• 查阅复制权：联系客服申请导出全部数据{"\n"}• 更正权：在"我的"中修改信息{"\n"}• 删除权："我的→账号设置→注销账号"或联系客服{"\n"}• 撤回同意权：可随时解绑老师/亲人{"\n"}• 拒绝自动化决策权：可申诉 AI 分析结果，由人工复核{"\n"}• 可携带权：联系客服申请数据迁移{"\n"}{"\n"}行使权利：客服邮箱【support@yourdomain.com】，15 个工作日内响应。</text>
    </view>

    <view class="section">
      <text class="h2">八、账号注销</text>
      <text class="body">入口：我的→账号设置→注销账号{"\n"}流程：申请 → 短信验证 → 30 天冷静期（可撤销）→ 期满自动执行{"\n"}执行后：个人可识别信息匿名化；学情数据脱敏保留作产品统计；订单记录依财务合规保留 5 年。注销后不可恢复；剩余会员时长不退款（详见用户协议 §4.3）。</text>
    </view>

    <view class="section">
      <text class="h2">九、本地存储</text>
      <text class="body">本产品在您的微信小程序客户端本地存储：access_token（JWT 短期凭证，保持登录态）、refresh_token（JWT 长期凭证，自动续签）、用户基础信息缓存（减少网络请求）。清除微信小程序缓存即可清除以上信息。</text>
    </view>

    <view class="section">
      <text class="h2">十、未成年人监护人通道</text>
      <text class="body">如您是未成年人的监护人，发现孩子未经授权使用、上传不当内容或未经授权付费，请联系：{"\n"}客服邮箱：【minor@yourdomain.com】{"\n"}提供材料：监护人身份证 + 与孩子关系证明 + 书面说明{"\n"}我们将在 3 个工作日内响应处理。</text>
    </view>

    <view class="section">
      <text class="h2">十一、政策变更</text>
      <text class="body">本政策可能根据法律法规变化修订；重大修订将公示至少 7 天并要求您重新同意。您继续使用本产品视为接受修订。</text>
    </view>

    <view class="section">
      <text class="h2">十二、联系我们</text>
      <text class="body">客服邮箱：【support@yourdomain.com】{"\n"}数据保护官（DPO）：【dpo@yourdomain.com】{"\n"}客服电话：【400-XXX-XXXX】{"\n"}公司地址：【XXX 市 XXX 区 XXX 街 XXX 号】</text>
    </view>

    <view class="section">
      <text class="body-hint">生效日期：【2026 年 X 月 X 日】　版本号：v1.0</text>
    </view>

  </scroll-view>
</template>

<style scoped>
.page { padding: 32rpx 28rpx; background: var(--c-bg-page); min-height: 100vh; box-sizing: border-box; }
.section { margin-bottom: 36rpx; }
.h1 { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; margin-bottom: 8rpx; }
.updated { font-size: 24rpx; color: var(--c-text-hint); display: block; margin-bottom: 8rpx; }
.notice { font-size: 22rpx; color: var(--c-orange); display: block; background: #fff8e7; border-radius: 8rpx; padding: 8rpx 12rpx; }
.h2 { font-size: 30rpx; font-weight: 700; color: var(--c-ink); display: block; margin-bottom: 12rpx; }
.body { font-size: 26rpx; color: var(--c-text-body); line-height: 1.8; display: block; margin-bottom: 12rpx; }
.body-bold { font-size: 26rpx; font-weight: 700; color: var(--c-ink); display: block; margin-top: 16rpx; margin-bottom: 6rpx; }
.body-hint { font-size: 22rpx; color: var(--c-text-hint); line-height: 1.6; display: block; }
</style>
