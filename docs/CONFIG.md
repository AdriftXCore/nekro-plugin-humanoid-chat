# 配置参考

> 下表是 `HumanoidConfig` 的代码默认值。实际生产值以 `config.yaml` 和 NAS 上的 `plugin_data/afx.humanoid_chat/config.yaml` 为准。
> 配置项按标题中的【分类】分组。

### 唤醒

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `extra_bot_names` | 空 | 【唤醒】补充机器人昵称：除人设中的名字外，额外会被当成在叫你的称呼。逗号分隔，不区分大小写。 |
| `trigger_keywords` | 空 | 【唤醒】感兴趣的话题词：群聊中提到这些词会提高接话概率。逗号分隔；留空则只响应名字与概率。 |
| `keyword_reply_probability` | `0.8` | 【唤醒】命中名字/话题后的唤醒概率：命中后唤醒 AI 自主判断是否接话的概率。 |
| `reply_probability` | `0.0` | 【唤醒】纯闲聊插话概率：没有命中名字/话题时的搭话概率。建议 0 或 0.02，避免打扰。 |
| `reply_cd_seconds` | `30` | 【唤醒】群聊插话冷却（秒）：非直接呼叫的主动接话后，群内冷却时间。直接叫名字/@/私聊不受此限制。 |
| `always_reply_when_mentioned` | `True` | 【唤醒】@ 与私聊必回：被 @ 或私聊时无视概率与冷却，必定唤醒 AI。 |
| `ai_self_decision` | `True` | 【唤醒】AI 自主决定是否插话：被话题/名字唤醒后，由 AI 结合上下文判断；觉得突兀可以保持沉默。 |

### 节奏

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `auto_split` | `True` | 【节奏】自动分段：AI 没有手动使用 [SPLIT] 时，按句子/逗号自动拆成多段发送。 |
| `auto_split_min_chars` | `18` | 【节奏】自动分段最小长度：短于该长度的消息不自动拆段，避免把一句话拆得稀碎。 |
| `min_segments` | `1` | 【节奏】最少段数：自动分段时尽量不少于该段数；AI 手动 SPLIT 时以其为准。 |
| `max_segments` | `4` | 【节奏】最多段数：一次回复最多拆成多少段，超出部分会合并到最后一段。 |
| `segment_delay_min` | `0.35` | 【节奏】段间基础延迟下限（秒）：每段发送前的基础等待时间下限。 |
| `segment_delay_max` | `1.1` | 【节奏】段间基础延迟上限（秒）：每段发送前的基础等待时间上限。 |
| `char_delay_min` | `0.012` | 【节奏】逐字延迟下限（秒/字）：模拟打字速度：每个字额外等待的下限。 |
| `char_delay_max` | `0.045` | 【节奏】逐字延迟上限（秒/字）：模拟打字速度：每个字额外等待的上限。 |
| `punctuation_pause` | `0.35` | 【节奏】句末停顿（秒）：段落以问号/句号/感叹号等结尾时额外停顿。 |
| `thinking_delay_min` | `0.4` | 【节奏】首段思考延迟下限（秒）：看到消息后到第一段发出前的思考/阅读时间下限。 |
| `thinking_delay_max` | `1.6` | 【节奏】首段思考延迟上限（秒）：看到消息后到第一段发出前的思考/阅读时间上限。 |
| `max_segment_delay` | `6.0` | 【节奏】单次等待上限（秒）：任何一段的等待时间都不会超过该值，避免回复卡太久。 |
| `min_segment_gap` | `2.0` | 【节奏】段间最小间隔（秒）：每段之间至少等待这么久；连发概率只会缩短计算延迟，但不会低于该间隔。 |
| `burst_probability` | `0.18` | 【节奏】连发概率：偶尔像真人一样快速补发下一段（跳过大部分基础延迟）。 |
| `interrupt_on_new_message` | `True` | 【节奏】被新消息打断时停止后续分段：正在分段发送时对方又发来消息，停止剩余分段，像真人一样先看新消息。 |

### 瑕疵

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `enable_imperfections` | `True` | 【瑕疵】启用口语化瑕疵：口癖、省略号、重复字、偶发错字后更正。只作用于纯聊天文本，不碰链接/代码/提及。 |
| `filler_rate` | `0.08` | 【瑕疵】口癖概率：在句首加入「嗯/诶/那个」等口癖的概率。 |
| `filler_words` | `嗯,诶,那个,让我想想,哈哈,欸` | 【瑕疵】口癖词表：逗号分隔，随机挑选。 |
| `trailing_ellipsis_rate` | `0.12` | 【瑕疵】句尾省略号/波浪号概率：句尾没有标点时，偶尔补一个「…」或「~」。 |
| `duplicate_char_rate` | `0.03` | 【瑕疵】重复字概率：偶尔把「好」发成「好好」这类轻微口吃。 |
| `correction_rate` | `0.02` | 【瑕疵】错字后更正概率：偶发先发一个错字版本，再补一句更正。概率建议很低。 |
| `correction_prefix` | `啊打错了，` | 【瑕疵】更正前缀：更正消息前加的口头语。 |

### 情绪

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `mood_baseline` | `60` | 【情绪】心情基线：情绪会缓慢回落到该值。 |
| `mood_decay_hours` | `6.0` | 【情绪】心情回落时长（小时）：情绪偏离基线后，大约多久回落一半。 |
| `patience_start` | `70` | 【情绪】初始耐心：被连续轰炸或被无视会降低耐心。 |
| `patience_recover_per_hour` | `8.0` | 【情绪】耐心每小时恢复：耐心随时间恢复的速度。 |
| `rapid_message_window` | `8.0` | 【情绪】连续消息判定窗口（秒）：同一用户在该时间内继续发消息，视为连续轰炸。 |
| `rapid_patience_cost` | `6.0` | 【情绪】连续消息耐心消耗：连续轰炸时每次额外消耗的耐心。 |

### 精力

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `energy_enabled` | `True` | 【精力】启用精力系统：精力影响回复速度、分段数量和主动冒泡。 |
| `energy_start` | `80` | 【精力】初始精力：新频道首次出现时的精力值。 |
| `energy_cost_per_message` | `1.5` | 【精力】每条消息消耗：每发一条分段消息消耗的精力。 |
| `energy_recover_day_per_hour` | `6.0` | 【精力】白天每小时恢复：非睡眠时段的精力恢复速度。 |
| `energy_recover_night_per_hour` | `18.0` | 【精力】夜间每小时恢复：睡眠时段的精力恢复速度。 |
| `low_energy_threshold` | `30` | 【精力】低精力阈值：低于该值后回复更慢、更短、更少主动说话。 |
| `low_energy_reply_multiplier` | `0.4` | 【精力】低精力接话倍率：低精力时，群聊接话概率乘以该值。 |
| `low_energy_delay_multiplier` | `1.8` | 【精力】低精力延迟倍率：低精力时，打字延迟乘以该值。 |

### 关系

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `familiarity_enabled` | `True` | 【关系】启用熟悉度：按用户累计熟悉度；与「好感度系统」插件的长期评分互不替代。 |
| `familiarity_gain` | `1.2` | 【关系】每条消息熟悉度增量：正常互动时的熟悉度增长；连续轰炸会打折。 |
| `familiarity_max` | `100` | 【关系】熟悉度上限：熟悉度封顶值。 |
| `memory_limit` | `8` | 【关系】每用户小事记忆条数：AI 通过 humanoid_remember 记录的小事最多保留多少条。 |
| `enable_memory` | `True` | 【关系】启用小事记忆工具：允许 AI 调用 humanoid_remember 记录值得记住的互动。 |

### 本群档案

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `group_profile_enabled` | `True` | 【本群档案】启用每群 YAML 档案：从插件数据目录的 group_profiles/<chat_key>.yaml 读取身份、人物、群规和管理策略。 |
| `group_profile_dir` | 空 | 【本群档案】档案目录：留空使用插件数据目录下的 group_profiles；也可填绝对路径。 |
| `group_role_cache_minutes` | `10` | 【本群档案】群角色缓存（分钟）：自动识别 KONA 在群里的 owner/admin/member 角色，缓存多久。 |
| `group_profile_max_chars` | `2400` | 【本群档案】注入长度上限：本群档案注入提示词的最大字符数，超出会截断；群规较多时建议 2000 以上。 |
| `group_profile_member_limit` | `8` | 【本群档案】自动生成关键人物数：生成器只把和 KONA 直接互动过的前 N 人写进 members。 |
| `group_profile_preserve_limit` | `12` | 【本群档案】保留人物上限：重新生成时，已有描述但本次未进前 N 的人会追加保留，members 总数不超过该值。 |
| `group_profile_generator_lookback_days` | `30` | 【本群档案】生成器回看天数：生成器统计互动时回看最近多少天的聊天记录。 |

### 强制禁言

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `force_mute_default_seconds` | `600` | 【强制禁言】默认时长（秒）：force_mute 命令不写时长时使用的默认禁言秒数。 |
| `force_mute_max_seconds` | `86400` | 【强制禁言】最大时长（秒）：force_mute 命令允许的最长禁言秒数，超出会被截断。 |
| `force_mute_allow_admins` | `False` | 【强制禁言】允许禁言管理员：仅当 KONA 自己是群主时生效；默认不允许对管理员执行强制禁言。 |

### 作息

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `timezone` | `Asia/Shanghai` | 【作息】时区：用于判断白天/夜间，例如 Asia/Shanghai。 |
| `night_start` | `23:30` | 【作息】夜间开始：24 小时制 HH:MM。 |
| `night_end` | `07:30` | 【作息】夜间结束：24 小时制 HH:MM。 |
| `night_delay_multiplier` | `2.0` | 【作息】夜间延迟倍率：夜间打字速度变慢的倍率。 |
| `night_reply_multiplier` | `0.5` | 【作息】夜间群聊接话倍率：夜间群聊主动接话概率乘以该值。 |
| `night_silence_groups` | `True` | 【作息】夜间群聊不主动接话：夜间未被 @ 的群聊直接保持沉默；私聊/@ 仍按配置处理。 |
| `night_direct_reply` | `True` | 【作息】夜间仍回复私聊/@：夜间被直接找时是否仍然回复。关闭后夜间只记录不回复。 |

### 主动

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `proactive_enabled` | `True` | 【主动】启用后台生活循环：定期评估是否主动冒泡；不是每次都发，会结合活跃度与精力。 |
| `active_chat_probability` | `0.0` | 【主动】每轮冒泡概率：后台每轮检查时的基础冒泡概率；建议 0.02~0.08。 |
| `proactive_min_interval_minutes` | `45` | 【主动】两次冒泡最小间隔（分钟）：避免刚冒泡完又冒泡。 |
| `proactive_max_per_day` | `4` | 【主动】每日最多冒泡次数：0 表示不限制。 |
| `proactive_min_group_idle_minutes` | `10` | 【主动】群聊最少安静时长（分钟）：群刚聊得火热时不主动插话。 |
| `proactive_max_group_idle_minutes` | `180` | 【主动】群聊最长安静时长（分钟）：群太久没人说话也不冒泡，避免自说自话。 |
| `proactive_ignored_penalty` | `0.15` | 【主动】被忽略后的概率衰减：上次冒泡没人理时，下次概率按此比例降低。 |
| `proactive_night_enabled` | `False` | 【主动】夜间也允许冒泡：默认夜间不主动打扰。 |

### 表情

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `enable_sticker_coordination` | `True` | 【表情】与表情管理插件协作：提示 AI 用 emotions 插件的 xemo_get_best_emotion_path 取图，本插件只负责发送时机。 |
| `media_delay_min` | `0.3` | 【表情】发图前延迟下限（秒）：模拟挑选/加载图片的时间。 |
| `media_delay_max` | `1.2` | 【表情】发图前延迟上限（秒）：模拟挑选/加载图片的时间。 |
| `sticker_emotion_hint` | `True` | 【表情】情绪明显时提示 AI 可发表情：满足情绪阈值、冷却和概率时，在提示词里建议 AI 自行决定是否发 1 张表情；不会自动发送。 |
| `sticker_mood_threshold` | `20` | 【表情】情绪提示阈值：心情偏离基线达到该值时才考虑提示发表情。 |
| `sticker_hint_probability` | `0.35` | 【表情】情绪提示概率：满足情绪与冷却条件时，每次回复注入表情建议的概率。 |
| `sticker_cooldown_minutes` | `10` | 【表情】表情冷却（分钟）：距离上次提示或发送图片不足该时间时，不再提示表情。普通文件不计入冷却。 |

### 画图

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `draw_refuse_enabled` | `True` | 【画图】启用概率拒绝：用户明确要求画图时，按概率拒绝；只对普通用户生效。 |
| `draw_refuse_probability` | `0.8` | 【画图】拒绝概率：普通用户请求画图时被拒绝的概率；0 表示不拒绝，1 表示总是拒绝。 |
| `draw_refuse_exempt_superusers` | `True` | 【画图】超级管理员豁免拒绝：Nekro `SUPER_USERS` 中的账号请求画图时不适用拒绝概率。 |
| `draw_proactive_enabled` | `True` | 【画图】允许主动画图：允许 AI 在合适场景主动画图；使用独立概率。 |
| `draw_proactive_probability` | `0.1` | 【画图】主动画图概率：每轮判断是否允许主动画图的独立概率，仍需满足场景条件。 |
| `draw_proactive_cooldown_minutes` | `180` | 【画图】主动画图冷却（分钟）：两次主动画图之间的建议最小间隔。 |
| `draw_proactive_max_per_day` | `1` | 【画图】主动画图每日上限：每天最多主动画几张；0 表示不允许主动画。 |

### 联网

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `human_search_enabled` | `True` | 【联网】启用 `human_search`：允许 AI 通过 DeepSeek Search 查询实时网页信息。 |
| `human_fetch_enabled` | `True` | 【联网】启用 `human_fetch`：允许 AI 抓取网页正文与 B 站评论；关闭后不会调用抓取工具。 |
| `human_search_api_key` | 空 | 【联网】DeepSeek API Key：用于 Search/Fetch 的 Bearer Key；留空则联网工具不可用。 |
| `human_search_base_url` | `https://api.deepseek.com` | 【联网】DeepSeek API 地址。 |
| `human_search_max_results` | `5` | 【联网】默认搜索结果数，范围 1-10。 |
| `human_search_timeout_seconds` | `12` | 【联网】Search/Fetch 单次请求超时（秒）。 |
| `human_search_need_content` | `False` | 【联网】搜索是否返回网页正文；一般保持关闭，需要全文时用 `human_fetch`。 |
| `human_fetch_max_chars` | `6000` | 【联网】`human_fetch` 返回正文的最大字符数，超出会截断。 |
| `bili_comments_enabled` | `True` | 【联网】B站视频自动附带评论：`human_fetch` 遇到 B 站链接时调用公开 API 获取标题、简介和评论。 |
| `bili_comments_limit` | `10` | 【联网】B站评论条数：默认 10，0 表示只返回视频信息。 |
| `bili_comments_sort` | `hot` | 【联网】B站评论排序：`hot` 热门，`time` 最新。 |
| `link_fetch_enabled` | `True` | 【联网】允许 AI 根据最近链接上下文判断是否调用 `human_fetch`。 |
| `link_fetch_probability` | `0.3` | 【联网】模糊指代时的自动抓取概率；明确引用不受此限制。 |
| `link_context_limit` | `5` | 【联网】注入提示词的最近链接候选数量。 |
| `link_context_max_age_minutes` | `30` | 【联网】最近链接有效期（分钟）。 |
| `quoted_link_always_fetch` | `True` | 【联网】明确引用带链接消息时，100% 允许抓取。 |

### Bangumi

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `bangumi_enabled` | `True` | 【Bangumi】启用动漫搜索、条目详情、角色和每日放送工具。 |
| `bangumi_access_token` | 空 | 【Bangumi】Access Token；留空仍可匿名查询公开条目，NSFW/部分受限内容不可用。 |
| `bangumi_base_url` | `https://api.bgm.tv` | 【Bangumi】API 地址。 |
| `bangumi_user_agent` | `humanoid_chat/3.5.0 ...` | 【Bangumi】请求 User-Agent；Bangumi 要求带可识别 UA。 |
| `bangumi_timeout_seconds` | `12` | 【Bangumi】单次请求超时（秒）。 |
| `bangumi_search_limit` | `5` | 【Bangumi】搜索结果数。 |
| `bangumi_character_limit` | `10` | 【Bangumi】角色结果数。 |
| `bangumi_calendar_limit` | `10` | 【Bangumi】每日放送结果数。 |
| `bangumi_include_nsfw` | `False` | 【Bangumi】是否包含 NSFW 条目；需要有效 Token。 |

### 回复方式

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `follow_trigger_reply_style` | `True` | 【回复方式】按触发方式决定首条格式：总开关：按对方是普通@、引用+@、私聊/叫名字，自动纠正本轮第一条文字的 @ 与引用。 |
| `at_first_reply_plain` | `True` | 【回复方式】普通@ → 首条纯文本：对方只是 @ 你时，第一条回复不 @、不引用，直接说内容。 |
| `quote_at_first_reply_quote_at` | `True` | 【回复方式】引用+@ → 首条也引用+@：对方引用你的消息并 @ 你时，第一条回复 @ 对方并引用刚刚触发的那条消息。 |
| `non_at_first_reply_plain` | `True` | 【回复方式】私聊/叫名字/仅引用 → 首条纯文本：非 @ 触发时，第一条回复不 @、不引用。 |
| `strip_punctuation` | `True` | 【回复方式】去掉回复中的标点符号：发送前自动删除句号、逗号、问号、感叹号、引号、括号等标点；@ 提及、链接、代码和路径会保留。 |
| `punctuation_chars` | `。，！？；：、…—～~·,.!?;:'"()[]{}<>《》〈〉「」『』（）【】“”‘’-/` | 【回复方式】要删除的标点字符：按字符删除，可自行增删；@ 提及、链接、代码、路径、数字小数、负数、时间、`km/h` 等单位会被保护。 |

### 闸门

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `strict_send_gate` | `False` | 【闸门】严格拦截无触发记录的群消息：开启后，群聊里没有唤醒记录的发送会被丢弃。默认关闭，避免误伤命令、定时任务等正常回复。 |

### 防重复

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `anti_repeat_window` | `20` | 【防重复】检查最近多少条：最近发送文本中完全相同的内容会被处理。 |
| `anti_repeat_action` | `vary` | 【防重复】处理方式：vary=轻微改写后发送；skip=直接跳过；off=关闭。 |

### 调试

| 配置键 | 默认值 | 说明 |
|---|---|---|
| `debug_log` | `False` | 【调试】详细日志：打印漏斗判定、延迟、状态更新等详细信息。 |

