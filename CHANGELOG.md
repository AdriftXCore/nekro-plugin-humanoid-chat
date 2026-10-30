# Changelog

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
  - 只统计与 KONA 直接互动的人
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
