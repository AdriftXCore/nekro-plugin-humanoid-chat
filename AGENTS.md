# AGENTS.md

本仓库是 Nekro Agent 插件 `humanoid_chat` 的源码仓库。运行时把 `humanoid_chat.py` 放入你的 Nekro Agent 插件工作目录。

## 修改后必须做

1. 先跑自检：

   ```bash
   ./scripts/check.sh
   ```

2. 部署到你的 Nekro Agent 环境并热重载：

   ```bash
   ./scripts/deploy.sh --reload
   ```

3. 提交并推送：

   ```bash
   ./scripts/publish.sh "feat: ..."
   ```

## 配置

- `config.yaml` 是示例配置，不含密钥。
- `docs/CONFIG.md` 是 `HumanoidConfig` 全量字段说明。
- 新增/删除配置字段时，同步更新：
  - `config.yaml`
  - `docs/CONFIG.md`
  - `README.md` 的相关说明
  - `NekroPlugin(version=...)`
  - `CHANGELOG.md`

## 群档案

- 真实档案在 Nekro 数据目录的 `plugin_data/afx.humanoid_chat/group_profiles/`。
- 仓库只提交 `examples/` 脱敏模板。
- **不要提交真实群成员 QQ、昵称、群规或聊天内容。**
- 生成器命令：`/group_profile_gen`；只统计与机器人直接互动的人，保留 `description` 和 `rules`。

## 依赖边界

- 本插件维护：分段/延迟、情绪/精力、群档案、提示词、`/force_mute`、`/group_profile_gen`、`human_search` / `human_fetch` 联网工具。
- 联网搜索/抓取使用 DeepSeek Search/Fetch API；B 站链接会额外调用公开 API 读取视频信息和热门评论；Bangumi 资料使用 api.bgm.tv；Key/Token 只放插件配置，不写入仓库。
- 红包只做识别和 AI 话术推脱，不领取、不接 NapCat 抢红包插件。
- QQ空间说说通过 NapCat `send_qzone_msg` 发布，工具层限制冷却和每日上限。
- 实际禁言/撤回/踢人由 `XiaoJiu.group_admin` 执行；不要在本插件里重复实现。
- 表情由 `xggm.emotions` 负责；不要接管图库或表情 ID。
- 长期好感度由 `liugu.nekro_favorability` 负责；本插件只有即时熟悉度。
- 长期记忆由 Nekro 核心记忆系统负责；不要重复实现向量库。

## 安全

- 不提交密钥、token、cookie。
- 不提交真实群档案。
- 修改 ACL / 群管权限后要重启 `nekro_agent`。
- 测试踢人/禁言必须用测试号，并确认可重新拉回群。
- 本仓库不包含 `sudo`、宿主机网络、SSH 配置相关操作。
