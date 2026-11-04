# Nekro Agent 拟人交互助手（humanoid_chat）

让 Nekro Agent 的聊天回复更像真人：分段与打字节奏、情绪/精力、群内身份档案、群规执法、作息疲劳、主动潜水、口语化瑕疵，以及与表情/好感度/记忆系统的协作。

> 插件文件：`humanoid_chat.py`
>
> 当前版本：`3.9.12`
>
> 适用：Nekro Agent `2.4.x+`
>
> 主要适配：OneBot V11 / NapCat（QQ）
>
> 仓库：<https://github.com/AdriftXCore/nekro-plugin-humanoid-chat>

---

## 功能概览

- **分段与打字节奏**
  - 自动按句子拆分，或用 `[SPLIT]` 手动分段
  - 段间随机延迟、逐字延迟、句末停顿、首段思考延迟
  - 段间最小间隔、夜间减速、低精力减速、偶发连发
  - 被新消息打断时停止剩余分段
- **社交直觉与表达习惯**
  - 17 字左右、7~10 字小短句，凭直觉接话，不霸道
  - 禁止 Emoji、颜文字、句尾 `~` / `呀` / `呢` / `哦` 和 AI 腔
  - 机器人昵称从 `extra_bot_names` 和人设名动态读取
  - 群聊消息明确 @别人或引用别人时，不参与普通闲聊随机插话；只有叫机器人名字、命中关键词或被直接 @/引用机器人时才触发
  - 优先文字表达；短句 + 强情绪/紧张/直白时主动考虑配 1 张表情包/图片，不适合时回退纯文字
- **不是工具人**
  - 提示词明确群友身份：不是客服、助手、搜索引擎、计算器、百科或作业代写
  - 对“背圆周率、查股票、写作业、快点查”等命令式 AI 请求，可反问、吐槽、装傻、拒绝或转移话题
  - 股票/基金/币/医疗/法律等风险话题不装专家、不预测；联网结果只顺口说结论，默认不列点、不贴 URL
- **戳一戳**
  - 被戳机器人时按概率三选一：AI 回复 / 戳回去 / 完全不回应
  - 默认 AI 5%、戳回 15%、不回应 80%，同一群同一人 60 秒冷却
  - 戳回去不调用 LLM；不回应也不消耗 token
- **引用 AT 上下文**
  - NoneBot 会把“回复目标 + 同一目标的 @”合并删除；humanoid 会从原始事件中补回非机器人 AT，避免模型把 @别人的问题当成问自己
  - 缓存 60 秒过期；过期后用 OneBot `get_msg` 兜底恢复 AT
- **拟真瑕疵**
  - 口癖、省略号、重复字、偶发错字后更正
  - 不影响链接、代码、`[@id:...@]` 提及和文件路径
- **情绪 / 精力 / 耐心**
  - 每个频道独立的心情、精力、耐心
  - 会根据聊天内容、连续轰炸、被忽略等变化
  - 夜间恢复精力，低精力时更短、更慢、更少主动说话
  - 每天按 `night_end` 起床时间进入新周期，精力和耐心随机重置到 `30~默认值`
  - 低精力/低耐心时，群聊直接 @ 或引用机器人有概率完全不回复；超级管理员豁免
- **本群档案**
  - 每个群一个 YAML：群描述、身份、群主/管理员、关键人物、群文化、语气、群规、管理策略
  - 自动识别机器人在群里的 `owner/admin/member` 角色
  - 可手动覆盖身份
  - 普通成员群只提醒不执法；群主/管理员群可按群规执法
  - 可选群黑话候选：`/group_learn` 自动应用高置信度安全候选，其余编号审查，可撤销
- **群规执法**
  - 支持提醒、撤回、禁言、撤回并禁言、撤回并踢出、只记录不执行
  - 可指定每条规则的动作和禁言时长
  - 依赖「群管助手」插件执行实际禁言/撤回/踢人
- **主动 / 潜水**
  - 根据群活跃度、精力、被忽略次数、每日上限决定是否主动冒泡
  - 夜间默认不主动打扰
- **表情 / 多模态协作**
  - 不接管表情库，调用「表情管理」插件的 `xemo_get_best_emotion_path`
  - 情绪明显时提示 AI 自行决定是否发 1 张表情
- **画图概率拒绝 / 主动画图**
  - 普通用户请求画图时按 `draw_refuse_probability` 概率拒绝，超级管理员默认豁免
  - 拒绝时不调用「绘图」/「多图绘制」，用符合人设的短句拒绝或转移话题
  - 主动画图使用独立概率、冷却和每日上限，不套用用户请求的拒绝概率
  - 提示词层约束，不会修改内置 draw 插件
- **联网搜索 / 网页抓取**
  - 提供 `human_search(query, max_results)` 和 `human_fetch(url, max_chars)`
  - 底层使用 DeepSeek Search/Fetch API，Bearer Key 在插件配置中填写
  - 搜索返回标题、摘要、来源和 URL；抓取返回网页 Markdown 正文
  - B 站视频链接会直接读取公开 API，自动附带标题、UP 主、播放数据和热门评论
  - 用户引用卡片/消息时，会把被引用消息的链接注入提示词，优先使用引用链接
  - 明确引用 100% 允许抓取；模糊指代按 `link_fetch_probability` 概率提示
  - 引用图片时提取图片路径并交给多模态上下文；图片不在最近视觉窗口时直接回复“没看到”
  - 引用无链接卡片时直接根据卡片标题回复，不触发 AI
  - `human_fetch` 可独立开关；Key 未配置、限流、余额不足或网络失败时明确报错
- **Bangumi 动漫资料**
  - 提供 `human_bangumi_search`、`human_bangumi_subject`、`human_bangumi_characters`、`human_bangumi_calendar`
  - 查询动画条目、评分、简介、角色/声优和每日放送
  - 遇到具体动漫事实且 AI 不确定时主动查 Bangumi；普通闲聊/玩梗不查
  - Token 可选，默认匿名查询公开条目；Token 只放插件配置，不写入仓库
- **红包识别与推脱**
  - 识别群里的红包卡片，记录标题和是否点名机器人
  - 不主动提红包；有人让机器人收/领/抢红包时，用“QQ没实名”自然推脱
  - 不领取、不假装收到、不报金额
- **QQ空间说说**
  - 提供 `human_qzone_publish(content, images, ugc_right)`
  - 通过 NapCat `send_qzone_msg` 发布，支持文字和最多 9 张图片
  - 默认所有人可见；可主动发，但有冷却和每日上限
  - 支持每天 `09:00~23:00` 随机自动发一条：读取 Nekro 默认人设生成，当天已通过插件发过则跳过
  - 不发聊天记录、他人隐私、联系方式、住址、定位
- **长期记忆协作**
  - 不重复维护好感度分数；长期好感度由「好感度系统」负责
  - 支持 Nekro 自带记忆系统的被动注入
  - 支持「主动记忆工具」插件的主动检索

---

## 精力、耐心、熟悉度机制

三者都是 `plugin.store` 中的 JSON 状态，不是数据库表。

### 范围与上限

| 状态 | 作用范围 | 初始值 | 上限 |
| --- | --- | ---: | ---: |
| 精力 `energy` | 每个群/频道独立 | `80` | `100` |
| 耐心 `patience` | 每个群/频道独立 | `70` | `100` |
| 熟悉度 `familiarity` | 每群 + 每用户独立 | `0` | `familiarity_max`，默认 `100` |

精力和耐心最低都是 `0`。

### 每日随机重置

- 重置周期以 `night_end` 为起床时间，默认 `07:30`，线上当前为 `10:00`
- 每天第一次读取状态时检查，不在 00:00 定时重置
- 精力和耐心分别随机重置到：
  - 精力：`daily_state_reset_min ~ energy_start`，默认 `30~80`
  - 耐心：`daily_state_reset_min ~ patience_start`，默认 `30~70`
- 同一周期只重置一次
- 重置后立即写回 `plugin.store`
- 旧状态第一次升级只记录当前周期，不立即重置
- 熟悉度不会每日重置

### 精力

- 每发送一个分段消息，精力减少 `energy_cost_per_message`，默认 `1.5`
- 夜间每段消耗再乘以 `night_energy_cost_multiplier`，默认 `2.0`
  - 白天每段约 `1.5`
  - 夜间每段约 `3.0`
- 按真实时间恢复：
  - 白天 `+energy_recover_day_per_hour`，默认 `6/小时`
  - 夜间 `+energy_recover_night_per_hour`，默认 `18/小时`
- 低于 `low_energy_threshold`（默认 30）时：
  - 群聊接话概率 × `low_energy_reply_multiplier`，默认 `0.4`
  - 打字/分段延迟 × `low_energy_delay_multiplier`，默认 `1.8`
  - 主动冒泡概率降低
  - 提示词会要求少说两句

### 耐心

- 初始 `70`，每小时恢复 `patience_recover_per_hour`，默认 `8`
- 同一用户在 `rapid_message_window`（默认 8 秒）内连续发消息，视为连续轰炸
- 连续第 3 条及以后，每条额外减少 `rapid_patience_cost`，默认 `6`
- 耐心接话倍率：
  ```text
  clamp(0.35 + patience / 100 * 0.75, 0.35, 1.1)
  ```
- 耐心低于 30 时主动冒泡概率再 × `0.4`
- 提示词在耐心低于 35 时要求回复更短，必要时直接说不想聊

### 熟悉度

- 每次收到某个用户的消息，互动次数 +1
- 正常每条增长 `familiarity_gain`，默认 `1.2`
- 连续轰炸会降低增长：
  ```text
  实际增长 = familiarity_gain / (1 + (rapid_streak - 1) * 0.6)
  ```
- 上限 `familiarity_max`，默认 `100`
- 当前没有时间衰减
- 熟悉度不直接改变接话概率，只影响提示词里的关系感、语气和记忆唤起
- 熟悉度表示“认识多久/聊过多少”，不等同于「好感度系统」的长期喜欢/讨厌评分

### 低状态概率不回 AT

当同时满足：

- 当前是 OneBot 群聊
- 消息是直接 @ 或引用机器人
- 发送者不是 `SUPER_USERS`

则按精力和耐心加权计算拒回概率：

```text
E = clamp((low_energy_threshold - energy) / low_energy_threshold, 0, 1)
P = clamp((low_patience_threshold - patience) / low_patience_threshold, 0, 1)

状态权重 = (0.6 * E + 0.4 * P) / (0.6 + 0.4)
拒回概率 = low_resource_ignore_probability * 状态权重
```

其中：

- 精力、耐心都正常：`0%`
- 只有精力低、耐心高：高耐心会明显拉低拒回概率
- 只有耐心低、精力高：同理
- 两者都不高于 `low_resource_critical_threshold`（默认 `10`）：拒回概率拉满到 `low_resource_ignore_probability`
- `low_resource_ignore_probability` 默认 `1.0`，即双临界时可达到 `100%`

权重可通过 `low_resource_energy_weight`、`low_resource_patience_weight` 调整。

命中时：`BLOCK_TRIGGER`，不调用 AI、不发送文字、不执行工具。

未命中时正常回复；私聊不受影响；超级管理员始终必须回复。

---

## 仓库结构

```text
.
├── humanoid_chat.py                 # 插件本体（单文件）
├── config.yaml                      # 示例配置（不含密钥）
├── docs/CONFIG.md                   # 全量配置项参考
├── examples/
│   ├── group_profile.owner.example.yaml
│   └── group_profile.member.example.yaml
├── scripts/
│   ├── check.sh                     # 语法/YAML 自检
│   ├── deploy.sh                    # 可选部署脚本，需按环境修改
│   └── publish.sh                   # git commit + push
├── CHANGELOG.md
└── README.md
```

> 真实的 `group_profiles/` 含群成员 QQ、昵称、群规，不要提交到公开仓库；只提交脱敏示例。

---

## 依赖与兼容性

### 必需

| 依赖 | 说明 |
| --- | --- |
| Nekro Agent `2.4.x+` | 插件基于 `NekroPlugin`、`mount_command`、`mount_on_user_message`、`mount_prompt_inject_method`、`plugin.store` 等 API |
| OneBot V11 / NapCat | QQ 群聊；群角色识别、禁言、撤回、踢人都依赖 OneBot API |
| `KroMiose.basic` | 提供 `send_msg_text` / `send_msg_file` 等基础发送工具，通常默认启用 |

### 功能依赖（可选）

| 插件 / 能力 | 插件 key | 用途 | 缺失时 |
| --- | --- | --- | --- |
| 群管助手 | `XiaoJiu.group_admin` | AI 实际执行禁言、撤回、踢人；`/force_mute` 不依赖它 | 仍可注入群规和提醒，但 AI 不能实际执法 |
| 表情管理 | `xggm.emotions` | 提供 `xemo_get_best_emotion_path`，本插件只控制发送时机 | 不能自动选表情；建议关闭 `enable_sticker_coordination` / `sticker_emotion_hint` |
| 好感度系统 | `liugu.nekro_favorability` | 维护长期好感度分数、事件、标签 | 本插件仍可运行，但长期好感度不存在 |
| 主动记忆工具 | `KroMiose.memory_tools` | 让 AI 主动搜索工作区记忆 | 只能使用被动记忆注入 |
| 群荣誉 | `KroMiose.group_honor` | 修改群头衔等 | 头衔相关行为不可用 |
| Nekro 记忆系统 | 核心能力 | 被动记忆注入、沉淀、Episode、Qdrant | 需要 `MEMORY_ENABLE_SYSTEM=true` 且频道绑定 workspace |

### Python / 运行时依赖

插件本身不额外安装 pip 包，使用 Nekro Agent 运行环境已有依赖：

- `pydantic`（v2）
- `PyYAML`（群档案）
- `nonebot2`
- `nekro_agent` 内部模块

插件主体不主动调用 LLM；群黑话提取、记忆沉淀、增强检索、绘图等场景才会消耗模型额度。

---

## 安装

### 1. 获取插件

```bash
git clone https://github.com/AdriftXCore/nekro-plugin-humanoid-chat.git
```

也可以直接下载 `humanoid_chat.py`。

### 2. 放入插件目录

把 `humanoid_chat.py` 放到 Nekro Agent 的插件工作目录。不同部署方式的路径不同，通常类似：

```text
<Nekro 数据目录>/plugins/workdir/humanoid_chat.py
```

然后在 Nekro Agent WebUI 中启用「拟人交互助手」。

### 3. 配置

首次加载会自动生成默认配置。也可以手动放置示例配置：

```text
<Nekro 数据目录>/plugin_data/afx.humanoid_chat/config.yaml
```

不要把真实 API Key、Token 提交到公开仓库。

### 4. 群档案（可选）

```text
<Nekro 数据目录>/plugin_data/afx.humanoid_chat/group_profiles/
  onebot_v11-group_<群号>.yaml
```

不配置群档案也可以正常聊天，只是没有群身份、群规和关键人物信息。

### 5. 重载插件

优先在 Nekro Agent WebUI/API 中热重载 `humanoid_chat`。
如果修改了 Nekro 核心配置或群管插件包，重启你的 `nekro_agent` 容器：

```bash
docker restart <你的 nekro_agent 容器名>
```

---

## 快速开始

1. 启用「拟人交互助手」
2. 调整基础配置：
   - `extra_bot_names`：群友怎么叫你的机器人
   - `trigger_keywords`：哪些话题会提高接话概率
   - `min_segment_gap`：分段最小间隔（默认 2 秒）
   - `strip_punctuation`：回复是否去标点
3. 如需群身份/群规：配置 `group_profiles/<chat_key>.yaml`
4. 如需实际禁言/撤回/踢人：安装并配置 `XiaoJiu.group_admin`
5. 如需长期记忆：给频道绑定 workspace

---

## 命令

### 查看全部命令

Nekro Agent 自带：

```text
/na_help
```

会按分类列出所有已注册命令。命令较多时会自动使用合并转发。

### `/force_mute`

```text
/force_mute <QQ>             # 默认 600 秒
/force_mute <QQ> 300         # 禁言 300 秒
/force_mute <QQ> 0           # 解除禁言
/force_mute 123,456 600      # 多个 QQ
```

- 权限：仅超级管理员
- 仅 OneBot 群聊
- 不能禁言自己、群主
- 默认不能禁言管理员；只有机器人自己是群主且 `force_mute_allow_admins=true` 才允许
- 不依赖「群管助手」，直接调用 OneBot `set_group_ban`
- 因此不受群管插件的 `ALLOW_GROUPS` / `PROTECTED_USERS` / `ENABLE_MUTE` 限制

### `/group_learn`

```text
/group_learn                     # 当前群
/group_learn <群号>              # 指定群号
/group_learn --all               # 所有 OneBot 群
```

- 权限：仅超级管理员
- 只读取最近 `group_learn_lookback_days` 天、非图片占位符、非命令、非机器人消息
- 发送者匿名化为“群友1/群友2”，不把昵称、QQ、图片文件名交给模型
- LLM 只输出黑话/缩写/梗/固定称呼/明确偏好候选
- 置信度达到自动阈值的**新词**最多自动应用 `group_learn_auto_apply_limit` 条
- 其余候选写入 `group_profiles/<chat_key>.learned_terms.candidates.yaml`，按编号审查
- 自动应用可用 `/group_learn_undo` 整批撤销
- 批准：`/group_learn_approve 1`、`/group_learn_approve 1 3`、`/group_learn_approve 词` 或 `/group_learn_approve all`
- 拒绝：`/group_learn_reject 1` 或 `/group_learn_reject all`
- 查看已批准：`/group_learn_list`
- 精确撤销已批准：`/group_learn_revoke 2`、`/group_learn_revoke 1 3`、`/group_learn_revoke 词` 或 `/group_learn_revoke all`

### `/group_profile_gen`

```text
/group_profile_gen                     # 当前群
/group_profile_gen <群号>              # 指定群号
/group_profile_gen --all               # 所有 OneBot 群
```

- 权限：仅超级管理员
- 只统计和机器人 **直接互动**的人：
  - `is_tome=1`
  - 引用机器人的消息
  - 消息里出现机器人名字/别名
- 排除机器人自己、SYSTEM、群主、管理员
- 只取互动次数前 N 人（`group_profile_member_limit`，默认 8）
- 自动生成角色、群主、管理员、关键人物、culture、tone、activity、admin_policy
- **不覆盖**：群 `description`、人物 `description`、`rules`、`learned_terms`
- 生成前自动备份：`<chat_key>.yaml.bak.<时间>`
- 不调用 LLM

---

## 本群档案 YAML

### 文件位置

```text
<Nekro 数据目录>/plugin_data/afx.humanoid_chat/group_profiles/<chat_key>.yaml
```

`chat_key` 通常形如：

```text
onebot_v11-group_<群号>
```

### 完整结构

```yaml
description: "这个群是干什么的、氛围如何"
enabled: true
role: auto                                  # auto | owner | admin | member

owner:
  name: 群主昵称
  qq: "100000001"
  aliases: [群主别名]
  note: 本群群主
  description: "你写的人物描述"

admins:
  - name: 管理员昵称
    qq: "100000002"
    aliases: [别名]
    note: 本群管理员
    description: ""

members:
  - name: 关键群友
    qq: "100000003"
    aliases: [别名]
    note: 与机器人直接互动 N 次；群内发言 M 条
    description: "你写的人物描述"

culture: "群文化/常聊话题"
tone: "机器人在这个群的语气"
activity: "主动程度/是否执法"

learned_terms:
  - term: "群内黑话"
    meaning: "一句话解释"
    evidence: "批准时保留的上下文证据"
    confidence: 0.8
    updated_at: "2026-11-03"
    expires_at: "2026-12-18"

rules:
  - text: 不得私发广告、扩列、建群
    action: recall_and_kick
  - text: 连续刷屏
    action: mute
    duration: 300
  - text: 普通提醒类规则
    action: remind

admin_policy:
  enabled: true
  direct_actions: [mute, recall, kick]
  observe_actions: []
  protected: [owner, admins, self]
  protected_extra: []
  max_mute_seconds: 600
  cooldown_seconds: 60
```

### 字段说明

- `description`：群描述，生成器永远保留
- `enabled`：是否启用本群档案
- `role`：
  - `auto`：运行时用 OneBot 查询机器人实际角色
  - `owner/admin/member`：语气/身份的手动覆盖
  - **实际权限始终以平台实际角色为准**
- `owner/admins/members`：
  - `name`：显示名
  - `qq`：平台 QQ，用于 @ 和执法
  - `aliases`：别名，最多 3 个
  - `note`：自动统计信息，可被生成器覆盖
  - `description`：你写的人物描述，生成器保留
- `culture/tone/activity`：自动生成，可被生成器覆盖
- `learned_terms`：只通过群黑话命令写入；`expires_at` 过期后不再注入
- `rules[].action`：
  - `remind`：只提醒
  - `recall`：撤回
  - `mute`：禁言，配合 `duration`
  - `recall_and_mute`：撤回并禁言
  - `recall_and_kick`：撤回并踢出
  - `observe_kick`：只记录/报告，不实际踢
- `admin_policy`：
  - `enabled`：是否允许实际管理
  - `direct_actions`：允许直接执行的动作
  - `observe_actions`：只观察/报告的动作
  - `protected`：不操作的身份
  - `protected_extra`：额外保护 QQ
  - `max_mute_seconds`：提示词里的禁言上限
  - `cooldown_seconds`：提示词里的冷却；目前不是硬限制

> 重要：`admin_policy` 是提示词/SOP；真正的硬权限由「群管助手」的 `ALLOW_GROUPS`、`ENABLE_MUTE`、`ENABLE_DELETE_MSG`、`ENABLE_KICK`、`PROTECTED_USERS`、`MAX_MUTE_DURATION` 控制。

### 示例

- [owner 群示例](examples/group_profile.owner.example.yaml)
- [普通成员群示例](examples/group_profile.member.example.yaml)

---

## 群管助手配置

AI 实际禁言/撤回/踢人由 `XiaoJiu.group_admin` 执行。推荐：

```yaml
ALLOW_GROUPS:
  - '<群号>'
PERMISSION_MODE: ai_autonomous
ENABLE_MUTE: true
ENABLE_DELETE_MSG: true
ENABLE_KICK: true
ENABLE_KICK_AND_BAN: false
ENABLE_ADMIN_REPORT: true
MAX_MUTE_DURATION: 600
PROTECTED_USERS:
  - '<机器人QQ>'
  - '<群主QQ>'
  - '<管理员QQ>'
```

- `ALLOW_GROUPS` 为空时允许所有群；生产环境建议显式列出
- `PERMISSION_MODE: ai_autonomous` 时，AI 可自行判断；`check_requester` 则要求请求者有权限
- `PROTECTED_USERS` 在 `ai_autonomous` 下不会自动保护管理员，**必须显式加入**
- 规则写了 `recall_and_kick`，还需要 `ENABLE_KICK: true` 才会真的踢
- 规则写了 `recall_and_mute`，需要 `ENABLE_DELETE_MSG` 和 `ENABLE_MUTE`
- `MAX_MUTE_DURATION` 是硬上限；YAML 里的 `duration` 不应超过它

---

## 与记忆系统协作

Nekro 自带长期记忆按 **workspace** 隔离。启用方式：

1. 在 WebUI 创建工作区
2. 把群绑定到工作区（`chat_channel.workspace_id`）
3. 保持 `MEMORY_ENABLE_SYSTEM=true`
4. 如需回补历史，在 workspace 的「记忆图谱」里执行「清空并重新沉淀」

注意：

- workspace 的 `status=stopped` 只代表 CC 沙盒未启动，**不影响 NA 记忆**
- 记忆检索按 `workspace_id` 过滤，不是按群过滤；同一 workspace 的多个群会共享记忆
- 想分群隔离，每群一个 workspace
- `/group_profile_gen` 和群档案不依赖 workspace；只有长期记忆依赖
- 被动记忆注入上限由 `MEMORY_CONTEXT_MAX_LENGTH` 控制（建议 800–1200）
- 主动检索需要启用 `KroMiose.memory_tools`

---

## 与表情、好感度协作

### 表情管理

本插件不维护表情库、不记录表情 ID。提示词只告诉 AI：

```text
调用 xemo_get_best_emotion_path("完整场景")
再用 send_msg_file(_ck, 路径) 发送
```

如果未安装 `xggm.emotions`，请关闭：

- `enable_sticker_coordination`
- `sticker_emotion_hint`

### 好感度系统

本插件**不维护第二个好感度分数**：

- `liugu.nekro_favorability` 维护长期好感度、事件、标签
- 本插件只维护即时 `valence/energy/patience` 和每用户 `familiarity`（熟悉度）
- 熟悉度表示“认识多久/多熟”，不是喜欢/讨厌评分
- 提示词明确“长期好感度以好感度系统为准”

---

## 配置说明

- 示例配置：[config.yaml](config.yaml)
- 全量字段说明：[docs/CONFIG.md](docs/CONFIG.md)

常用配置：

| 配置 | 说明 |
| --- | --- |
| `extra_bot_names` | 额外昵称，逗号分隔 |
| `trigger_keywords` | 感兴趣的话题词 |
| `poke_reply_ai_probability` | 被戳后 AI 回复概率，默认 0.05 |
| `poke_reply_poke_probability` | 被戳后戳回去概率，默认 0.15 |
| `poke_reply_cooldown_seconds` | 戳一戳响应冷却，默认 60 秒 |
| `min_segment_gap` | 分段最小间隔，默认 2 秒 |
| `segment_delay_min/max` | 每段基础随机延迟 |
| `max_segments` | 最多分几段 |
| `strip_punctuation` | 是否去掉回复标点 |
| `group_profile_enabled` | 是否启用每群 YAML |
| `group_profile_max_chars` | 群档案注入上限，默认 2400 |
| `group_learn_enabled` | 是否启用群黑话候选/注入 |
| `group_learn_auto_apply` | 是否自动应用高置信度安全候选 |
| `group_learn_auto_apply_min_confidence` | 自动应用最低置信度，默认 0.85 |
| `group_learn_auto_apply_limit` | 单次自动应用上限，默认 3 |
| `group_learn_auto_ttl_days` | 自动应用词条有效期，默认 14 天 |
| `group_learn_inject_limit` | 每轮最多注入词条数，默认 6 |
| `force_mute_default_seconds` | `/force_mute` 默认时长 |
| `proactive_enabled` | 是否启用后台主动冒泡 |
| `active_chat_probability` | 每轮主动冒泡概率，建议 0.02–0.08 |
| `enable_sticker_coordination` | 是否与表情管理协作 |
| `sticker_emotion_hint` | 情绪明显时是否提示发表情 |
| `draw_refuse_enabled` | 是否启用画图概率拒绝 |
| `draw_refuse_probability` | 普通用户请求画图的拒绝概率，默认 0.8 |
| `human_search_enabled` | 是否启用 `human_search` |
| `human_fetch_enabled` | 是否启用 `human_fetch` |
| `human_search_api_key` | DeepSeek Search/Fetch Bearer Key，留空则不可用 |
| `bangumi_access_token` | Bangumi Access Token，留空匿名查询 |
| `red_packet_enabled` | 是否识别红包卡片 |
| `qzone_enabled` | 是否启用 QQ 空间发说说 |
| `qzone_daily_enabled` | 是否每天随机自动发一条说说 |
| `debug_log` | 详细日志；排查时临时开启 |

> `config.yaml` 是示例配置，可能需要按你的机器人、时区和群环境调整；不要把真实密钥提交到公开仓库。

---

## 常见问题与排查

### 为什么只踢不撤回？

- 旧提示词只约束“踢”，AI 可能不调用 `群管_撤回消息`
- 撤回工具需要触发消息的 `message_id`
- 本插件会提示“先撤回，再踢”，并把当前触发消息的 `message_id` 注入提示词
- 检查日志：`rpc_exec: admin_delete_message` 与 `admin_kick_user`

### 为什么消息后面带 `True`？

AI 调用了返回 bool 的工具（例如 `group_honor` 的 `set_user_special_title`），并把返回值拼进消息。本插件会：

- 提示词禁止把工具返回值拼进聊天内容
- 发送前清理中文后面拖尾的 `True` / `False` / `None`

### 为什么漏出 `SPLIT` / `TSPLIT`？

AI 可能把 `[SPLIT]` 写成 `[TSPLIT]`。本插件会：

- 识别 `[SPLIT]`、`[TSPLIT]`、大小写和空格变体
- 发送前清理残留 `SPLIT` / `TSPLIT`
- 提示词要求精确写 `[SPLIT]`

### 为什么机器人不执法？

按顺序检查：

1. 机器人在该群实际是 owner/admin 吗？
2. `XiaoJiu.group_admin` 是否启用？
3. `ALLOW_GROUPS` 是否包含该群？
4. `ENABLE_MUTE` / `ENABLE_DELETE_MSG` / `ENABLE_KICK` 是否开启？
5. 目标是否在 `PROTECTED_USERS`？
6. 消息是否触发了 Agent（@、叫名字、话题词）？
7. 群档案是否加载（日志 `本群档案加载`）？
8. 规则 `action` 是否写对？

### 为什么群档案没生效？

- 文件名必须是 `<chat_key>.yaml`
- YAML 必须能解析
- 修改后按 mtime 热加载，下一条消息生效
- 角色识别有 10 分钟缓存
- 查看日志 `本群档案加载`、`本群角色识别`

### 为什么记忆没生效？

- 频道是否绑定 workspace
- `MEMORY_ENABLE_SYSTEM` 是否为 true
- 是否有 embedding 额度（日志 401/余额不足）
- 重建是否完成
- 查询是否太泛；尝试具体关键词

### LLM 卡住怎么办？

- 先发 `/stop` 终止当前回复流程，不需要重启
- 检查模型 provider 是否超时/余额不足
- 必要时降低 `AI_GENERATE_TIMEOUT`、`AI_CHAT_LLM_API_MAX_RETRIES`
- 配置真正的 fallback 模型组

---

## 开发与维护

### 自检

```bash
./scripts/check.sh
```

等价于：

```bash
python3 -m py_compile humanoid_chat.py
python3 - <<'PY'
import glob, yaml
for path in glob.glob('examples/*.yaml'):
    with open(path, encoding='utf-8') as f:
        yaml.safe_load(f)
    print('ok', path)
PY
```

### 发布

```bash
./scripts/publish.sh "feat: describe your change"
```

`scripts/deploy.sh` 和 `scripts/publish.sh` 是可选开发脚本，里面的容器路径、SSH 别名和远程仓库需要按你的环境修改。

### 修改约定

- 改配置字段时同步更新：
  - `config.yaml`
  - `docs/CONFIG.md`
  - README 的配置说明
- 改行为时同步更新版本号（`NekroPlugin(version=...)`）和 `CHANGELOG.md`
- **不要提交真实群档案**（含 QQ、昵称、群规）；只提交 `examples/` 脱敏模板
- 修改群管插件包后，重启你的 `nekro_agent` 容器才能加载
- 提交前先跑 `scripts/check.sh`

---

## 更新记录

见 [CHANGELOG.md](CHANGELOG.md)。

---

## 参考

- [Nekro Agent](https://github.com/KroMiose/nekro-agent)
- [本项目 GitHub 仓库](https://github.com/AdriftXCore/nekro-plugin-humanoid-chat)
