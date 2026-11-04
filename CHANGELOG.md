# Changelog

## 3.9.5 - 2026-11-04

- 修复戳回去后，机器人自己的戳一戳通知因文本包含机器人名字而再次触发 AI 的问题。
- 所有非“戳机器人”的 poke 通知现在都阻止触发，不进入 LLM；避免戳回去形成 AI 回环。
- 版本升至 `3.9.5`。

## 3.9.4 - 2026-11-04

- 新增戳一戳三选一响应：AI 回复、戳回去、完全不回应。
- 默认概率为 AI 5% / 戳回 15% / 不回应 80%，同一群同一人 60 秒冷却。
- 戳回去与不回应都会阻止 Agent 触发，不消耗 LLM token；戳回去只调用 OneBot `group_poke`。
- 新增 `poke_reply_ai_probability`、`poke_reply_poke_probability`、`poke_reply_cooldown_seconds` 配置。
- 版本升至 `3.9.4`。

## 3.9.3 - 2026-11-03

- 插件元信息与文档链接更新为 GitHub 仓库地址。
- README 改为通用安装、配置和使用说明，移除个人环境与特定群信息。
- 用户可见文案中的固定机器人名改为通用“机器人”。
- Bangumi User-Agent 更新为当前版本和 GitHub 仓库地址。
- 移除代码中硬编码的 NAS 上传目录回退路径。
- 版本升至 `3.9.3`。

## 3.9.2 - 2026-11-03

- 新增 `/group_learn_list`：按置信度列出当前群已批准词条，标注自动/手动和是否过期。
- 新增 `/group_learn_revoke <编号|词|all>`：精确撤销已批准词条，不需要手改 YAML。
- 撤销已批准词条时同步移除 `last_auto_applied` 中的对应项，避免之后 `/group_learn_undo` 又把它退回。
- 撤销前仍会备份群档案；`/group_learn_undo` 仍保留为整批撤销自动应用。
- 版本升至 `3.9.2`。

## 3.9.1 - 2026-11-03

- `/group_learn` 改为自动应用高置信度安全候选，单次最多 3 条，默认阈值 0.85，自动有效期 14 天。
- 未自动应用的候选按 `1/2/3` 编号输出，支持 `/group_learn_approve 1 3`、`/group_learn_approve all` 和按词批准。
- 新增 `/group_learn_undo`：撤销最近一次自动应用批次，并把词条退回候选列表。
- 自动应用只添加新词，不覆盖已有词；写入前仍备份群档案。
- 新增 `group_learn_auto_apply`、`group_learn_auto_apply_min_confidence`、`group_learn_auto_apply_limit`、`group_learn_auto_ttl_days` 配置。
- 版本升至 `3.9.1`。

## 3.9.0 - 2026-11-03

- 新增群黑话候选流程：`/group_learn` 扫描近期群聊并生成候选，只写入 `*.learned_terms.candidates.yaml`，不自动应用。
- 新增 `/group_learn_approve <词>` 和 `/group_learn_reject <词>`；批准后才写入群档案的 `learned_terms`。
- 候选提取会过滤命令、机器人、图片占位符、图片文件名、链接和随机哈希；发送者匿名化为“群友N”。
- `learned_terms` 带置信度、证据、更新时间和过期时间；注入时只取未过期、置信度最高的前 N 条；重新生成群档案时保留已批准词条。
- 新增 `group_learn_enabled`、`group_learn_lookback_days`、`group_learn_max_messages`、`group_learn_max_candidates`、`group_learn_min_confidence`、`group_learn_term_limit`、`group_learn_inject_limit`、`group_learn_ttl_days` 配置。
- 版本升至 `3.9.0`。

## 3.8.0 - 2026-11-03

- 新增每天随机自动发 QQ 空间：默认 `09:00~23:00` 窗口内随机一次，当天只发 1 条。
- 内容使用 Nekro 默认人设（`AI_CHAT_DEFAULT_PRESET_ID`）通过默认模型组生成，不绑定某个群或私聊。
- 当天已通过 `human_qzone_publish` 发过说说时自动跳过；重启后通过 `plugin.store` 保留当天目标时间，不重复发。
- 离线恢复支持最多 30 分钟补发；窗口结束、生成 `EMPTY`、内容过长或发布失败时当天跳过，失败最多重试 1 次。
- 新增 `qzone_daily_enabled`、`qzone_daily_window_start`、`qzone_daily_window_end`、`qzone_daily_catchup_minutes`、`qzone_daily_max_chars`、`qzone_daily_themes` 配置。
- 版本升至 `3.8.0`。

## 3.7.0 - 2026-11-02

- 新增 `human_qzone_publish`：通过 NapCat `send_qzone_msg` 发布 QQ 空间说说，支持文字和最多 9 张图片。
- 默认所有人可见，可配置 `ugc_right`；图片支持本地路径转 base64、HTTP URL 和 base64。
- 支持主动发空间，但工具层强制冷却和每日上限，默认 360 分钟、每日 1 条。
- 提示词要求不发聊天记录、群聊截图、他人隐私、联系方式、住址、定位；失败不假装成功。
- 新增 `qzone_enabled`、`qzone_default_ugc_right`、`qzone_max_chars`、`qzone_images_enabled`、`qzone_max_images`、`qzone_proactive_enabled`、`qzone_cooldown_minutes`、`qzone_max_per_day` 配置。
- 版本升至 `3.7.0`。

## 3.6.0 - 2026-11-02

- 新增红包卡片识别：记录最近红包标题、时间和是否点名机器人。
- 不主动提红包；有人让机器人收/领/抢红包时，提示 AI 用“QQ没实名”自然推脱。
- 不调用领取接口、不假装收到、不报金额、不反复解释。
- 指定给机器人的红包也只在用户要求时回应，不主动提。
- 新增 `red_packet_enabled`、`red_packet_refusal_reason`、`red_packet_context_minutes` 配置。
- 版本升至 `3.6.0`。

## 3.5.1 - 2026-11-02

- 强化 Bangumi 触发规则：群聊涉及具体动漫作品、角色、声优、新番、评分、播出时间等可验证事实，且 AI 不确定时，必须先查 Bangumi，不能凭记忆编。
- 闲聊、表达喜好、玩梗、没有具体事实要确认时不查，避免打扰群聊。
- 限制每轮最多 1 次搜索，查不到明确说没查到，不连续重试。
- 版本升至 `3.5.1`。

## 3.5.0 - 2026-11-02

- 新增 Bangumi 动漫资料工具：`human_bangumi_search`、`human_bangumi_subject`、`human_bangumi_characters`、`human_bangumi_calendar`。
- 支持动画条目搜索、详情、评分、标签、角色/声优和每日放送查询。
- 新增 Bangumi Token、Base URL、User-Agent、超时、结果数、NSFW 等配置；Token 只放线上配置，不提交仓库。
- 提示词在动漫、新番、评分、角色、声优、放送时间话题下优先使用 Bangumi；新闻/实时事件仍用 `human_search`。
- 版本升至 `3.5.0`。

## 3.4.5 - 2026-11-02

- 修复某个群普通文字引用被反复硬拦截、形成“你引用的是...”复读链的问题。
- 引用类型新增 `card`；硬拦截只针对无 URL 卡片，普通文字引用恢复交给 AI。
- 不再硬拦截机器人自己的文字回复引用，避免链式复读。
- 图片可见性硬拦截、无链接卡片回复、链接抓取规则保持不变。
- 版本升至 `3.4.5`。

## 3.4.4 - 2026-11-02

- 无链接引用硬拦截不再依赖“这个是什么/这个呢”等关键词，改为直接检查当前消息是否在找机器人。
- 当前消息出现实际人设名或 `extra_bot_names` 中的名字时，也会触发无链接引用硬拦截，修复“机器人这个怎么样”漏拦截导致的串台。
- 版本升至 `3.4.4`。

## 3.4.3 - 2026-11-02

- 修复引用无链接卡片/文字时仍串历史 B 站链接的问题：直接根据引用内容回复，并阻止 AI 触发。
- 引用卡片无 URL 时回复“这条卡片只写了「...」，没带链接”；引用文字无 URL 时回复“你引用的是「...」，没有链接内容”。
- 引用图片的可见性硬拦截、引用链接抓取规则保持不变。
- 版本升至 `3.4.3`。

## 3.4.2 - 2026-11-02

- 引用图片时提取图片的 `file_name` / `local_path` / `remote_url`，并注入 `/app/uploads/<文件名>` 路径。
- 判断引用图片是否在最近 `AI_VISION_IMAGE_LIMIT` 张视觉图片内；不在时由 humanoid 直接回复“这张图我没看到”，并阻止 AI 触发，避免从历史 B 站链接/角色猜测。
- 图片可见时提示模型在 `recent_chat_images` 中匹配路径后直接查看，不启用 view_image、不修改核心。
- 版本升至 `3.4.2`。

## 3.4.1 - 2026-11-02

- 修复引用图片时 AI 拿上下文 B 站链接回答的问题：识别引用消息为图片后，不再注入最近链接，并明确禁止用其它链接代替。
- `human_fetch` 增加硬拦截：模糊指代且 `allow=False` 时，抓取上下文链接会被工具层拒绝；明确引用、当前消息直接给出 URL、明确要求看链接时仍放行。
- B 站分支只处理视频链接（`b23.tv`、`BV`、`av`）；`bilibili.com/toy/...` 等页面直接走 DeepSeek Fetch，避免 BV/av 解析失败。
- `human_fetch` 日志增加实际抓取 URL。
- 版本升至 `3.4.1`。

## 3.4.0 - 2026-11-02

- 新增 `human_fetch_enabled` 独立开关，可单独关闭网页抓取/B 站评论，不影响 `human_search`。
- 新增最近链接上下文：记录最近 30 分钟、最多 5 条带 URL 的消息，供 AI 判断是否抓取。
- 明确引用带链接消息时，默认 100% 允许抓取（`quoted_link_always_fetch`）。
- 模糊指代（“这个/刚才那个”）按 `link_fetch_probability`（默认 0.3）注入抓取提示，AI 再判断相关性。
- 增加“明确说看评论但没有引用”的处理：单一候选视为明确；多个候选优先最近一条，不确定则询问用户。
- 提示词要求无关不抓、多个候选不随便选；概率只控制提示，不硬预抓。
- 版本升至 `3.4.0`。

## 3.3.1 - 2026-11-02

- 修复引用消息时 AI 拿错链接的问题：现在会解析被引用消息的正文、卡片标题和 `card_url` / `qqdocurl`。
- 提示词注入【引用消息】：用户说“这个/这条/这个视频/评论”时，默认指引用消息，抓取时只用引用链接，不得改用上下文其它链接。
- B 站短链会规范化为 `https://b23.tv/<id>`，避免把带 `bbid` / `ts` 的长链接写进提示词。
- 版本升至 `3.3.1`。

## 3.3.0 - 2026-11-02

- `human_fetch` 遇到 B 站视频链接时，改为调用 B 站公开 API，直接返回标题、UP 主、播放数据、简介和热门评论。
- 支持 `bilibili.com/video/BV...`、`b23.tv` 短链和 `av` 号。
- 新增 `bili_comments_enabled`、`bili_comments_limit`、`bili_comments_sort` 配置；默认取 10 条热门评论。
- B 站 API 失败时自动回退到 DeepSeek Fetch；评论关闭或读取失败时仍返回视频信息。
- 提示词要求遇到 B 站链接时优先用 `human_fetch` 看评论，不逐条复读、不把评论当事实。
- 版本升至 `3.3.0`。

## 3.2.0 - 2026-11-02

- 新增 `human_search(query, max_results)`：通过 DeepSeek Search API 查询实时网页信息，返回标题、摘要、来源和 URL。
- 新增 `human_fetch(url, max_chars)`：通过 DeepSeek Fetch API 抓取网页 Markdown 正文，按配置截断。
- 新增 DeepSeek Base URL、API Key、结果数、超时、搜索正文开关、抓取最大字符数等配置；Key 未配置时明确报错，不静默编造。
- 新增【联网查询】提示词：实时信息先搜索、引用 URL、摘要不足再抓取、每轮限制调用次数。
- 修复消息标点清理误删数字小数、负数、时间、日期和 `km/h` / `m/s` 等单位的问题。
- 版本升至 `3.2.0`。

## 3.1.0 - 2026-11-01

- 新增画图概率拒绝：普通用户明确要求画图时，按 `draw_refuse_probability` 概率拒绝；超级管理员通过 `SUPER_USERS` 默认豁免。
- 拒绝时不调用「绘图」/「多图绘制」，不生成图片、不重试；用符合人设的 1 句短话拒绝或转移话题，不解释概率/系统/模型。
- 新增主动画图独立概率、冷却和每日上限：默认 `0.1`、`180` 分钟、`1` 张/天；不套用用户请求的拒绝概率。
- 明确「绘图」生成新图与「表情管理」`xemo_get_best_emotion_path` 现有表情包的边界，避免混用。
- 仅修改 human_chat 提示词与配置，不修改内置 draw 插件；概率与频率为提示词层约束。

## 3.0.2 - 2026-10-30

- 新增【社交直觉与表达习惯】提示：17 字左右、7~10 字小短句、凭直觉接话、不霸道。
- 明确禁止 Emoji、颜文字、句尾 `~` / `呀` / `呢` / `哦` 和 AI 腔。
- 机器人昵称改为读取 `extra_bot_names` + 当前人设名，不再硬编码。
- 情绪强烈/紧张/害羞/震惊/直白且句子很短时，明确要求主动考虑配 1 张表情包/图片；给出 `xemo_get_best_emotion_path` + `send_msg_file` 的完整流程、适用/不适用场景，以及没有合适图时的回退规则。优先文字，不主动发语音。
- 去除插件生成的口癖中的 `~`，并在标点清理字符中加入 ASCII `~`。

## 3.0.1 - 2026-10-30

- 强化提示词中的【代码格式铁律】：禁止裸文本、Markdown 围栏、`<SPLIT>` / `[TSPLIT]`、发明不存在的方法。
- 明确自然语言只能写在字符串内、代码语法使用英文标点、工具返回值不拼进聊天内容。
- 增加正确/错误示例和发送前自检清单，降低沙盒 SyntaxError 概率。

## 3.0.0 - 2026-10-30

- 重写拟人交互管线：分段、随机延迟、首段思考、夜间/精力倍率、连发、被打断。
- 新增情绪、精力、耐心、熟悉度和小事记忆。
- 新增每群 YAML 档案：身份、群主/管理员、关键人物、群文化、语气、群规、管理策略。
- 新增自动角色识别（OneBot `get_group_member_info`）+ 手动覆盖 + 缓存。
- 新增 `/group_profile_gen` 群档案生成器：
  - 只统计与机器人直接互动的人
  - 自动生成角色/人物/文化/语气/管理策略
  - 保留群描述、人物描述和群规
  - 生成前备份
- 新增 `/force_mute` 强制禁言/解禁命令。
- 支持群规动作：`remind` / `recall` / `mute` / `recall_and_mute` / `recall_and_kick` / `observe_kick`。
- 与 `XiaoJiu.group_admin` 协作执行实际禁言/撤回/踢人。
- 与 `xggm.emotions` 协作发表情包，不接管表情库。
- 与 `liugu.nekro_favorability` 分工：不重复维护长期好感度。
- 与 Nekro 记忆系统/`KroMiose.memory_tools` 协作：被动注入 + 主动检索。
- 回复方式：按普通 @ / 引用+@ / 私聊/叫名字动态控制首条 @/引用。
- 去标点、防重复、口语化瑕疵、错字更正。
- 修复：`[TSPLIT]` 变体漏出、工具返回值 `True` 拖尾、撤回时缺少 `message_id`。
