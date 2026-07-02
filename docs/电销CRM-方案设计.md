# 电销 CRM 方案设计(平台自用 · 预留机构扩展)

> 目标:admin 后台内建一套「线索 → 外呼 → 分析 → 跟进」闭环的电销 CRM,用于向商家/机构推销本产品。
> 定位:**平台自用优先**,数据模型预留 `institution_id` 维度,打磨成熟后再开机构端(机构需求不同,按需扩)。
> 依据:本方案的功能选型来自一轮深研(探迹拓客、Gong/循环智能/Megaview、企微会话存档官方文档),结论见文末「来源」。

---

## 0. 设计铁律(对齐 CLAUDE.md)

- **地区一律走 `region_service`**:线索的省/市存 `region_code`(与 `user.city_code` 同源),不写死城市清单;文本取城市用 `region_from_name`。
- **列表页必须分页**:所有线索/跟进列表后端 `skip/limit/total`,前端 `el-pagination`;筛选变更走 `reload()` 回第一页。
- **运营可配置值读后台**:公海回收天数、拨打时段、意向权重、ASR/企微开关等一律入 `system_configs`,禁写死。
- **图标线性 SVG / Element Plus 图标**,不用 emoji。

---

## 1. 范围与分期

| 期 | 内容 | 第三方依赖 |
|---|---|---|
| **P0(MVP)** | 线索库 + 公海/私海 + 认领/回收 + 按 region 派单 + 跟进记录/待办 + 导入/录入 + 分页页面 + DNC/consent + **赢单画像反查推荐(纯查询)** | 无 |
| **P1** | 云呼叫中心外呼 + 录音 + ASR + **意向分析 LLM** + 回填跟进 | 呼叫中心、云 ASR |
| **P2** | **企微会话存档接入** + 会话分析(复用意向管道) | 企微会话存档 |
| **P3** | `institution_id` 生效 + 机构维度隔离,开机构端 | — |

**P1/P2 的能力现在就把字段/接入位建好(nullable 列 + 预留接口),不接第三方也能跑 P0。**

---

## 2. 数据模型

新建领域模型文件 `app/models/d23_sales_crm.py`,迁移 `mXXX_sales_crm`(幂等)。

### 2.1 `sales_lead`(线索/商家)

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | |
| `name` | str | 商家/机构名 |
| `contact_name` | str? | 联系人 |
| `phone` | str? | 电话(外呼主键) |
| `wechat_id` | str? | 微信/企微 external_userid |
| `address` | str? | |
| `region_code` | str? | **走 region_service**,省/市码 |
| `region_name` | str? | 冗余展示名 |
| `industry` | str? | 行业标签 |
| `biz_tags` | JSONB? | 经营特征(招聘/推广/资质…,借探迹维度分层) |
| `source` | enum | `baidu_map/meituan/dianping/tungee/manual/import/other` |
| `source_note` | str? | **合规:来源与合法性依据** |
| `status` | enum | `new→contacted→interested→negotiating→won/lost/invalid` |
| `intent_score` | int? | 0–100,最新意向分(P1 由分析回填) |
| `intent_grade` | char? | `A/B/C/D`(意向分层,借 Megaview) |
| `product_feedback` | JSONB? | 产品意见原始抽取(聚类前) |
| `similar_score` | float? | **赢单画像反查得分**(见 §3) |
| `consent` | bool | 是否同意营销联系,默认 false |
| `dnc` | bool | 拒接名单;**true → 系统禁呼** |
| `pool` | enum | `public/private`(公海/私海) |
| `owner_admin_id` | UUID? | 私海归属座席 |
| `claimed_at` | ts? | 认领进私海时间(回收计时基准) |
| `last_contacted_at` | ts? | |
| `next_follow_at` | ts? | 下次跟进(待办提醒) |
| `institution_id` | UUID? | **预留机构维度**,P0 恒 null |
| `created_at/updated_at` | ts | |

索引:`region_code`、`status`、`owner_admin_id`、`next_follow_at`、`dnc`、`(institution_id)`、`phone`(查重)。

### 2.2 `sales_lead_activity`(跟进记录,一线索多条)

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | |
| `lead_id` | UUID FK | |
| `admin_id` | UUID | 座席 |
| `channel` | enum | `call/wechat/note/sms` |
| `direction` | enum? | `out/in` |
| `content` | text? | 跟进内容/备注 |
| `outcome` | enum? | `connected/no_answer/rejected/callback/...` |
| **通话/分析预留** | | |
| `recording_url` | str? | 录音(COS) |
| `call_duration_sec` | int? | |
| `asr_text` | text? | 转写 |
| `intent_score` | int? | 本次通话意向分 |
| `analysis` | JSONB? | **意向分析 schema 输出**(§4) |
| `created_at` | ts | |

索引:`lead_id`、`admin_id`、`created_at`。

### 2.3 `wecom_chat_archive`(企微会话存档 · P2 预留)

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | |
| `seq` | bigint | 存档游标(拉取用) |
| `msg_id` | str | 企微 msgid |
| `from_userid` | str | 员工 |
| `external_userid` | str? | 客户(关联 lead.wechat_id) |
| `roomid` | str? | 群 |
| `msgtype` | enum | `text/voice/image/file/...` |
| `content_text` | text? | **解密后**文本 |
| `media_url` | str? | 语音/图片/文件转存 COS |
| `msgtime` | ts | |
| `lead_id` | UUID? | 关联线索 |
| `analyzed` | bool | |
| `analysis` | JSONB? | 复用意向 schema |

索引:`seq`、`external_userid`、`lead_id`。

### 2.4 `system_configs` 配置项(禁写死)

- `sales_crm.public_pool_recycle_days`:私海 N 天未跟进→回收公海(默认 7)
- `sales_crm.dial_time_windows`:允许拨打时段(如 `[["09:00","12:00"],["14:00","20:00"]]`)
- `sales_crm.intent_weights`:意向分权重(会话信号 vs 行为信号,默认各 0.5,借 Gong)
- `sales_crm.asr_provider` / `sales_crm.wecom_archive_enabled` / `sales_crm.call_center_provider`:接入开关
- 常量仅兜底,实际值读 `pricing_service`/`config_service` 同源。

---

## 3. 赢单画像反查推荐(P0,纯查询,自研)

> 探迹「相似企业推荐」的真实机制 = **分析已成交客户画像,反向匹配线索库**(深研已证)。轻量版自己就能做,不用买 SaaS。

**派生逻辑(不新建表)**:
1. 取 `status=won` 的线索集合,统计其画像分布:`industry`、`region_code` 前缀(省/市)、`biz_tags`、`scale`。
2. 对 `pool=public & status=new` 的线索,按画像相似度加权打分 → 写 `similar_score`:
   - 行业命中 +权重、同省 +权重、同市 +权重、经营特征标签重合度 ×权重(权重读 `system_configs`)。
3. 排序输出「今日推荐优质线索」列表;座席可一键认领进私海。

**接口**:`GET /admin/sales/leads/recommend`(分页,按 `similar_score desc`)。
可用定时任务每日重算,或查询时实时算(线索量小于万级实时即可)。

---

## 4. 意向分析 schema(P1,云 ASR + 自建 LLM)

> Gong 成交意向分结构 = **50% 会话信号 + 50% 行为信号**(接通/时长/跟进/历史);会话信号含价格提及、竞品提及、red flags(深研已证)。循环智能同一套管道分析**语音+文本**。

**LLM 输出结构(存 `activity.analysis` / `wecom_chat_archive.analysis`)**:
```jsonc
{
  "intent_score": 0-100,            // 会话信号 ~50% + 行为信号 ~50%(权重读 system_configs)
  "intent_grade": "A|B|C|D",        // 意向分层(Megaview)
  "signals": {                      // 会话信号(Gong)
    "asked_price": true,            // 主动问价 = 强意向
    "asked_next_step": false,       // 问"怎么合作/下一步"
    "competitor_mentioned": ["xx机构"],
    "objections": ["价格高", "要开会讨论"],   // 异议
    "red_flags": ["明确拒绝", "已有供应商"]
  },
  "product_feedback": ["希望支持XX年级", "想要机构版"],  // 产品意见 → 后续聚类归档(VoC 思路)
  "talk_ratio": 0.35,               // 坐席说话时长占比
  "summary": "一句话通话摘要,自动回填跟进记录",
  "next_action": "3天后发试用链接",
  "compliance": { "violations": [] } // 电销违规质检:禁语/违规承诺(教育行业:保过/包提分)
}
```
**管道**:录音/语音 → 云 ASR(阿里/腾讯,支持实时流式 + 说话人分离,¥1.2–3/h)→ 分轨文本 → LLM(本项目 `chat_completion` + `fast_model()`,`response_format=json_object`)→ 写 `activity`,并把 `intent_score/grade/product_feedback` 冗余回 `sales_lead`。
**电话与企微共用同一分析函数**(文本入口),只是数据源不同。

---

## 5. 企微会话存档接入位(P2)

> 全部据企微开发者文档(91360/91361/91774)与开源 SDK 核验。

**开通前提**:管理后台开会话存档,配置**开启范围 + IP 地址 + 消息加密公钥(2048bit RSA)**;私钥自存。
**获取方式**:SDK 主动拉取 `GetChatData(seq, limit≤1000, ≤4000次/分钟)`,按 `seq` 分页;+ 事件回调。
**加解密(两层)**:每条含 `EncryptRandomKey` + `EncryptChatMsg` → 用企业 RSA 私钥解出随机对称密钥 → `DecryptData(EncryptRandomKey, EncryptChatMsg)` 得正文。
**SDK**:开源 `NICEXAI/WeWorkFinanceSDK`(Go),`NewClient(corpID, corpSecret, rsaPrivateKey)` → `GetChatData(...)`。可用独立拉取服务落 `wecom_chat_archive`,语音过 ASR 后进 §4 管道。

**合规红线(硬性)**:
1. **员工授权**:被存档员工登录客户端进企业时经「告知页面」(SDK 强制)。
2. **外部联系人同意**:员工与外部联系人的会话,**须经外部联系人同意**企业方可 API 获取 → 客户侧要有知会话术。
3. 私钥安全存储。

---

## 6. Admin 接口(遵守分页)

```
GET   /admin/sales/leads            # 分页 skip/limit/total + 筛选 region/status/source/pool/owner
POST  /admin/sales/leads            # 手动录入
POST  /admin/sales/leads/import     # Excel 导入(region 走 region_from_name)
PATCH /admin/sales/leads/{id}       # 改状态/DNC/consent/派单
POST  /admin/sales/leads/{id}/claim # 认领进私海
POST  /admin/sales/leads/{id}/release  # 退回公海
GET   /admin/sales/leads/{id}/activities   # 跟进时间线(分页)
POST  /admin/sales/leads/{id}/activities   # 加跟进
GET   /admin/sales/leads/recommend  # 赢单画像反查推荐(分页)
GET   /admin/sales/board            # 座席看板:拨打量/接通率/转化率

# 预留(P1/P2)
POST  /admin/sales/leads/{id}/call        # 点击外呼(校验 dnc + 拨打时段)
POST  /admin/sales/call-callback          # 呼叫中心 webhook(录音回传→触发分析)
POST  /admin/sales/wecom-callback         # 企微会话回调
```

**合规内建**:`dnc=true` → `call` 接口拒绝 + 列表标红;`call` 前校验 `system_configs` 拨打时段;录音开场告知由呼叫中心放音。

---

## 7. Admin 页面

- **线索列表页**:分页 + 筛选(地区级联走 region / 状态 / 来源 / 公海私海 / 负责人),标红 DNC。
- **Tabs**:我的私海 / 公海 / 今日推荐(赢单反查)。
- **线索详情抽屉**:资料 + 跟进时间线 + 意向分/分层 + 产品意见;录入跟进;`外呼`按钮(P0 禁用+提示"待接呼叫中心")。
- **导入弹窗**:Excel 上传 → 预览 → 入库(自动 region 匹配 + 查重)。
- **座席看板**:拨打量/接通率/转化漏斗。
- (P1/P2)通话录音播放 + 转写 + 分析结果;企微会话分析。

---

## 8. Build vs Buy(据深研修正)

| 模块 | 结论 | 依据 |
|---|---|---|
| 线索池 + 公海私海 + **赢单画像反查推荐** + 派单 + 跟进 | **自研** | 相似推荐原理已摸清(成交画像反查),轻量版可做 |
| 商家线索来源 | **买探迹类授权数据** + 人工导入 | 爬地图/美团/点评踩 ToS+PIPL;探迹靠聚合公开+授权 |
| 外呼线路/录音/软电话 | **接**云呼叫中心 | 号码资质 |
| ASR(转写+说话人分离) | **接**阿里云/腾讯云 | ¥1.2–3/h,实时+分轨现成 |
| 意向打分/异议·产品意见/摘要回填 | **自研**(云ASR+自建LLM,复刻 §4) | 成本低;Gong 50/50 + 循环智能质检维度已给蓝图 |
| 企微会话分析 | **自建接**会话存档 API + 开源 SDK | 官方通道,SDK 开源可控 |

---

## 9. 合规红线汇总(内建为字段/开关,非注释)

1. **数据来源**:禁爬百度地图/美团/大众点评;公开电话人工导入须存 `source_note`;规模化用授权数据源。
2. **电销**:`dnc` 黑名单禁呼、拨打时段/频次限制、来电身份告知。
3. **录音**:开场告知(呼叫中心放音)。
4. **企微**:员工告知页 + 外部联系人同意 + 私钥安全。

---

## 来源(深研核验,官方一手为主)

- 探迹官网/新闻(线索维度、相似推荐机制、数据来源)
- 企微开发者文档 91360 / 91361 / 91774(会话存档开通、授权、拉取、加解密)
- Gong 官方 deal-likelihood 文档(50/50 结构、会话信号)
- 循环智能官网+知识库(会话智能链路、质检维度、VoC 抽取)
- Megaview 官网(意向分层)
- WeWorkFinanceSDK(GitHub,SDK 接法)
- 阿里云 / 腾讯云 ASR(实时转写、说话人分离、价格)

> 注:探迹「四大客群 + 具体数量」网传数字未通过核验,已剔除。
