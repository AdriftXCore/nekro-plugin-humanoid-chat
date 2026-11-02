"""拟人交互助手 v3

在 humanoid_chat v2.9.0 的基础上重写「像人」的部分：

- 可配置的分段、思考停顿、逐字延迟、连发与夜间减速
- 情绪、精力、耐心、对单个用户的熟悉度与小事记忆
- 作息/疲劳：夜间变慢、低精力少说、睡眠时段降低主动冒泡
- 拟真瑕疵：口癖、省略号、重复字、偶发错字后更正
- 主动/潜水：根据群活跃度、被忽略程度、每日上限自适应
- 与「表情管理」插件协作：不碰图库与表情 ID，只用它给的路径
- 与「好感度系统」插件协作：不重复维护长期好感度，只补充即时情绪

部署位置：/volume1/docker/nekro-agent/plugins/workdir/humanoid_chat.py
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Deque, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

from nekro_agent.api import message
from nekro_agent.api.plugin import (
    Arg,
    CmdCtl,
    CommandExecutionContext,
    CommandPermission,
    CommandResponse,
    ConfigBase,
    ExtraField,
    NekroPlugin,
    SandboxMethodType,
)
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.api.signal import MsgSignal
from nekro_agent.models.db_chat_channel import DBChatChannel
from nekro_agent.models.db_chat_message import DBChatMessage

try:
    import nonebot
    import nonebot.message
    from nonebot.internal.adapter import Bot, Event
    from nonebot.message import event_preprocessor
    from nonebot.typing import T_State

    NONEBOT_AVAILABLE = True
except ImportError:
    NONEBOT_AVAILABLE = False


# ============================================================
# 1. 插件元信息
# ============================================================

INSTANCE_ID = random.randint(1000, 9999)

plugin = NekroPlugin(
    name="拟人交互助手",
    module_name="humanoid_chat",
    description="让回复更像真人：可配置分段与打字节奏、情绪精力、关系记忆、作息疲劳、主动潜水与拟真瑕疵；并提供 DeepSeek 联网搜索与网页抓取。",
    author="afx",
    version="3.5.0",
    url="https://github.com/nekro-agent/humanoid-chat",
    sleep_brief="让聊天回复更像真人，负责分段、打字节奏、情绪精力、作息、主动潜水与联网查询。",
)


# ============================================================
# 2. 可视化配置
# ============================================================


@plugin.mount_config()
class HumanoidConfig(ConfigBase):
    # --- 唤醒与漏斗 ---
    extra_bot_names: str = Field(
        default="",
        title="【唤醒】补充机器人昵称",
        description="除人设中的名字外，额外会被当成在叫你的称呼。逗号分隔，不区分大小写。",
    )
    trigger_keywords: str = Field(
        default="",
        title="【唤醒】感兴趣的话题词",
        description="群聊中提到这些词会提高接话概率。逗号分隔；留空则只响应名字与概率。",
    )
    keyword_reply_probability: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        title="【唤醒】命中名字/话题后的唤醒概率",
        description="命中后唤醒 AI 自主判断是否接话的概率。",
    )
    reply_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        title="【唤醒】纯闲聊插话概率",
        description="没有命中名字/话题时的搭话概率。建议 0 或 0.02，避免打扰。",
    )
    reply_cd_seconds: int = Field(
        default=30,
        ge=0,
        title="【唤醒】群聊插话冷却（秒）",
        description="非直接呼叫的主动接话后，群内冷却时间。直接叫名字/@/私聊不受此限制。",
    )
    always_reply_when_mentioned: bool = Field(
        default=True,
        title="【唤醒】@ 与私聊必回",
        description="被 @ 或私聊时无视概率与冷却，必定唤醒 AI。",
    )
    ai_self_decision: bool = Field(
        default=True,
        title="【唤醒】AI 自主决定是否插话",
        description="被话题/名字唤醒后，由 AI 结合上下文判断；觉得突兀可以保持沉默。",
    )

    # --- 分段与打字节奏 ---
    auto_split: bool = Field(
        default=True,
        title="【节奏】自动分段",
        description="AI 没有手动使用 [SPLIT] 时，按句子/逗号自动拆成多段发送。",
    )
    auto_split_min_chars: int = Field(
        default=18,
        ge=1,
        title="【节奏】自动分段最小长度",
        description="短于该长度的消息不自动拆段，避免把一句话拆得稀碎。",
    )
    min_segments: int = Field(
        default=1,
        ge=1,
        le=6,
        title="【节奏】最少段数",
        description="自动分段时尽量不少于该段数；AI 手动 SPLIT 时以其为准。",
    )
    max_segments: int = Field(
        default=4,
        ge=1,
        le=8,
        title="【节奏】最多段数",
        description="一次回复最多拆成多少段，超出部分会合并到最后一段。",
    )
    segment_delay_min: float = Field(
        default=0.35,
        ge=0.0,
        title="【节奏】段间基础延迟下限（秒）",
        description="每段发送前的基础等待时间下限。",
    )
    segment_delay_max: float = Field(
        default=1.1,
        ge=0.0,
        title="【节奏】段间基础延迟上限（秒）",
        description="每段发送前的基础等待时间上限。",
    )
    char_delay_min: float = Field(
        default=0.012,
        ge=0.0,
        title="【节奏】逐字延迟下限（秒/字）",
        description="模拟打字速度：每个字额外等待的下限。",
    )
    char_delay_max: float = Field(
        default=0.045,
        ge=0.0,
        title="【节奏】逐字延迟上限（秒/字）",
        description="模拟打字速度：每个字额外等待的上限。",
    )
    punctuation_pause: float = Field(
        default=0.35,
        ge=0.0,
        title="【节奏】句末停顿（秒）",
        description="段落以问号/句号/感叹号等结尾时额外停顿。",
    )
    thinking_delay_min: float = Field(
        default=0.4,
        ge=0.0,
        title="【节奏】首段思考延迟下限（秒）",
        description="看到消息后到第一段发出前的思考/阅读时间下限。",
    )
    thinking_delay_max: float = Field(
        default=1.6,
        ge=0.0,
        title="【节奏】首段思考延迟上限（秒）",
        description="看到消息后到第一段发出前的思考/阅读时间上限。",
    )
    max_segment_delay: float = Field(
        default=6.0,
        ge=0.1,
        title="【节奏】单次等待上限（秒）",
        description="任何一段的等待时间都不会超过该值，避免回复卡太久。",
    )
    min_segment_gap: float = Field(
        default=2.0,
        ge=0.0,
        title="【节奏】段间最小间隔（秒）",
        description="每段之间至少等待这么久；连发概率只会缩短计算延迟，但不会低于该间隔。",
    )
    burst_probability: float = Field(
        default=0.18,
        ge=0.0,
        le=1.0,
        title="【节奏】连发概率",
        description="偶尔像真人一样快速补发下一段（跳过大部分基础延迟）。",
    )
    interrupt_on_new_message: bool = Field(
        default=True,
        title="【节奏】被新消息打断时停止后续分段",
        description="正在分段发送时对方又发来消息，停止剩余分段，像真人一样先看新消息。",
    )

    # --- 拟真瑕疵 ---
    enable_imperfections: bool = Field(
        default=True,
        title="【瑕疵】启用口语化瑕疵",
        description="口癖、省略号、重复字、偶发错字后更正。只作用于纯聊天文本，不碰链接/代码/提及。",
    )
    filler_rate: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
        title="【瑕疵】口癖概率",
        description="在句首加入「嗯/诶/那个」等口癖的概率。",
    )
    filler_words: str = Field(
        default="嗯,诶,那个,让我想想,哈哈,欸",
        title="【瑕疵】口癖词表",
        description="逗号分隔，随机挑选。",
    )
    trailing_ellipsis_rate: float = Field(
        default=0.12,
        ge=0.0,
        le=1.0,
        title="【瑕疵】句尾省略号/波浪号概率",
        description="句尾没有标点时，偶尔补一个「…」或「~」。",
    )
    duplicate_char_rate: float = Field(
        default=0.03,
        ge=0.0,
        le=1.0,
        title="【瑕疵】重复字概率",
        description="偶尔把「好」发成「好好」这类轻微口吃。",
    )
    correction_rate: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        title="【瑕疵】错字后更正概率",
        description="偶发先发一个错字版本，再补一句更正。概率建议很低。",
    )
    correction_prefix: str = Field(
        default="啊打错了，",
        title="【瑕疵】更正前缀",
        description="更正消息前加的口头语。",
    )

    # --- 情绪 / 精力 / 关系 ---
    mood_baseline: int = Field(
        default=60,
        ge=0,
        le=100,
        title="【情绪】心情基线",
        description="情绪会缓慢回落到该值。",
    )
    mood_decay_hours: float = Field(
        default=6.0,
        ge=0.1,
        title="【情绪】心情回落时长（小时）",
        description="情绪偏离基线后，大约多久回落一半。",
    )
    energy_enabled: bool = Field(
        default=True,
        title="【精力】启用精力系统",
        description="精力影响回复速度、分段数量和主动冒泡。",
    )
    energy_start: int = Field(
        default=80,
        ge=0,
        le=100,
        title="【精力】初始精力",
        description="新频道首次出现时的精力值。",
    )
    energy_cost_per_message: float = Field(
        default=1.5,
        ge=0.0,
        title="【精力】每条消息消耗",
        description="每发一条分段消息消耗的精力。",
    )
    energy_recover_day_per_hour: float = Field(
        default=6.0,
        ge=0.0,
        title="【精力】白天每小时恢复",
        description="非睡眠时段的精力恢复速度。",
    )
    energy_recover_night_per_hour: float = Field(
        default=18.0,
        ge=0.0,
        title="【精力】夜间每小时恢复",
        description="睡眠时段的精力恢复速度。",
    )
    low_energy_threshold: int = Field(
        default=30,
        ge=0,
        le=100,
        title="【精力】低精力阈值",
        description="低于该值后回复更慢、更短、更少主动说话。",
    )
    low_energy_reply_multiplier: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        title="【精力】低精力接话倍率",
        description="低精力时，群聊接话概率乘以该值。",
    )
    low_energy_delay_multiplier: float = Field(
        default=1.8,
        ge=1.0,
        title="【精力】低精力延迟倍率",
        description="低精力时，打字延迟乘以该值。",
    )
    patience_start: int = Field(
        default=70,
        ge=0,
        le=100,
        title="【情绪】初始耐心",
        description="被连续轰炸或被无视会降低耐心。",
    )
    patience_recover_per_hour: float = Field(
        default=8.0,
        ge=0.0,
        title="【情绪】耐心每小时恢复",
        description="耐心随时间恢复的速度。",
    )
    rapid_message_window: float = Field(
        default=8.0,
        ge=0.0,
        title="【情绪】连续消息判定窗口（秒）",
        description="同一用户在该时间内继续发消息，视为连续轰炸。",
    )
    rapid_patience_cost: float = Field(
        default=6.0,
        ge=0.0,
        title="【情绪】连续消息耐心消耗",
        description="连续轰炸时每次额外消耗的耐心。",
    )
    familiarity_enabled: bool = Field(
        default=True,
        title="【关系】启用熟悉度",
        description="按用户累计熟悉度；与「好感度系统」插件的长期评分互不替代。",
    )
    familiarity_gain: float = Field(
        default=1.2,
        ge=0.0,
        title="【关系】每条消息熟悉度增量",
        description="正常互动时的熟悉度增长；连续轰炸会打折。",
    )
    familiarity_max: int = Field(
        default=100,
        ge=1,
        title="【关系】熟悉度上限",
        description="熟悉度封顶值。",
    )
    memory_limit: int = Field(
        default=8,
        ge=0,
        le=30,
        title="【关系】每用户小事记忆条数",
        description="AI 通过 humanoid_remember 记录的小事最多保留多少条。",
    )
    enable_memory: bool = Field(
        default=True,
        title="【关系】启用小事记忆工具",
        description="允许 AI 调用 humanoid_remember 记录值得记住的互动。",
    )

    # --- 本群档案 ---
    group_profile_enabled: bool = Field(
        default=True,
        title="【本群档案】启用每群 YAML 档案",
        description="从插件数据目录的 group_profiles/<chat_key>.yaml 读取身份、人物、群规和管理策略。",
    )
    group_profile_dir: str = Field(
        default="",
        title="【本群档案】档案目录",
        description="留空使用插件数据目录下的 group_profiles；也可填绝对路径。",
    )
    group_role_cache_minutes: int = Field(
        default=10,
        ge=1,
        title="【本群档案】群角色缓存（分钟）",
        description="自动识别 KONA 在群里的 owner/admin/member 角色，缓存多久。",
    )
    group_profile_max_chars: int = Field(
        default=2400,
        ge=200,
        title="【本群档案】注入长度上限",
        description="本群档案注入提示词的最大字符数，超出会截断；群规较多时建议 2000 以上。",
    )
    group_profile_member_limit: int = Field(
        default=8,
        ge=1,
        le=20,
        title="【本群档案】自动生成关键人物数",
        description="生成器只把和 KONA 直接互动过的前 N 人写进 members。",
    )
    group_profile_preserve_limit: int = Field(
        default=12,
        ge=1,
        le=30,
        title="【本群档案】保留人物上限",
        description="重新生成时，已有描述但本次未进前 N 的人会追加保留，members 总数不超过该值。",
    )
    group_profile_generator_lookback_days: int = Field(
        default=30,
        ge=1,
        le=365,
        title="【本群档案】生成器回看天数",
        description="生成器统计互动时回看最近多少天的聊天记录。",
    )

    # --- 强制禁言 ---
    force_mute_default_seconds: int = Field(
        default=600,
        ge=1,
        title="【强制禁言】默认时长（秒）",
        description="force_mute 命令不写时长时使用的默认禁言秒数。",
    )
    force_mute_max_seconds: int = Field(
        default=86400,
        ge=1,
        title="【强制禁言】最大时长（秒）",
        description="force_mute 命令允许的最长禁言秒数，超出会被截断。",
    )
    force_mute_allow_admins: bool = Field(
        default=False,
        title="【强制禁言】允许禁言管理员",
        description="仅当 KONA 自己是群主时生效；默认不允许对管理员执行强制禁言。",
    )

    # --- 作息与疲劳 ---
    timezone: str = Field(
        default="Asia/Shanghai",
        title="【作息】时区",
        description="用于判断白天/夜间，例如 Asia/Shanghai。",
    )
    night_start: str = Field(
        default="23:30",
        title="【作息】夜间开始",
        description="24 小时制 HH:MM。",
    )
    night_end: str = Field(
        default="07:30",
        title="【作息】夜间结束",
        description="24 小时制 HH:MM。",
    )
    night_delay_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        title="【作息】夜间延迟倍率",
        description="夜间打字速度变慢的倍率。",
    )
    night_reply_multiplier: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="【作息】夜间群聊接话倍率",
        description="夜间群聊主动接话概率乘以该值。",
    )
    night_silence_groups: bool = Field(
        default=True,
        title="【作息】夜间群聊不主动接话",
        description="夜间未被 @ 的群聊直接保持沉默；私聊/@ 仍按配置处理。",
    )
    night_direct_reply: bool = Field(
        default=True,
        title="【作息】夜间仍回复私聊/@",
        description="夜间被直接找时是否仍然回复。关闭后夜间只记录不回复。",
    )

    # --- 主动冒泡 / 潜水 ---
    proactive_enabled: bool = Field(
        default=True,
        title="【主动】启用后台生活循环",
        description="定期评估是否主动冒泡；不是每次都发，会结合活跃度与精力。",
    )
    active_chat_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        title="【主动】每轮冒泡概率",
        description="后台每轮检查时的基础冒泡概率；建议 0.02~0.08。",
    )
    proactive_min_interval_minutes: int = Field(
        default=45,
        ge=1,
        title="【主动】两次冒泡最小间隔（分钟）",
        description="避免刚冒泡完又冒泡。",
    )
    proactive_max_per_day: int = Field(
        default=4,
        ge=0,
        title="【主动】每日最多冒泡次数",
        description="0 表示不限制。",
    )
    proactive_min_group_idle_minutes: int = Field(
        default=10,
        ge=1,
        title="【主动】群聊最少安静时长（分钟）",
        description="群刚聊得火热时不主动插话。",
    )
    proactive_max_group_idle_minutes: int = Field(
        default=180,
        ge=1,
        title="【主动】群聊最长安静时长（分钟）",
        description="群太久没人说话也不冒泡，避免自说自话。",
    )
    proactive_ignored_penalty: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        title="【主动】被忽略后的概率衰减",
        description="上次冒泡没人理时，下次概率按此比例降低。",
    )
    proactive_night_enabled: bool = Field(
        default=False,
        title="【主动】夜间也允许冒泡",
        description="默认夜间不主动打扰。",
    )

    # --- 表情 / 多模态协作 ---
    enable_sticker_coordination: bool = Field(
        default=True,
        title="【表情】与表情管理插件协作",
        description="提示 AI 用 emotions 插件的 xemo_get_best_emotion_path 取图，本插件只负责发送时机。",
    )
    media_delay_min: float = Field(
        default=0.3,
        ge=0.0,
        title="【表情】发图前延迟下限（秒）",
        description="模拟挑选/加载图片的时间。",
    )
    media_delay_max: float = Field(
        default=1.2,
        ge=0.0,
        title="【表情】发图前延迟上限（秒）",
        description="模拟挑选/加载图片的时间。",
    )
    sticker_emotion_hint: bool = Field(
        default=True,
        title="【表情】情绪明显时提示 AI 可发表情",
        description="满足情绪阈值、冷却和概率时，在提示词里建议 AI 自行决定是否发 1 张表情；不会自动发送。",
    )
    sticker_mood_threshold: int = Field(
        default=20,
        ge=0,
        le=100,
        title="【表情】情绪提示阈值",
        description="心情偏离基线达到该值时才考虑提示发表情。",
    )
    sticker_hint_probability: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        title="【表情】情绪提示概率",
        description="满足情绪与冷却条件时，每次回复注入表情建议的概率。",
    )
    sticker_cooldown_minutes: int = Field(
        default=10,
        ge=0,
        title="【表情】表情冷却（分钟）",
        description="距离上次提示或发送图片不足该时间时，不再提示表情。普通文件不计入冷却。",
    )

    draw_refuse_enabled: bool = Field(
        default=True,
        title="【画图】启用概率拒绝",
        description="用户明确要求画图时，按概率拒绝；只对普通用户生效，超级管理员可豁免。",
    )
    draw_refuse_probability: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        title="【画图】拒绝概率",
        description="普通用户请求画图时被拒绝的概率；0 表示不拒绝，1 表示总是拒绝。",
    )
    draw_refuse_exempt_superusers: bool = Field(
        default=True,
        title="【画图】超级管理员豁免拒绝",
        description="开启后，Nekro SUPER_USERS 中的账号请求画图时不适用拒绝概率。",
    )
    draw_proactive_enabled: bool = Field(
        default=True,
        title="【画图】允许主动画图",
        description="允许 AI 在合适场景主动画图；主动画图使用独立概率，不套用用户请求的拒绝概率。",
    )
    draw_proactive_probability: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        title="【画图】主动画图概率",
        description="每轮判断是否允许主动画图的独立概率；仍需要满足场景条件，不确定就不画。",
    )
    draw_proactive_cooldown_minutes: int = Field(
        default=180,
        ge=0,
        title="【画图】主动画图冷却（分钟）",
        description="两次主动画图之间的建议最小间隔；提示词层约束。",
    )
    draw_proactive_max_per_day: int = Field(
        default=1,
        ge=0,
        title="【画图】主动画图每日上限",
        description="每天最多主动画几张；0 表示不允许主动画。",
    )

    human_search_enabled: bool = Field(
        default=True,
        title="【联网】启用 human_search",
        description="允许 AI 通过 DeepSeek Search 查询实时网页信息；Key 未配置时会明确报错。",
    )
    human_fetch_enabled: bool = Field(
        default=True,
        title="【联网】启用 human_fetch",
        description="允许 AI 抓取网页正文与 B 站评论；关闭后不会调用 human_fetch。",
    )
    human_search_api_key: str = Field(
        default="",
        title="【联网】DeepSeek API Key",
        description="用于 DeepSeek Search/Fetch 的 Bearer Key；留空则联网工具不可用。",
        json_schema_extra=ExtraField(is_secret=True).model_dump(),
    )
    human_search_base_url: str = Field(
        default="https://api.deepseek.com",
        title="【联网】DeepSeek Base URL",
        description="DeepSeek API 地址，默认 https://api.deepseek.com。",
    )
    human_search_max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        title="【联网】默认搜索结果数",
        description="human_search 不传 max_results 时返回的条数，范围 1-10。",
    )
    human_search_timeout_seconds: int = Field(
        default=12,
        ge=3,
        le=60,
        title="【联网】请求超时（秒）",
        description="Search/Fetch 单次请求超时时间。",
    )
    human_search_need_content: bool = Field(
        default=False,
        title="【联网】搜索返回网页正文",
        description="开启后搜索会返回 content，响应更大；一般保持关闭，需要全文时用 human_fetch。",
    )
    human_fetch_max_chars: int = Field(
        default=6000,
        ge=500,
        le=20000,
        title="【联网】抓取正文最大字符数",
        description="human_fetch 返回的 Markdown 正文超过该长度时截断。",
    )
    bili_comments_enabled: bool = Field(
        default=True,
        title="【联网】B站视频自动附带评论",
        description="human_fetch 遇到 B 站视频链接时，直接调用 B 站公开 API 获取标题、简介和热门评论。",
    )
    bili_comments_limit: int = Field(
        default=10,
        ge=0,
        le=20,
        title="【联网】B站评论条数",
        description="自动附带的评论数量；0 表示只返回视频信息，不取评论。",
    )
    bili_comments_sort: str = Field(
        default="hot",
        title="【联网】B站评论排序",
        description="hot=热门，time=最新；其它值按热门处理。",
    )
    link_fetch_enabled: bool = Field(
        default=True,
        title="【联网】上下文链接自动抓取",
        description="允许 AI 根据最近链接上下文判断是否调用 human_fetch；关闭后不会主动提示抓取。",
    )
    link_fetch_probability: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        title="【联网】模糊指代抓取概率",
        description="用户只说“这个/刚才那个”等模糊指代时，本轮允许自动抓取的概率。明确引用不受此限制。",
    )
    link_context_limit: int = Field(
        default=5,
        ge=1,
        le=10,
        title="【联网】最近链接数量",
        description="注入提示词的最近链接候选数量。",
    )
    link_context_max_age_minutes: int = Field(
        default=30,
        ge=1,
        le=240,
        title="【联网】最近链接有效期（分钟）",
        description="超过该时间的链接不再作为自动抓取候选。",
    )
    quoted_link_always_fetch: bool = Field(
        default=True,
        title="【联网】明确引用链接 100% 抓取",
        description="用户引用带链接的消息时，直接允许抓取，不受模糊指代概率影响。",
    )

    bangumi_enabled: bool = Field(
        default=True,
        title="【Bangumi】启用动漫资料查询",
        description="启用 Bangumi 搜索、条目详情、角色和每日放送工具。",
    )
    bangumi_access_token: str = Field(
        default="",
        title="【Bangumi】Access Token",
        description="Bangumi API Access Token；留空仍可匿名查询公开条目，NSFW/部分受限内容不可用。",
        json_schema_extra=ExtraField(is_secret=True).model_dump(),
    )
    bangumi_base_url: str = Field(
        default="https://api.bgm.tv",
        title="【Bangumi】API Base URL",
        description="Bangumi API 地址，默认 https://api.bgm.tv。",
    )
    bangumi_user_agent: str = Field(
        default="humanoid_chat/3.5.0 (Nekro Agent; +https://github.com/nekro-agent/humanoid-chat)",
        title="【Bangumi】User-Agent",
        description="Bangumi 要求带可识别 User-Agent；一般不用改。",
    )
    bangumi_timeout_seconds: int = Field(
        default=12,
        ge=3,
        le=60,
        title="【Bangumi】请求超时（秒）",
        description="Bangumi API 单次请求超时时间。",
    )
    bangumi_search_limit: int = Field(
        default=5,
        ge=1,
        le=10,
        title="【Bangumi】搜索结果数",
        description="默认返回的动漫条目数量。",
    )
    bangumi_character_limit: int = Field(
        default=10,
        ge=1,
        le=20,
        title="【Bangumi】角色结果数",
        description="查询条目角色时默认返回数量。",
    )
    bangumi_calendar_limit: int = Field(
        default=10,
        ge=1,
        le=20,
        title="【Bangumi】每日放送结果数",
        description="查询每日放送时每个星期返回的条目数量。",
    )
    bangumi_include_nsfw: bool = Field(
        default=False,
        title="【Bangumi】包含 NSFW 条目",
        description="需要有效 Access Token；没有权限时 Bangumi 会忽略该选项。",
    )

    # --- 回复方式 ---
    follow_trigger_reply_style: bool = Field(
        default=True,
        title="【回复方式】按触发方式决定首条格式",
        description="总开关：按对方是普通@、引用+@、私聊/叫名字，自动纠正本轮第一条文字的 @ 与引用。",
    )
    at_first_reply_plain: bool = Field(
        default=True,
        title="【回复方式】普通@ → 首条纯文本",
        description="对方只是 @ 你时，第一条回复不 @、不引用，直接说内容。",
    )
    quote_at_first_reply_quote_at: bool = Field(
        default=True,
        title="【回复方式】引用+@ → 首条也引用+@",
        description="对方引用你的消息并 @ 你时，第一条回复 @ 对方并引用刚刚触发的那条消息。",
    )
    non_at_first_reply_plain: bool = Field(
        default=True,
        title="【回复方式】私聊/叫名字/仅引用 → 首条纯文本",
        description="非 @ 触发时，第一条回复不 @、不引用。",
    )
    strip_punctuation: bool = Field(
        default=True,
        title="【回复方式】去掉回复中的标点符号",
        description="发送前自动删除句号、逗号、问号、感叹号、引号、括号等标点；@ 提及、链接、代码和路径会保留。",
    )
    punctuation_chars: str = Field(
        default="。，！？；：、…—～~·,.!?;:'\"()[]{}<>《》〈〉「」『』（）【】“”‘’-/",
        title="【回复方式】要删除的标点字符",
        description="按字符删除，可自行增删；注意不要把 @ 提及、链接和代码里的符号误伤（这些会被保护）。",
    )

    # --- 发送闸门 / 防重复 / 日志 ---
    strict_send_gate: bool = Field(
        default=False,
        title="【闸门】严格拦截无触发记录的群消息",
        description="开启后，群聊里没有唤醒记录的发送会被丢弃。默认关闭，避免误伤命令、定时任务等正常回复。",
    )
    anti_repeat_window: int = Field(
        default=20,
        ge=0,
        title="【防重复】检查最近多少条",
        description="最近发送文本中完全相同的内容会被处理。",
    )
    anti_repeat_action: str = Field(
        default="vary",
        title="【防重复】处理方式",
        description="vary=轻微改写后发送；skip=直接跳过；off=关闭。",
    )
    debug_log: bool = Field(
        default=False,
        title="【调试】详细日志",
        description="打印漏斗判定、延迟、状态更新等详细信息。",
    )


config = plugin.get_config(HumanoidConfig)


def _is_super_user(user_id: str) -> bool:
    if not user_id:
        return False
    try:
        from nekro_agent.core.config import config as core_config

        return str(user_id) in {str(item) for item in getattr(core_config, "SUPER_USERS", [])}
    except Exception:
        return False


class HumanSearchError(RuntimeError):
    pass


def _human_search_base_url() -> str:
    return (config.human_search_base_url or "https://api.deepseek.com").strip().rstrip("/")


def _human_deepseek_post(path: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    api_key = (config.human_search_api_key or "").strip()
    if not api_key:
        raise HumanSearchError("DeepSeek API Key 未配置，请在 humanoid_chat 配置里填写 human_search_api_key。")
    url = f"{_human_search_base_url()}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise HumanSearchError("DeepSeek 返回了非对象 JSON。")
        return parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise HumanSearchError(f"DeepSeek HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise HumanSearchError(f"DeepSeek 请求失败: {exc.reason}") from exc
    except HumanSearchError:
        raise
    except Exception as exc:
        raise HumanSearchError(f"DeepSeek 请求失败: {type(exc).__name__}: {exc}") from exc


def _clip_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _format_human_search_results(query: str, data: Dict[str, Any]) -> str:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return f"联网搜索没有找到 `{query}` 的可用结果。"
    lines = [f"【联网搜索结果】{query}"]
    used = len(lines[0])
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = _clip_text(item.get("title"), 160)
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        summary = _clip_text(
            item.get("summary") or item.get("snippet") or item.get("content"),
            500,
        )
        site = _clip_text(item.get("site_name"), 80)
        date = _clip_text(item.get("date"), 40)
        block = [f"{index}. {title}"]
        if summary:
            block.append(f"   摘要：{summary}")
        meta = " / ".join(part for part in (site, date) if part)
        if meta:
            block.append(f"   来源：{meta}")
        block.append(f"   URL：{url}")
        rendered = "\n".join(block)
        if used + len(rendered) > 6000:
            break
        lines.append(rendered)
        used += len(rendered) + 1
    if len(lines) == 1:
        return f"联网搜索没有找到 `{query}` 的可用结果。"
    return "\n".join(lines)


def _format_human_fetch_result(url: str, data: Dict[str, Any], max_chars: int) -> str:
    title = _clip_text(data.get("title"), 200) or url
    content = str(data.get("content") or "").strip()
    if not content:
        return f"网页抓取没有返回可用正文：{url}"
    if len(content) > max_chars:
        content = content[:max_chars].rstrip() + "\n\n...(已截断)"
    return f"【网页内容】{title}\n来源：{url}\n\n{content}"


class BiliFetchError(RuntimeError):
    pass


_BILI_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
_RE_BILI_BVID = re.compile(r"(BV[0-9A-Za-z]{10})")
_RE_BILI_AVID = re.compile(r"(?:/video/)?av(\d+)", re.IGNORECASE)


def _is_bilibili_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return (
        host == "b23.tv"
        or host.endswith(".b23.tv")
        or host == "bilibili.com"
        or host.endswith(".bilibili.com")
        or host.endswith("bili2233.cn")
    )


def _is_bilibili_video_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host == "b23.tv" or host.endswith(".b23.tv") or host.endswith("bili2233.cn"):
        return True
    if host == "bilibili.com" or host.endswith(".bilibili.com"):
        return bool(_RE_BILI_BVID.search(url) or _RE_BILI_AVID.search(url))
    return False


def _resolve_bili_url(url: str, timeout: int) -> str:
    if "b23.tv" not in urllib.parse.urlparse(url).netloc.lower():
        return url
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _BILI_UA, "Referer": "https://www.bilibili.com/"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.geturl() or url
    except Exception as exc:
        raise BiliFetchError(f"短链解析失败: {type(exc).__name__}: {exc}") from exc


def _bili_api_json(path: str, params: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://api.bilibili.com{path}?{query}",
        headers={
            "User-Agent": _BILI_UA,
            "Referer": "https://www.bilibili.com/",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
        parsed = json.loads(body)
    except Exception as exc:
        raise BiliFetchError(f"B站 API 请求失败: {type(exc).__name__}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BiliFetchError("B站 API 返回了非对象 JSON。")
    code = parsed.get("code")
    if code != 0:
        raise BiliFetchError(f"B站 API 错误 {code}: {parsed.get('message') or 'unknown'}")
    data = parsed.get("data")
    if not isinstance(data, dict):
        raise BiliFetchError("B站 API 没有返回 data。")
    return data


def _extract_bili_identity(url: str, timeout: int) -> Tuple[str, Dict[str, Any]]:
    resolved = _resolve_bili_url(url, timeout)
    match = _RE_BILI_BVID.search(resolved) or _RE_BILI_BVID.search(url)
    if match:
        return resolved, {"bvid": match.group(1)}
    match = _RE_BILI_AVID.search(resolved) or _RE_BILI_AVID.search(url)
    if match:
        return resolved, {"aid": int(match.group(1))}
    raise BiliFetchError("无法从链接中识别 BV/av 号。")


def _fetch_bili_bundle(
    url: str,
    comment_limit: int,
    comment_sort: str,
    timeout: int,
) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], str]:
    resolved, identity = _extract_bili_identity(url, timeout)
    info = _bili_api_json("/x/web-interface/view", identity, timeout)
    bvid = str(info.get("bvid") or "").strip()
    aid = info.get("aid")
    canonical = f"https://www.bilibili.com/video/{bvid}/" if bvid else resolved
    comments: List[Dict[str, Any]] = []
    comment_error = ""
    if comment_limit > 0:
        if aid:
            sort = 0 if comment_sort.strip().lower() == "time" else 2
            try:
                reply_data = _bili_api_json(
                    "/x/v2/reply",
                    {"type": 1, "oid": int(aid), "pn": 1, "ps": comment_limit, "sort": sort},
                    timeout,
                )
                raw_replies = reply_data.get("replies")
                if isinstance(raw_replies, list):
                    comments = [item for item in raw_replies if isinstance(item, dict)]
            except BiliFetchError as exc:
                comment_error = str(exc)
        else:
            comment_error = "视频信息里没有 aid，无法读取评论。"
    return canonical, info, comments, comment_error


def _format_bili_fetch(
    url: str,
    info: Dict[str, Any],
    comments: List[Dict[str, Any]],
    comment_error: str,
    comment_limit: int,
    max_chars: int,
) -> str:
    title = _clip_text(info.get("title"), 200) or "B站视频"
    owner = info.get("owner") if isinstance(info.get("owner"), dict) else {}
    stat = info.get("stat") if isinstance(info.get("stat"), dict) else {}
    desc = _clip_text(info.get("desc"), 500)
    lines = [
        f"【网页内容】{title}",
        f"来源：{url}",
        f"UP主：{_clip_text(owner.get('name'), 80) or '未知'}",
        (
            f"播放：{stat.get('view', 0)} / 点赞：{stat.get('like', 0)} / "
            f"评论：{stat.get('reply', 0)} / 弹幕：{stat.get('danmaku', 0)}"
        ),
    ]
    if desc:
        lines.append(f"简介：{desc}")
    if comment_limit > 0:
        if comments:
            lines.append("")
            lines.append("【热门评论】")
            for index, reply in enumerate(comments[:comment_limit], start=1):
                member = reply.get("member") if isinstance(reply.get("member"), dict) else {}
                content = reply.get("content") if isinstance(reply.get("content"), dict) else {}
                message = _clip_text(content.get("message"), 300)
                if not message:
                    continue
                suffix = f"，回复 {reply.get('rcount')}" if reply.get("rcount") else ""
                lines.append(
                    f"{index}. {_clip_text(member.get('uname'), 60) or '匿名'}（赞 {reply.get('like', 0)}{suffix}）：{message}"
                )
        elif comment_error:
            lines.append("")
            lines.append(f"评论读取失败：{comment_error}")
        else:
            lines.append("")
            lines.append("暂无可见评论。")
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars].rstrip() + "\n\n...(已截断)"
    return result


class BangumiError(RuntimeError):
    pass


def _bangumi_request(
    path: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
) -> Any:
    base_url = (config.bangumi_base_url or "https://api.bgm.tv").strip().rstrip("/")
    query = urllib.parse.urlencode(params or {})
    url = f"{base_url}{path}" + (f"?{query}" if query else "")
    headers = {
        "User-Agent": (config.bangumi_user_agent or "humanoid_chat/3.5.0").strip(),
        "Accept": "application/json",
    }
    token = (config.bangumi_access_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout or int(config.bangumi_timeout_seconds)) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise BangumiError(f"Bangumi HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise BangumiError(f"Bangumi 请求失败: {exc.reason}") from exc
    except Exception as exc:
        raise BangumiError(f"Bangumi 请求失败: {type(exc).__name__}: {exc}") from exc


def _bangumi_subject_title(subject: Dict[str, Any]) -> str:
    name_cn = str(subject.get("name_cn") or "").strip()
    name = str(subject.get("name") or "").strip()
    if name_cn and name and name_cn != name:
        return f"{name_cn} / {name}"
    return name_cn or name or "未知条目"


def _bangumi_rating_text(subject: Dict[str, Any]) -> str:
    rating = subject.get("rating") if isinstance(subject.get("rating"), dict) else {}
    score = rating.get("score")
    total = rating.get("total")
    rank = rating.get("rank")
    if score is None:
        return "暂无评分"
    text = f"{score} 分"
    if total:
        text += f"（{total} 人评分"
        if rank:
            text += f"，排名 {rank}"
        text += "）"
    elif rank:
        text += f"（排名 {rank}）"
    return text


def _format_bangumi_search(keyword: str, data: Dict[str, Any]) -> str:
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return f"Bangumi 没有找到 `{keyword}` 的动画条目。"
    lines = [f"【Bangumi 动漫搜索】{keyword}"]
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        title = _bangumi_subject_title(item)
        meta = [
            part
            for part in (
                f"ID {item.get('id')}" if item.get("id") else "",
                str(item.get("platform") or "").strip(),
                str(item.get("date") or "").strip(),
                f"{item.get('eps')} 话" if item.get("eps") else "",
                _bangumi_rating_text(item),
            )
            if part
        ]
        lines.append(f"{index}. 《{title}》")
        if meta:
            lines.append("   " + " ｜ ".join(meta))
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        tag_text = "、".join(str(tag.get("name") or "").strip() for tag in tags[:6] if isinstance(tag, dict) and tag.get("name"))
        if tag_text:
            lines.append(f"   标签：{tag_text}")
        summary = _clip_text(item.get("summary"), 260)
        if summary:
            lines.append(f"   简介：{summary}")
    return "\n".join(lines)


def _format_bangumi_subject(subject: Dict[str, Any]) -> str:
    title = _bangumi_subject_title(subject)
    meta = [
        part
        for part in (
            f"ID {subject.get('id')}" if subject.get("id") else "",
            str(subject.get("platform") or "").strip(),
            str(subject.get("date") or "").strip(),
            f"{subject.get('eps')} 话" if subject.get("eps") else "",
            _bangumi_rating_text(subject),
        )
        if part
    ]
    lines = [f"【Bangumi 条目】{title}"]
    if meta:
        lines.append(" ｜ ".join(meta))
    tags = subject.get("tags") if isinstance(subject.get("tags"), list) else []
    tag_text = "、".join(str(tag.get("name") or "").strip() for tag in tags[:12] if isinstance(tag, dict) and tag.get("name"))
    if tag_text:
        lines.append(f"标签：{tag_text}")
    summary = _clip_text(subject.get("summary"), 800)
    if summary:
        lines.append(f"简介：{summary}")
    return "\n".join(lines)


def _format_bangumi_characters(subject_id: int, characters: List[Dict[str, Any]]) -> str:
    if not characters:
        return f"Bangumi 条目 {subject_id} 没有返回角色信息。"
    lines = [f"【Bangumi 角色】条目 {subject_id}"]
    for index, item in enumerate(characters, start=1):
        if not isinstance(item, dict):
            continue
        name = _clip_text(item.get("name"), 80) or "未知角色"
        relation = _clip_text(item.get("relation"), 40)
        actors = item.get("actors") if isinstance(item.get("actors"), list) else []
        actor_text = "、".join(
            _clip_text(actor.get("name"), 60)
            for actor in actors
            if isinstance(actor, dict) and actor.get("name")
        )
        line = f"{index}. {name}"
        if relation:
            line += f"（{relation}）"
        if actor_text:
            line += f"：CV {actor_text}"
        lines.append(line)
    return "\n".join(lines)


def _bangumi_weekday_number(value: Any) -> int:
    text = str(value or "").strip().lower()
    if not text or text in {"today", "今天", "今日"}:
        return _local_now().isoweekday()
    mapping = {
        "mon": 1, "monday": 1, "周一": 1, "星期一": 1, "1": 1,
        "tue": 2, "tuesday": 2, "周二": 2, "星期二": 2, "2": 2,
        "wed": 3, "wednesday": 3, "周三": 3, "星期三": 3, "3": 3,
        "thu": 4, "thursday": 4, "周四": 4, "星期四": 4, "4": 4,
        "fri": 5, "friday": 5, "周五": 5, "星期五": 5, "5": 5,
        "sat": 6, "saturday": 6, "周六": 6, "星期六": 6, "6": 6,
        "sun": 7, "sunday": 7, "周日": 7, "周天": 7, "星期日": 7, "星期天": 7, "7": 7,
    }
    return mapping.get(text, _local_now().isoweekday())


def _format_bangumi_calendar(weekday: int, items: List[Dict[str, Any]]) -> str:
    labels = {1: "星期一", 2: "星期二", 3: "星期三", 4: "星期四", 5: "星期五", 6: "星期六", 7: "星期日"}
    if not items:
        return f"Bangumi 的{labels.get(weekday, '今天')}没有放送条目。"
    lines = [f"【Bangumi 每日放送】{labels.get(weekday, '今天')}"]
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        title = _bangumi_subject_title(item)
        date = str(item.get("air_date") or "").strip()
        suffix = f"（{date}）" if date else ""
        lines.append(f"{index}. 《{title}》{suffix}")
    return "\n".join(lines)


def _normalize_quoted_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host == "b23.tv" or host.endswith(".b23.tv"):
        path = parsed.path.strip("/")
        return f"https://b23.tv/{path}" if path else url
    if host == "bilibili.com" or host.endswith(".bilibili.com"):
        match = _RE_BILI_BVID.search(url)
        if match:
            return f"https://www.bilibili.com/video/{match.group(1)}/"
    return url


def _quoted_message_info(message: DBChatMessage) -> Tuple[str, str, str, List[str]]:
    summary = str(message.content_text or "").strip()
    urls: List[str] = []
    image_refs: List[str] = []
    has_image = summary.startswith("[Image:")
    has_card = summary.startswith("[卡片消息]") or "卡片消息" in summary
    try:
        content_data = json.loads(message.content_data or "[]")
    except Exception:
        content_data = []
    if isinstance(content_data, list):
        for segment in content_data:
            if not isinstance(segment, dict):
                continue
            seg_type = str(segment.get("type") or "").lower()
            if seg_type == "json_card":
                has_card = True
            if seg_type == "image":
                has_image = True
                file_name = str(segment.get("file_name") or "").strip()
                local_path = str(segment.get("local_path") or "").strip()
                remote_url = str(segment.get("remote_url") or "").strip()
                if file_name:
                    image_refs.append(f"/app/uploads/{Path(file_name).name}")
                elif local_path:
                    image_refs.append(f"/app/uploads/{Path(local_path).name}")
                elif remote_url:
                    image_refs.append(remote_url)
            desc = str(segment.get("card_desc") or "").strip()
            if desc:
                summary = desc
            card_url = str(segment.get("card_url") or "").strip()
            if card_url:
                urls.append(card_url)
            json_data = segment.get("json_data")
            if isinstance(json_data, dict):
                meta = json_data.get("meta")
                if isinstance(meta, dict):
                    detail = meta.get("detail_1")
                    if isinstance(detail, dict):
                        for key in ("qqdocurl", "url"):
                            value = str(detail.get(key) or "").strip()
                            if value:
                                urls.append(value)
    if not urls:
        urls.extend(re.findall(r"https?://[^\s\"'<>]+", summary))
    normalized = [_normalize_quoted_url(url) for url in urls if url]
    bili_urls = [url for url in normalized if _is_bilibili_url(url)]
    chosen = bili_urls[0] if bili_urls else (normalized[0] if normalized else "")
    if chosen:
        kind = "link"
    elif has_image:
        kind = "image"
    elif has_card:
        kind = "card"
    else:
        kind = "text"
    if kind == "image" and summary.startswith("[Image:"):
        summary = "（一张图片）"
    return _clip_text(summary, 400), chosen, kind, list(dict.fromkeys(image_refs))


def _quoted_no_link_reply(summary: str) -> str:
    text = str(summary or "").strip()
    title_match = re.search(r'标题为["“](.+?)["”]', text)
    if title_match:
        title = _clip_text(title_match.group(1), 60)
    else:
        title = _clip_text(text, 60)
    if "卡片消息" in text:
        return f"这条卡片只写了「{title}」，没带链接，我确认不了是什么。"
    if title:
        return f"你引用的是「{title}」，没有链接内容，我不确定你指什么。"
    return "你引用的消息没有链接内容，我不确定你指什么。"


async def _load_quoted_message(
    chat_key: str,
    trigger_msg_id: str,
) -> Optional[Tuple[str, str, str, str, List[str]]]:
    if not chat_key or not trigger_msg_id:
        return None
    current = await DBChatMessage.filter(
        chat_key=chat_key,
        message_id=str(trigger_msg_id),
    ).order_by("-id").first()
    if not current:
        return None
    ref_id = str(getattr(current.ext_data_obj, "ref_msg_id", "") or "").strip()
    if not ref_id:
        return None
    quoted = await DBChatMessage.filter(
        chat_key=chat_key,
        message_id=ref_id,
    ).order_by("-id").first()
    if not quoted:
        return None
    summary, url, kind, image_refs = _quoted_message_info(quoted)
    sender = str(quoted.sender_nickname or quoted.sender_name or "").strip()
    return sender or "某人", summary, url, kind, image_refs


async def _quoted_image_visible(chat_key: str, image_refs: List[str]) -> bool:
    if not image_refs:
        return False
    try:
        from nekro_agent.core.config import config as core_config

        image_limit = max(1, int(getattr(core_config, "AI_VISION_IMAGE_LIMIT", 5)))
    except Exception:
        image_limit = 5
    targets: Set[str] = set()
    for ref in image_refs:
        text = str(ref or "").strip()
        if not text:
            continue
        targets.add(text if text.startswith(("http://", "https://")) else Path(text).name)
    if not targets:
        return False
    messages = await DBChatMessage.filter(
        chat_key=chat_key,
        is_recalled=False,
    ).order_by("-send_timestamp").limit(80).all()
    seen: Set[str] = set()
    for message in messages:
        try:
            content_data = json.loads(message.content_data or "[]")
        except Exception:
            continue
        if not isinstance(content_data, list):
            continue
        for segment in reversed(content_data):
            if not isinstance(segment, dict):
                continue
            if str(segment.get("type") or "").lower() != "image":
                continue
            file_name = str(segment.get("file_name") or "").strip()
            local_path = str(segment.get("local_path") or "").strip()
            remote_url = str(segment.get("remote_url") or "").strip()
            key = file_name or (Path(local_path).name if local_path else remote_url)
            if not key or key in seen:
                continue
            seen.add(key)
            if key in targets:
                return True
            if len(seen) >= image_limit:
                return False
    return False


_RE_LINK_URL = re.compile(r"https?://[^\s\"'<>\\]+", re.IGNORECASE)
_LOW_VALUE_LINK_HOSTS = (
    "multimedia.nt.qq.com.cn",
    "gchat.qpic.cn",
    "qq.ugcimg.cn",
    "miniapp.gtimg.cn",
    "m.q.qq.com",
    "i0.hdslb.com",
    "i1.hdslb.com",
    "i2.hdslb.com",
)
_LINK_REFERENCE_WORDS = (
    "看评论",
    "评论区",
    "这个链接",
    "这个视频",
    "看看这个",
    "上面的链接",
    "刚才那个",
    "刚才的链接",
)


def _is_low_value_link(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(host == item or host.endswith(f".{item}") for item in _LOW_VALUE_LINK_HOSTS)


def _record_recent_links(
    chat_key: str,
    raw_text: str,
    user_id: str,
    nickname: str,
    msg_id: str,
) -> None:
    source = str(raw_text or "").replace("\\/", "/")
    raw_urls = _RE_LINK_URL.findall(source)
    if not raw_urls:
        return
    links = _RECENT_LINKS.setdefault(chat_key, deque(maxlen=16))
    now = _now()
    seen: Set[str] = set()
    for raw_url in raw_urls:
        url = _normalize_quoted_url(raw_url.rstrip(".,;，。)]}"))
        if not url.startswith("http") or _is_low_value_link(url) or url in seen:
            continue
        seen.add(url)
        kept = [item for item in links if item.get("url") != url]
        links.clear()
        links.extend(kept)
        title_text = source.replace(raw_url, "")
        for pattern in (
            r'"标题"\s*:\s*"([^"]+)"',
            r'"desc"\s*:\s*"([^"]+)"',
            r'"prompt"\s*:\s*"([^"]+)"',
        ):
            match = re.search(pattern, title_text)
            if match:
                title_text = match.group(1)
                break
        if title_text.lstrip().startswith(("{", "[")):
            title_text = ""
        links.append(
            {
                "ts": now,
                "url": url,
                "sender_id": str(user_id or ""),
                "nickname": nickname or "",
                "msg_id": str(msg_id or ""),
                "title": _clip_text(title_text, 100),
            }
        )


def _get_recent_links(chat_key: str) -> List[Dict[str, Any]]:
    links = _RECENT_LINKS.get(chat_key)
    if not links:
        return []
    now = _now()
    max_age = max(1, int(config.link_context_max_age_minutes)) * 60
    fresh = [item for item in links if now - float(item.get("ts") or 0) <= max_age]
    return fresh[-max(1, int(config.link_context_limit)):]


def _is_explicit_link_reference(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(word in lowered for word in _LINK_REFERENCE_WORDS)


def _should_block_context_fetch(chat_key: str, url: str) -> bool:
    cache = _TRIGGER_CACHE.get(chat_key, {})
    if cache.get("link_fetch_mode") not in {"vague", "quoted"}:
        return False
    if cache.get("link_fetch_allow"):
        return False
    requested = _normalize_quoted_url(url)
    context_urls = {
        _normalize_quoted_url(item)
        for item in (cache.get("link_context_urls") or [])
        if item
    }
    if requested not in context_urls:
        return False
    current_text = _LAST_INBOUND_TEXT.get(chat_key, "").replace("\\/", "/")
    current_urls = {
        _normalize_quoted_url(item.rstrip(".,;，。)]}"))
        for item in _RE_LINK_URL.findall(current_text)
        if item
    }
    return requested not in current_urls


# ============================================================
# 3. 本群档案模型
# ============================================================


class GroupPerson(BaseModel):
    name: str = ""
    qq: str = ""
    aliases: List[str] = Field(default_factory=list)
    note: str = ""
    description: str = ""


class GroupRule(BaseModel):
    text: str = ""
    action: str = "remind"
    duration: int = 0


class GroupAdminPolicy(BaseModel):
    enabled: bool = True
    direct_actions: List[str] = Field(default_factory=lambda: ["mute", "recall"])
    observe_actions: List[str] = Field(default_factory=lambda: ["kick"])
    protected: List[str] = Field(default_factory=lambda: ["owner", "admins", "self"])
    protected_extra: List[str] = Field(default_factory=list)
    max_mute_seconds: int = 600
    cooldown_seconds: int = 60


class GroupProfile(BaseModel):
    description: str = ""
    enabled: bool = True
    role: str = "auto"
    owner: Optional[GroupPerson] = None
    admins: List[GroupPerson] = Field(default_factory=list)
    members: List[GroupPerson] = Field(default_factory=list)
    rules: List[GroupRule] = Field(default_factory=list)
    culture: str = ""
    tone: str = ""
    activity: str = ""
    admin_policy: GroupAdminPolicy = Field(default_factory=GroupAdminPolicy)


GroupPerson.model_rebuild()
GroupRule.model_rebuild()
GroupAdminPolicy.model_rebuild()
GroupProfile.model_rebuild(force=True)


# ============================================================
# 4. 运行时状态
# ============================================================

STORE_CHAT_STATE = "humanoid_state"
STORE_USER_STATE = "humanoid_user_state"
STORE_LOOP_STATUS = "humanoid_loop_status"

_TRIGGER_CACHE: Dict[str, Dict[str, Any]] = {}
_BOT_NAMES_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_UNMENTIONED_REPLY: Dict[str, float] = {}
_PROCESSED_MSG_IDS: Set[str] = set()
_GROUP_ACTIVITY: Dict[str, Deque[float]] = {}
_LAST_INBOUND_TS: Dict[str, float] = {}
_LAST_INBOUND_MSG_ID: Dict[str, Tuple[float, str]] = {}
_LAST_INBOUND_TEXT: Dict[str, str] = {}
_RECENT_SENT: Dict[str, Deque[str]] = {}
_RECENT_LINKS: Dict[str, Deque[Dict[str, Any]]] = {}
_SEND_LOCKS: Dict[str, asyncio.Lock] = {}
_BG_TASKS: Dict[str, asyncio.Task] = {}
_LAST_MEDIA_SENT: Dict[str, float] = {}
_LAST_STICKER_HINT: Dict[str, float] = {}
_GROUP_PROFILE_CACHE: Dict[str, Tuple[float, GroupProfile]] = {}
_BOT_ROLE_CACHE: Dict[str, Tuple[float, str]] = {}

MOOD_WORDS_POSITIVE = (
    "谢谢", "喜欢", "可爱", "厉害", "好棒", "辛苦", "哈哈", "爱你", "牛", "赞", "开心", "有意思",
    "高兴", "好玩", "笑", "嘿嘿", "好耶", "太棒", "温柔", "体贴", "舒服", "轻松", "元气", "期待", "兴奋",
)
MOOD_WORDS_NEGATIVE = (
    "滚", "烦", "闭嘴", "傻", "笨", "讨厌", "别说了", "垃圾", "无聊", "恶心", "生气",
    "难过", "哭", "呜呜", "无语", "离谱", "可恶", "不要", "怎么才", "不满", "敷衍",
)
MOOD_EMOJI_POSITIVE = ("😊", "😄", "😆", "🥰", "😍", "👍", "❤️", "✨", "🎉", "🤣")
MOOD_EMOJI_NEGATIVE = ("😡", "😠", "💢", "😞", "😢", "🙄", "😑", "🤬")


def _mood_delta_from_text(text: str) -> float:
    lowered = (text or "").lower()
    positive = sum(1 for word in MOOD_WORDS_POSITIVE if word in lowered)
    negative = sum(1 for word in MOOD_WORDS_NEGATIVE if word in lowered)
    positive += sum(text.count(emoji) for emoji in MOOD_EMOJI_POSITIVE)
    negative += sum(text.count(emoji) for emoji in MOOD_EMOJI_NEGATIVE)
    return _clamp((positive - negative) * 3.0, -9.0, 9.0)


def _log(level: str, text: str) -> None:
    cfg = config
    if not cfg.debug_log and level == "debug":
        return
    logger = plugin.logger
    if level == "debug":
        logger.debug(f"[humanoid_chat #{INSTANCE_ID}] {text}")
    elif level == "warning":
        logger.warning(f"[humanoid_chat #{INSTANCE_ID}] {text}")
    elif level == "error":
        logger.error(f"[humanoid_chat #{INSTANCE_ID}] {text}")
    else:
        logger.info(f"[humanoid_chat #{INSTANCE_ID}] {text}")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in re.split(r"[,，|/、\s]+", value or "") if item.strip()]


def _now() -> float:
    return time.time()


def _today_str() -> str:
    return _local_now().strftime("%Y-%m-%d")


def _local_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(config.timezone))
    except Exception:
        return datetime.now()


def _parse_hhmm(value: str, fallback: Tuple[int, int]) -> Tuple[int, int]:
    try:
        hour, minute = value.strip().split(":", 1)
        return int(hour), int(minute)
    except Exception:
        return fallback


def _is_night() -> bool:
    now = _local_now()
    start_h, start_m = _parse_hhmm(config.night_start, (23, 30))
    end_h, end_m = _parse_hhmm(config.night_end, (7, 30))
    current = now.hour * 60 + now.minute
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _night_factor_delay() -> float:
    return config.night_delay_multiplier if _is_night() else 1.0


def _night_factor_reply() -> float:
    return config.night_reply_multiplier if _is_night() else 1.0


async def _store_get_dict(chat_key: str = "", user_key: str = "", store_key: str = "") -> Dict[str, Any]:
    try:
        raw = await plugin.store.get(chat_key=chat_key, user_key=user_key, store_key=store_key)
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        _log("debug", f"读取状态失败 {store_key}: {exc}")
        return {}


async def _store_set_dict(value: Dict[str, Any], chat_key: str = "", user_key: str = "", store_key: str = "") -> None:
    try:
        await plugin.store.set(
            chat_key=chat_key,
            user_key=user_key,
            store_key=store_key,
            value=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        )
    except Exception as exc:
        _log("warning", f"写入状态失败 {store_key}: {exc}")


def _default_chat_state() -> Dict[str, Any]:
    return {
        "valence": float(config.mood_baseline),
        "energy": float(config.energy_start),
        "patience": float(config.patience_start),
        "last_update": _now(),
        "last_bot_msg": 0.0,
        "last_user_msg": 0.0,
        "ignored_streak": 0,
        "ignored_marked_for": 0.0,
        "proactive_date": "",
        "proactive_count": 0,
        "last_proactive": 0.0,
        "recent_topics": [],
        "bot_msg_count": 0,
    }


async def _load_chat_state(chat_key: str) -> Dict[str, Any]:
    state = await _store_get_dict(chat_key=chat_key, store_key=STORE_CHAT_STATE)
    merged = _default_chat_state()
    merged.update(state or {})
    now = _now()
    last_update = float(merged.get("last_update") or now)
    hours = max(0.0, (now - last_update) / 3600.0)
    if hours > 0:
        recover = config.energy_recover_night_per_hour if _is_night() else config.energy_recover_day_per_hour
        if config.energy_enabled:
            merged["energy"] = _clamp(float(merged.get("energy", config.energy_start)) + recover * hours, 0, 100)
        baseline = float(config.mood_baseline)
        decay = min(1.0, hours / max(0.1, config.mood_decay_hours))
        merged["valence"] = _clamp(float(merged.get("valence", baseline)) + (baseline - float(merged.get("valence", baseline))) * decay, 0, 100)
        merged["patience"] = _clamp(float(merged.get("patience", config.patience_start)) + config.patience_recover_per_hour * hours, 0, 100)
        merged["last_update"] = now
    return merged


async def _save_chat_state(chat_key: str, state: Dict[str, Any]) -> None:
    state["last_update"] = _now()
    await _store_set_dict(state, chat_key=chat_key, store_key=STORE_CHAT_STATE)


def _default_user_state() -> Dict[str, Any]:
    return {
        "familiarity": 0.0,
        "interactions": 0,
        "last_seen": 0.0,
        "last_msg_ts": 0.0,
        "rapid_streak": 0,
        "nickname": "",
        "memories": [],
    }


async def _load_user_state(chat_key: str, user_key: str) -> Dict[str, Any]:
    state = await _store_get_dict(chat_key=chat_key, user_key=user_key, store_key=STORE_USER_STATE)
    merged = _default_user_state()
    merged.update(state or {})
    return merged


async def _save_user_state(chat_key: str, user_key: str, state: Dict[str, Any]) -> None:
    memories = state.get("memories")
    if not isinstance(memories, list):
        memories = []
    state["memories"] = memories[-max(0, config.memory_limit):]
    await _store_set_dict(state, chat_key=chat_key, user_key=user_key, store_key=STORE_USER_STATE)


def _is_direct_chat(chat_key: str, cache: Optional[Dict[str, Any]] = None) -> bool:
    if "private" in chat_key.lower():
        return True
    if cache and _now() - float(cache.get("time", 0)) < 300:
        return bool(cache.get("is_direct"))
    return False


def _classify_mention(raw_msg: str, is_to_me: bool, self_id: str, group_id: Any) -> str:
    """区分普通 @、引用+@、私聊，用于决定本轮首条回复格式。"""
    if not group_id:
        return "private"
    has_reply = bool(re.search(r"\[CQ:reply(?:,|\])", raw_msg, re.IGNORECASE))
    has_at_me = bool(
        self_id
        and (
            re.search(rf"\[CQ:at,qq={re.escape(self_id)}(?:,|\])", raw_msg, re.IGNORECASE)
            or f"[@id:{self_id}" in raw_msg
        )
    )
    if has_reply and (has_at_me or is_to_me):
        return "quote_at"
    if has_at_me or is_to_me:
        return "at"
    return "other"


def _new_trigger_cache(
    *,
    is_direct: bool,
    proactive: bool,
    reason: str,
    sender_id: Optional[str],
    msg_id: Optional[str],
    mention_type: Optional[str],
) -> Dict[str, Any]:
    return {
        "is_direct": is_direct,
        "proactive": proactive,
        "reason": reason,
        "time": _now(),
        "sender_id": sender_id,
        "msg_id": msg_id,
        "mention_type": mention_type,
        "first_reply_done": False,
    }


async def _touch_user_state(chat_key: str, user_id: str, text: str, nickname: str = "") -> None:
    cfg = config
    state = await _load_chat_state(chat_key)
    user_state = await _load_user_state(chat_key, user_id)
    now = _now()

    last_msg = float(user_state.get("last_msg_ts") or 0)
    rapid = now - last_msg <= cfg.rapid_message_window if last_msg else False
    user_state["rapid_streak"] = int(user_state.get("rapid_streak") or 0) + 1 if rapid else 0
    user_state["last_msg_ts"] = now
    user_state["last_seen"] = now
    user_state["interactions"] = int(user_state.get("interactions") or 0) + 1
    if nickname:
        user_state["nickname"] = nickname[:32]

    if cfg.familiarity_enabled:
        gain = cfg.familiarity_gain / (1.0 + max(0, int(user_state["rapid_streak"]) - 1) * 0.6)
        user_state["familiarity"] = _clamp(float(user_state.get("familiarity") or 0.0) + gain, 0, cfg.familiarity_max)

    if user_state["rapid_streak"] > 2:
        state["patience"] = _clamp(float(state.get("patience", cfg.patience_start)) - cfg.rapid_patience_cost, 0, 100)

    mood_delta = _mood_delta_from_text(text)
    if mood_delta:
        state["valence"] = _clamp(float(state.get("valence", cfg.mood_baseline)) + mood_delta, 0, 100)

    if state.get("last_bot_msg") and now - float(state["last_bot_msg"]) < 300:
        state["ignored_streak"] = 0

    topics = state.get("recent_topics")
    if not isinstance(topics, list):
        topics = []
    topics.append({"t": now, "u": user_id, "text": text[:80]})
    state["recent_topics"] = topics[-12:]
    state["last_user_msg"] = now

    await _save_chat_state(chat_key, state)
    await _save_user_state(chat_key, user_id, user_state)


async def _note_bot_send(chat_key: str, text: str) -> None:
    state = await _load_chat_state(chat_key)
    state["last_bot_msg"] = _now()
    state["bot_msg_count"] = int(state.get("bot_msg_count") or 0) + 1
    if config.energy_enabled:
        state["energy"] = _clamp(float(state.get("energy", config.energy_start)) - config.energy_cost_per_message, 0, 100)
    mood_delta = _mood_delta_from_text(text)
    if mood_delta:
        state["valence"] = _clamp(float(state.get("valence", config.mood_baseline)) + mood_delta * 0.6, 0, 100)
    await _save_chat_state(chat_key, state)

    recent = _RECENT_SENT.setdefault(chat_key, deque(maxlen=max(1, config.anti_repeat_window)))
    recent.append(_normalize_for_repeat(text))


def _normalize_for_repeat(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def _energy_delay_factor(state: Dict[str, Any]) -> float:
    if not config.energy_enabled:
        return 1.0
    if float(state.get("energy", 100)) < config.low_energy_threshold:
        return config.low_energy_delay_multiplier
    return 1.0


def _energy_reply_factor(state: Dict[str, Any]) -> float:
    if not config.energy_enabled:
        return 1.0
    if float(state.get("energy", 100)) < config.low_energy_threshold:
        return config.low_energy_reply_multiplier
    return 1.0


def _patience_reply_factor(state: Dict[str, Any]) -> float:
    patience = float(state.get("patience", config.patience_start))
    return _clamp(0.35 + patience / 100.0 * 0.75, 0.35, 1.1)


# ============================================================
# 3.1 本群档案加载与角色识别
# ============================================================


def _group_profile_root() -> Path:
    configured = (config.group_profile_dir or "").strip()
    if configured:
        return Path(configured)
    return plugin.get_plugin_data_dir() / "group_profiles"


def _load_group_profile(chat_key: str) -> Optional[GroupProfile]:
    if not config.group_profile_enabled:
        return None
    path = _group_profile_root() / f"{chat_key}.yaml"
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _GROUP_PROFILE_CACHE.pop(chat_key, None)
        return None
    cached = _GROUP_PROFILE_CACHE.get(chat_key)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("YAML 顶层必须是对象")
        profile = GroupProfile.model_validate(raw)
        _GROUP_PROFILE_CACHE[chat_key] = (mtime, profile)
        if config.debug_log:
            _log(
                "info",
                f"本群档案加载: {chat_key} role={profile.role} "
                f"rules={len(profile.rules)} admins={len(profile.admins)} members={len(profile.members)}",
            )
        return profile
    except Exception as exc:
        _log("warning", f"本群档案加载失败 {path}: {exc}")
        return None


def _role_label(role: str) -> str:
    return {"owner": "群主", "admin": "管理员", "member": "普通成员"}.get(role, "未知")


def _profile_role(profile: GroupProfile) -> str:
    value = (profile.role or "auto").strip().lower()
    return value if value in ("owner", "admin", "member") else "auto"


async def _detect_bot_role(_ctx: AgentCtx, chat_key: str) -> str:
    if _ctx.adapter_key != "onebot_v11" or _ctx.channel_type != "group":
        return "member"
    now = _now()
    ttl = max(1, config.group_role_cache_minutes) * 60
    cached = _BOT_ROLE_CACHE.get(chat_key)
    if cached and now - cached[0] < ttl:
        return cached[1]

    role = "unknown"
    try:
        raw_group_id = str(_ctx.channel_id or "")
        group_id = raw_group_id.replace("group_", "", 1)
        if not group_id.isdigit() and "group_" in chat_key:
            group_id = chat_key.split("group_", 1)[-1]
        if group_id.isdigit():
            bot = await _ctx.get_onebot_v11_bot()
            info = await bot.get_group_member_info(
                group_id=int(group_id),
                user_id=int(bot.self_id),
                no_cache=False,
            )
            role = str(info.get("role") or "member")
    except Exception as exc:
        _log("debug", f"自动识别本群角色失败: {chat_key}: {exc}")

    _BOT_ROLE_CACHE[chat_key] = (now, role)
    if config.debug_log:
        _log("info", f"本群角色识别: {chat_key} role={role}")
    return role


def _format_person(person: GroupPerson) -> str:
    name = (person.name or person.qq or "未知").strip()
    meta: List[str] = []
    if person.qq.strip():
        meta.append(f"QQ:{person.qq.strip()}")
    aliases = [a.strip() for a in person.aliases if a and a.strip()]
    if aliases:
        meta.append("别名:" + "/".join(aliases[:3]))
    text = f"{name}（{'，'.join(meta)}）" if meta else name
    detail = person.description.strip() or person.note.strip()
    if detail:
        text += f"：{detail}"
    return text


def _rule_action_label(rule: GroupRule, default_mute: int) -> str:
    action = (rule.action or "remind").strip().lower()
    if action == "recall":
        return "撤回"
    if action == "mute":
        duration = rule.duration or default_mute
        return f"禁言 {duration} 秒"
    if action == "recall_and_mute":
        duration = rule.duration or default_mute
        return f"撤回并禁言 {duration} 秒"
    if action == "recall_and_kick":
        return "撤回并踢出"
    if action == "observe_kick":
        return "记录并报告（不实际踢人）"
    return "提醒"


def _render_group_profile(
    profile: GroupProfile,
    profile_role: str,
    actual_role: str,
    chat_key: str,
) -> str:
    policy = profile.admin_policy
    default_mute = max(1, policy.max_mute_seconds)
    can_enforce = policy.enabled and actual_role in ("owner", "admin")

    lines: List[str] = ["======【本群档案】======"]
    if profile.description.strip():
        lines.append(f"· 群描述：{profile.description.strip()}")
    if profile_role != "auto":
        lines.append(f"· 档案角色：{_role_label(profile_role)}")
    lines.append(f"· 平台实际权限：{_role_label(actual_role)}")
    if profile_role != "auto" and actual_role not in ("unknown", profile_role):
        lines.append("· 档案角色与平台实际角色不一致：权限以平台实际角色为准。")

    if profile.owner:
        lines.append(f"· 群主：{_format_person(profile.owner)}")
    if profile.admins:
        rendered = "；".join(_format_person(p) for p in profile.admins[:8])
        more = f"；等 {len(profile.admins)} 人" if len(profile.admins) > 8 else ""
        lines.append(f"· 管理员：{rendered}{more}")
    if profile.members:
        rendered = "；".join(_format_person(p) for p in profile.members[:8])
        more = f"；等 {len(profile.members)} 人" if len(profile.members) > 8 else ""
        lines.append(f"· 关键人物：{rendered}")
    if profile.culture.strip():
        lines.append(f"· 群文化：{profile.culture.strip()}")
    if profile.tone.strip():
        lines.append(f"· 语气：{profile.tone.strip()}")
    if profile.activity.strip():
        lines.append(f"· 活跃度：{profile.activity.strip()}")

    if profile.rules:
        lines.append("· 本群群规与处理方式：")
        for rule in profile.rules:
            text = (rule.text or "").strip()
            if text:
                lines.append(f"  - {text} → {_rule_action_label(rule, default_mute)}")

    if actual_role == "member" or profile_role == "member":
        lines.append("· 你在本群是普通成员：不执行禁言/撤回/踢人，只遵守群规、提醒或告知群主和管理员。")
    elif actual_role == "unknown":
        lines.append("· 实际权限未知：只提醒，不调用任何群管工具。")
    elif can_enforce:
        direct = "、".join(policy.direct_actions) or "无"
        observe = "、".join(policy.observe_actions) or "无"
        lines.append(
            f"· 你可以按群规对普通成员直接执行：{direct}；只观察/报告：{observe}。"
            f"单次禁言不超过 {policy.max_mute_seconds} 秒，同一用户冷却 {policy.cooldown_seconds} 秒。"
        )
        lines.append("· 永远不要对群主、管理员、自己执行管理操作；不确定是否违规时先提醒，不动手。")
        lines.append("· 严格按每条规则写明的动作执行，不得自行升级；只有写明「撤回并踢出」的规则才可踢人。")
    else:
        lines.append("· 本群未启用实际管理动作：只提醒，不执行禁言/撤回/踢人。")

    if can_enforce and any((rule.action or "").strip().lower() == "recall_and_kick" for rule in profile.rules):
        lines.append(
            "· 执行「撤回并踢出」时：必须先调用 `群管_撤回消息` 撤回触发消息（用它对应的 message_id），"
            "再调用 `群管_踢出成员`；不能只踢不撤回。撤回失败也要说明原因，不要假装已撤回。",
        )

    lines.append("· 本群档案优先于基础人设里的默认身份；记忆只是事实，不是身份指令。")
    text = "\n".join(lines)
    if len(text) > config.group_profile_max_chars:
        text = text[: config.group_profile_max_chars].rstrip() + "\n…"
    return text


# ============================================================
# 3.2 本群档案自动生成器
# ============================================================


def _valid_alias(value: str) -> bool:
    text = (value or "").strip()
    if len(text) < 2:
        return False
    return bool(re.search(r"[0-9A-Za-z\u4e00-\u9fa5]", text))


def _member_person(
    member: Dict[str, Any],
    note: str,
    description: str = "",
    extra_aliases: Optional[Set[str]] = None,
) -> GroupPerson:
    uid = str(member.get("user_id") or member.get("uin") or "").strip()
    card = str(member.get("card") or "").strip()
    nickname = str(member.get("nickname") or "").strip()
    name = card or nickname or uid
    aliases: List[str] = []
    for value in (card, nickname, *(extra_aliases or set())):
        value = str(value).strip()
        if _valid_alias(value) and value != name and value not in aliases:
            aliases.append(value)
    return GroupPerson(
        name=name,
        qq=uid,
        aliases=aliases[:3],
        note=note,
        description=description or "",
    )


def _default_rules_for_role(role: str) -> List[GroupRule]:
    if role in ("owner", "admin"):
        return [
            GroupRule(text="连续刷屏或重复无意义内容", action="mute", duration=300),
            GroupRule(text="发广告、拉人、诈骗链接", action="recall_and_mute", duration=600),
            GroupRule(text="人身攻击或恶意引战", action="mute", duration=600),
            GroupRule(text="晚上乱艾特人", action="remind"),
            GroupRule(text="严重违规且屡教不改", action="observe_kick"),
            GroupRule(text="发布违法、色情或政治敏感内容", action="recall_and_mute", duration=600),
        ]
    return [
        GroupRule(text="连续刷屏或重复无意义内容", action="remind"),
        GroupRule(text="发广告、拉人、诈骗链接", action="remind"),
        GroupRule(text="对群主或管理员不尊重", action="remind"),
        GroupRule(text="晚上乱艾特人", action="remind"),
    ]


def _default_admin_policy_for_role(role: str) -> GroupAdminPolicy:
    if role in ("owner", "admin"):
        return GroupAdminPolicy(
            enabled=True,
            direct_actions=["mute", "recall", "kick"],
            observe_actions=[],
            protected=["owner", "admins", "self"],
            max_mute_seconds=600,
            cooldown_seconds=60,
        )
    return GroupAdminPolicy(
        enabled=False,
        direct_actions=[],
        observe_actions=[],
        protected=["owner", "admins", "self"],
        max_mute_seconds=600,
        cooldown_seconds=60,
    )


async def _generate_group_profile(chat_key: str) -> Dict[str, Any]:
    if not chat_key.startswith("onebot_v11-group_"):
        raise ValueError("只支持 onebot_v11 群聊 chat_key")
    channel = await DBChatChannel.get_or_none(chat_key=chat_key)
    if channel is None:
        raise ValueError(f"找不到频道: {chat_key}")

    path = _group_profile_root() / f"{chat_key}.yaml"
    existing: Optional[GroupProfile] = None
    if path.exists():
        try:
            existing = GroupProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        except Exception as exc:
            raise ValueError(f"已有档案无法解析，已中止以免覆盖: {exc}") from exc

    ctx = await AgentCtx.create_by_chat_key(chat_key)
    bot = await ctx.get_onebot_v11_bot()
    raw_group_id = str(ctx.channel_id or "").replace("group_", "", 1)
    if not raw_group_id.isdigit():
        raw_group_id = chat_key.split("group_", 1)[-1]
    group_id = int(raw_group_id)
    try:
        member_list = await bot.get_group_member_list(group_id=group_id, no_cache=False)
    except TypeError:
        member_list = await bot.get_group_member_list(group_id=group_id)

    self_id = str(bot.self_id)
    member_map = {str(m.get("user_id")): m for m in member_list if m.get("user_id") is not None}
    self_member = member_map.get(self_id, {})
    role = str(self_member.get("role") or "member")
    if role not in ("owner", "admin", "member"):
        role = "member"

    owner_member = next((m for m in member_list if str(m.get("role")) == "owner"), None)
    admin_members = [m for m in member_list if str(m.get("role")) == "admin"]

    existing_desc: Dict[str, str] = {}
    if existing:
        for person in [existing.owner, *existing.admins, *existing.members]:
            if person and person.qq:
                existing_desc[person.qq] = person.description

    owner_person: Optional[GroupPerson] = None
    if owner_member:
        owner_qq = str(owner_member.get("user_id") or "")
        owner_person = _member_person(owner_member, "本群群主", existing_desc.get(owner_qq, ""))
    elif existing and existing.owner:
        owner_person = existing.owner

    admins = [
        _member_person(
            member,
            "本群管理员",
            existing_desc.get(str(member.get("user_id") or ""), ""),
        )
        for member in admin_members
    ]

    lookback_days = max(1, config.group_profile_generator_lookback_days)
    since = int(_now() - lookback_days * 86400)
    messages = await DBChatMessage.filter(
        chat_key=chat_key,
        send_timestamp__gte=since,
        is_recalled=False,
    ).order_by("send_timestamp").all()

    bot_names = await _get_bot_names_for_chat(chat_key, ctx)
    bot_names |= set(_split_csv(config.extra_bot_names))
    normalized_bot_names = {name.strip().lower() for name in bot_names if name and name.strip()}
    bot_message_ids = {str(msg.message_id) for msg in messages if str(msg.sender_id) == "-1"}

    stats: Dict[str, Dict[str, Any]] = {}
    for msg in messages:
        uid = str(msg.sender_id)
        if uid in ("-1", "") or uid == self_id or uid not in member_map:
            continue
        entry = stats.setdefault(uid, {"direct": 0, "total": 0, "aliases": set()})
        entry["total"] += 1
        text = (msg.content_text or "").lower()
        ref_id: Optional[str] = None
        try:
            ref_id = getattr(msg.ext_data_obj, "ref_msg_id", None)
        except Exception:
            ref_id = None
        direct = bool(msg.is_tome) or (
            ref_id is not None and str(ref_id) in bot_message_ids
        ) or any(name and name in text for name in normalized_bot_names)
        if direct:
            entry["direct"] += 1
        for alias in (msg.sender_nickname, msg.sender_name):
            if alias:
                entry["aliases"].add(str(alias))

    reserved_qqs = {self_id, owner_person.qq if owner_person else ""}
    reserved_qqs.update(str(m.get("user_id") or "") for m in admin_members)
    candidates = [
        (uid, data)
        for uid, data in stats.items()
        if data["direct"] > 0 and uid not in reserved_qqs
    ]
    candidates.sort(key=lambda item: (-item[1]["direct"], -item[1]["total"]))
    member_limit = max(1, config.group_profile_member_limit)
    members: List[GroupPerson] = []
    for uid, data in candidates[:member_limit]:
        member = member_map[uid]
        note = f"与KONA直接互动 {data['direct']} 次；群内发言 {data['total']} 条"
        members.append(
            _member_person(
                member,
                note,
                existing_desc.get(uid, ""),
                data["aliases"],
            ),
        )

    generated_qqs = {person.qq for person in members}
    preserve_limit = max(member_limit, config.group_profile_preserve_limit)
    if existing:
        preserved_qqs = set(generated_qqs) | set(reserved_qqs)
        old_people = [existing.owner, *existing.admins, *existing.members]
        for old_person in old_people:
            if (
                old_person
                and old_person.qq
                and old_person.qq not in preserved_qqs
                and old_person.description.strip()
                and len(members) < preserve_limit
            ):
                members.append(old_person)
                preserved_qqs.add(old_person.qq)

    active_users = sum(1 for data in stats.values() if data["total"] > 0)
    group_size = len(member_list)
    if role == "owner":
        tone = "群主身份，主动但克制，尊重管理员，不滥用权限"
        activity = "可以欢迎新人、提醒群规；少发长文"
    elif role == "admin":
        tone = "管理员身份，协助提醒规则，语气克制"
        activity = "适度提醒，不抢群主的话"
    else:
        tone = "普通成员，熟人语气，少发号施令"
        activity = "被叫到再回应；不主动执法"

    profile = GroupProfile(
        description=existing.description if existing else "",
        enabled=True,
        role="auto",
        owner=owner_person,
        admins=admins,
        members=members,
        culture=f"群人数约 {group_size}，近{lookback_days}天活跃约 {active_users} 人；常聊话题可补充",
        tone=tone,
        activity=activity,
        rules=existing.rules if existing else [],
        admin_policy=_default_admin_policy_for_role(role),
    )

    data = profile.model_dump()
    for rule in data.get("rules", []):
        if rule.get("action") not in ("mute", "recall_and_mute"):
            rule.pop("duration", None)
    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    if path.exists():
        backup_path = path.with_name(path.name + f".bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup_path)
    path.write_text(yaml_text, encoding="utf-8")
    _GROUP_PROFILE_CACHE.pop(chat_key, None)

    summary = {
        "chat_key": chat_key,
        "channel_name": channel.channel_name or chat_key,
        "role": role,
        "owner": owner_person.qq if owner_person else "",
        "admins": len(admins),
        "members": len(members),
        "interacted": len(candidates),
        "messages": len(messages),
        "path": str(path),
        "backup": str(backup_path) if backup_path else "",
    }
    _log("info", f"本群档案生成完成: {summary}")
    return summary


@plugin.mount_command(
    name="group_profile_gen",
    description="根据群成员和与KONA的直接互动生成每群档案 YAML（保留所有 description）",
    usage="group_profile_gen [chat_key|群号|--all]",
    permission=CommandPermission.SUPER_USER,
    category="拟人",
)
async def group_profile_gen_cmd(
    context: CommandExecutionContext,
    target: Annotated[str, Arg("目标 chat_key、群号或 --all", positional=True)] = "",
) -> CommandResponse:
    raw = (target or "").strip()
    if raw == "--all":
        channels = await DBChatChannel.filter(adapter_key="onebot_v11", channel_type="group").all()
        chat_keys = [channel.chat_key for channel in channels]
    elif raw:
        if raw.startswith("onebot_v11-group_"):
            chat_key = raw
        elif raw.isdigit():
            chat_key = f"onebot_v11-group_{raw}"
        else:
            chat_key = raw
        chat_keys = [chat_key]
    else:
        chat_keys = [context.chat_key]

    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    for chat_key in chat_keys:
        try:
            results.append(await _generate_group_profile(chat_key))
        except Exception as exc:
            errors.append(f"{chat_key}: {exc}")

    lines: List[str] = []
    for item in results:
        lines.append(
            f"{item['channel_name']}（{item['chat_key']}）：{_role_label(item['role'])}，"
            f"管理员 {item['admins']}，关键人物 {item['members']}，"
            f"互动用户 {item['interacted']}，消息 {item['messages']}",
        )
    if errors:
        lines.append("失败：")
        lines.extend(errors)
    if not results:
        return CmdCtl.failed("没有生成任何档案。\n" + "\n".join(lines))
    return CmdCtl.success("本群档案生成完成：\n" + "\n".join(lines))


@plugin.mount_command(
    name="force_mute",
    description="强制禁言群成员，0 秒表示解除禁言（超级管理员）",
    usage="force_mute <QQ[,QQ...]> [秒数]",
    permission=CommandPermission.SUPER_USER,
    category="拟人",
)
async def force_mute_cmd(
    context: CommandExecutionContext,
    targets: Annotated[str, Arg("目标QQ，多个用逗号分隔", positional=True)],
    duration: Annotated[int, Arg("禁言秒数，0=解除，留空用默认", positional=True)] = -1,
) -> CommandResponse:
    chat_key = context.chat_key
    if not chat_key.startswith("onebot_v11-group_"):
        return CmdCtl.failed("force_mute 只支持 onebot 群聊")

    qq_list = [item.strip() for item in re.split(r"[,，]+", targets or "") if item.strip()]
    if not qq_list:
        return CmdCtl.failed("请提供要禁言的 QQ，多个用逗号分隔")
    if any(not qq.isdigit() for qq in qq_list):
        return CmdCtl.failed("QQ 必须是纯数字")

    if duration < 0:
        duration = config.force_mute_default_seconds
    duration = min(duration, config.force_mute_max_seconds)

    try:
        ctx = await AgentCtx.create_by_chat_key(chat_key)
        bot = await ctx.get_onebot_v11_bot()
        group_id = int(str(ctx.channel_id or "").replace("group_", "", 1))
        self_id = int(bot.self_id)
        self_info = await bot.get_group_member_info(
            group_id=group_id,
            user_id=self_id,
            no_cache=False,
        )
        bot_role = str(self_info.get("role") or "member")
    except Exception as exc:
        return CmdCtl.failed(f"获取群信息失败: {exc}")

    if bot_role not in ("owner", "admin"):
        return CmdCtl.failed("KONA 在该群不是群主/管理员，无法禁言")

    successes: List[str] = []
    errors: List[str] = []
    for qq in qq_list:
        target = int(qq)
        if target == self_id:
            errors.append(f"{qq}: 不能禁言自己")
            continue
        try:
            target_info = await bot.get_group_member_info(
                group_id=group_id,
                user_id=target,
                no_cache=False,
            )
            target_role = str(target_info.get("role") or "member")
        except Exception as exc:
            errors.append(f"{qq}: 查询成员失败 {exc}")
            continue

        if target_role == "owner":
            errors.append(f"{qq}: 不能禁言群主")
            continue
        if target_role == "admin" and not (bot_role == "owner" and config.force_mute_allow_admins):
            errors.append(
                f"{qq}: 不能禁言管理员（需要 KONA 是群主且开启 force_mute_allow_admins）",
            )
            continue

        try:
            await bot.set_group_ban(group_id=group_id, user_id=target, duration=duration)
        except Exception as exc:
            errors.append(f"{qq}: 执行失败 {exc}")
            continue

        action = "解除禁言" if duration == 0 else f"禁言 {duration} 秒"
        successes.append(f"{qq}: {action}")
        _log(
            "info",
            f"强制禁言: chat={chat_key} target={qq} duration={duration} by={context.user_id}",
        )

    lines = successes + [f"失败 {item}" for item in errors]
    if not successes:
        return CmdCtl.failed("没有成功执行任何操作:\n" + "\n".join(lines))
    return CmdCtl.success("强制禁言完成:\n" + "\n".join(lines))


# ============================================================
# 4. 人设名字解析
# ============================================================


def _extract_bot_names_from_preset(preset: Any) -> Set[str]:
    names: Set[str] = set()
    if not preset:
        return names
    p_name = str(getattr(preset, "name", "") or "").strip()
    if p_name and p_name.lower() not in ("默认预设", "default", "拟人助手", "assistant", "none", "bot"):
        names.add(p_name)

    prompt_text = str(getattr(preset, "system_prompt", None) or getattr(preset, "prompt", None) or "")
    if prompt_text:
        patterns = [
            r"(?:你(?:的名字)?(?:是|叫)|名字[：:\s]+|自称|角色名[：:\s]+|我是)\s*([a-zA-Z0-9_\u4e00-\u9fa5]{2,12})",
            r"(?:name\s*[:=]\s*)([a-zA-Z0-9_-]{2,16})",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, prompt_text, re.IGNORECASE):
                cleaned = match.strip()
                if len(cleaned) >= 2 and cleaned.lower() not in ("一个", "助手", "机器人", "ai", "女孩", "男生"):
                    names.add(cleaned)
    return names


async def _get_bot_names_for_chat(chat_key: str, ctx: Optional[AgentCtx] = None) -> Set[str]:
    now = _now()
    cached = _BOT_NAMES_CACHE.get(chat_key)
    if cached and now - float(cached.get("time", 0)) < 300:
        return set(cached.get("names") or set())

    names: Set[str] = set()
    try:
        target_ctx = ctx
        if not target_ctx and hasattr(AgentCtx, "create_by_chat_key"):
            target_ctx = await AgentCtx.create_by_chat_key(chat_key)
        if target_ctx:
            preset = getattr(target_ctx, "current_preset", None)
            if callable(preset):
                preset = await preset() if asyncio.iscoroutinefunction(preset) else preset()
            names = _extract_bot_names_from_preset(preset)
    except Exception as exc:
        _log("debug", f"动态读取人设名字跳过: {exc}")

    _BOT_NAMES_CACHE[chat_key] = {"names": names, "time": now}
    return names


# ============================================================
# 5. NoneBot 事件拦截与唤醒漏斗
# ============================================================


async def _trigger_agent_for_context(chat_key: str, reason: str, raw_msg: str, user_id: str, msg_id: str) -> None:
    await asyncio.sleep(random.uniform(0.15, 0.45))
    _TRIGGER_CACHE[chat_key] = _new_trigger_cache(
        is_direct=False,
        proactive=False,
        reason=reason,
        sender_id=user_id,
        msg_id=msg_id or None,
        mention_type="other",
    )
    prompt = (
        f"【群聊旁听】{reason}，刚刚有人说：「{raw_msg}」。\n"
        "结合上下文和你的人设判断：对方是在跟你说话，还是你确实有自然、有趣的接话点？\n"
        "· 如果与你无关、对方在私下互动、或插话会突兀：保持沉默，不要调用任何发送方法，直接输出 `# 保持沉默` 结束。\n"
        "· 如果适合接话：像真人一样简短自然地说 1~2 句，不要复述规则。"
    )
    _log("info", f"唤醒 Agent 评估 [{chat_key}] 原因={reason}")
    await message.push_system(chat_key=chat_key, message=prompt, trigger_agent=True)


def _remove_old_preprocessors(only_instance: Optional[int] = None) -> None:
    if not NONEBOT_AVAILABLE:
        return
    try:
        pre_set = getattr(nonebot.message, "_event_preprocessors", None)
        if not pre_set:
            return
        to_remove = set()
        for dep in list(pre_set):
            call_obj = getattr(dep, "call", dep)
            name = getattr(call_obj, "__name__", "")
            marker = getattr(call_obj, "_humanoid_instance", None)
            if name != "_catch_nonebot_message_event" and not marker:
                continue
            if only_instance is not None and marker != only_instance:
                continue
            to_remove.add(dep)
        for dep in to_remove:
            pre_set.discard(dep)
        if to_remove:
            _log("info", f"清理 {len(to_remove)} 个历史事件钩子")
    except Exception as exc:
        _log("warning", f"清理旧事件钩子失败: {exc}")


if NONEBOT_AVAILABLE:
    _remove_old_preprocessors()

    @event_preprocessor
    async def _catch_nonebot_message_event(bot: Bot, event: Event, state: T_State) -> None:
        try:
            if getattr(event, "get_type", lambda: "")() != "message":
                return

            user_id = getattr(event, "user_id", None)
            group_id = getattr(event, "group_id", None)
            msg_id = getattr(event, "message_id", None)
            self_id = str(getattr(bot, "self_id", None) or getattr(event, "self_id", "") or "")

            if not user_id or str(user_id) == self_id:
                return

            msg_id_str = str(msg_id) if msg_id else f"{user_id}_{_now()}"
            if msg_id_str in _PROCESSED_MSG_IDS:
                return
            _PROCESSED_MSG_IDS.add(msg_id_str)
            if len(_PROCESSED_MSG_IDS) > 3000:
                _PROCESSED_MSG_IDS.clear()

            raw_msg = str(getattr(event, "raw_message", "") or "").strip()
            is_to_me = bool(getattr(event, "to_me", False))
            if self_id and (
                f"qq={self_id}" in raw_msg
                or f"[at:qq={self_id}]" in raw_msg
                or f"[CQ:at,qq={self_id}]" in raw_msg
                or f"[@id:{self_id}" in raw_msg
            ):
                is_to_me = True

            chat_key = f"onebot_v11-group_{group_id}" if group_id else f"onebot_v11-private_{user_id}"
            _LAST_INBOUND_TS[chat_key] = _now()
            if msg_id:
                _LAST_INBOUND_MSG_ID[chat_key] = (_now(), str(msg_id))
            if group_id and not is_to_me:
                cached = _TRIGGER_CACHE.get(chat_key)
                if cached and cached.get("is_direct"):
                    _TRIGGER_CACHE.pop(chat_key, None)

            nickname = ""
            sender = getattr(event, "sender", None)
            if sender is not None:
                nickname = str(getattr(sender, "card", "") or getattr(sender, "nickname", "") or "")

            _LAST_INBOUND_TEXT[chat_key] = raw_msg
            _record_recent_links(chat_key, raw_msg, str(user_id), nickname, msg_id_str)
            await _touch_user_state(chat_key, str(user_id), raw_msg, nickname)
            _ensure_background_loop(chat_key)

            if group_id:
                activity = _GROUP_ACTIVITY.setdefault(chat_key, deque(maxlen=64))
                activity.append(_now())

            mention_type = _classify_mention(raw_msg, is_to_me, self_id, group_id)

            if is_to_me or not group_id:
                if _is_night() and not config.night_direct_reply:
                    _log("info", f"夜间直接呼叫但已配置不回复: {chat_key}")
                    return
                direct_type = mention_type if mention_type in ("at", "quote_at", "private") else "at"
                _TRIGGER_CACHE[chat_key] = _new_trigger_cache(
                    is_direct=True,
                    proactive=False,
                    reason=f"直接呼叫({direct_type})",
                    sender_id=str(user_id),
                    msg_id=str(msg_id) if msg_id else None,
                    mention_type=direct_type,
                )
                _log("info", f"直接呼叫: group={group_id}, user={user_id}, type={direct_type}")
                return

            if _is_night() and config.night_silence_groups:
                _log("debug", f"夜间群聊保持沉默: {chat_key}")
                return

            state = await _load_chat_state(chat_key)
            preset_names = await _get_bot_names_for_chat(chat_key)
            config_names = set(_split_csv(config.extra_bot_names))
            all_names = {name.lower() for name in (preset_names | config_names)}
            keywords = [word.lower() for word in _split_csv(config.trigger_keywords)]

            raw_lower = raw_msg.lower()
            reason = ""
            target_prob = 0.0
            name_called = False

            for name in all_names:
                if name and name in raw_lower:
                    reason = f"提及人设名字「{name}」"
                    target_prob = config.keyword_reply_probability
                    name_called = True
                    break
            if not reason:
                for word in keywords:
                    if word in raw_lower:
                        reason = f"提及关注话题「{word}」"
                        target_prob = config.keyword_reply_probability
                        break
            if not reason:
                reason = "普通闲聊"
                target_prob = config.reply_probability

            if name_called:
                _TRIGGER_CACHE[chat_key] = _new_trigger_cache(
                    is_direct=True,
                    proactive=False,
                    reason=reason,
                    sender_id=str(user_id),
                    msg_id=str(msg_id) if msg_id else None,
                    mention_type="name",
                )
            else:
                last_reply = _LAST_UNMENTIONED_REPLY.get(chat_key, 0.0)
                if _now() - last_reply < config.reply_cd_seconds:
                    return

            target_prob *= _night_factor_reply()
            target_prob *= _energy_reply_factor(state)
            target_prob *= _patience_reply_factor(state)
            target_prob = _clamp(target_prob, 0.0, 1.0)

            if target_prob <= 0.0 or not raw_msg:
                return

            dice = random.random()
            hit = target_prob >= 1.0 or dice < target_prob
            _log(
                "debug",
                f"漏斗: msg='{raw_msg[:40]}' 名字={list(all_names)} 类型={reason} "
                f"阈值={target_prob:.3f} 骰子={dice:.3f} 命中={hit}",
            )
            if hit:
                asyncio.create_task(
                    _trigger_agent_for_context(
                        chat_key=chat_key,
                        reason=reason,
                        raw_msg=raw_msg,
                        user_id=str(user_id),
                        msg_id=str(msg_id) if msg_id else "",
                    ),
                )
        except Exception as exc:
            _log("error", f"事件拦截异常: {exc}")

    setattr(_catch_nonebot_message_event, "_humanoid_preprocessor", True)
    setattr(_catch_nonebot_message_event, "_humanoid_instance", INSTANCE_ID)


@plugin.mount_on_user_message()
async def _humanoid_on_user_message(_ctx: AgentCtx, chat_message: Any) -> MsgSignal:
    """处理引用图片硬拦截与夜间免打扰。"""
    try:
        chat_key = str(getattr(chat_message, "chat_key", "") or "")
        chat_type = str(getattr(chat_message, "chat_type", "") or "")
        is_tome = bool(getattr(chat_message, "is_tome", False))
        content_text = str(getattr(chat_message, "content_text", "") or "")
        bot_names = await _get_bot_names_for_chat(chat_key, _ctx) if chat_key else set()
        bot_names |= set(_split_csv(config.extra_bot_names))
        content_lower = content_text.lower()
        bot_called = any(name and name.lower() in content_lower for name in bot_names)
        if chat_key and (is_tome or "private" in chat_key or chat_type == "private" or bot_called):
            ext_data = getattr(chat_message, "ext_data", {}) or {}
            ref_msg_id = str(ext_data.get("ref_msg_id") or "").strip() if isinstance(ext_data, dict) else ""
            if ref_msg_id:
                quoted = await DBChatMessage.filter(
                    chat_key=chat_key,
                    message_id=ref_msg_id,
                ).order_by("-id").first()
                if quoted:
                    summary, _, kind, image_refs = _quoted_message_info(quoted)
                    if kind == "image" and not await _quoted_image_visible(chat_key, image_refs):
                        await message.send_text(
                            chat_key,
                            "这张图我没看到，你直接说图里是什么吧",
                            _ctx,
                        )
                        _log("info", f"引用图片不可见，已硬拦截: {chat_key} ref={ref_msg_id}")
                        return MsgSignal.BLOCK_TRIGGER
                    if kind == "card":
                        await message.send_text(
                            chat_key,
                            _quoted_no_link_reply(summary),
                            _ctx,
                        )
                        _log("info", f"无链接卡片引用，已硬拦截: {chat_key} ref={ref_msg_id}")
                        return MsgSignal.BLOCK_TRIGGER
        if not _is_night():
            return MsgSignal.CONTINUE
        if "private" in chat_key or chat_type == "private":
            if not config.night_direct_reply:
                _log("debug", "夜间私聊仅记录不触发")
                return MsgSignal.BLOCK_TRIGGER
            return MsgSignal.CONTINUE
        if config.night_silence_groups:
            _log("debug", "夜间群聊仅记录不触发")
            return MsgSignal.BLOCK_TRIGGER
        if is_tome and not config.night_direct_reply:
            _log("debug", "夜间群聊 @ 仅记录不触发")
            return MsgSignal.BLOCK_TRIGGER
    except Exception as exc:
        _log("warning", f"夜间消息信号处理失败: {exc}")
    return MsgSignal.CONTINUE


# ============================================================
# 6. 发送管线：分段、节奏、瑕疵、防重复
# ============================================================

RE_CQ_REPLY = re.compile(r"\[CQ:reply,id=(\d+)\]", re.IGNORECASE)
RE_CQ_AT = re.compile(r"\[CQ:at,qq=(\d+)\]", re.IGNORECASE)
RE_SPLIT_MARKER = re.compile(r"\[\s*T?\s*SPLIT\s*\]", re.IGNORECASE)
RE_LEFTOVER_SPLIT = re.compile(r"(?<![A-Za-z])(?:TSPLIT|SPLIT)(?![A-Za-z])")
RE_TRAILING_TOOL_VALUE = re.compile(r"(?<=[\u4e00-\u9fa5])\s*(?:True|False|None)\s*$")
RE_PUNCT_END = re.compile(r"[。！？!?…~～]$")
RE_SPLIT_SENTENCE = re.compile(r"(?<=[。！？!?…])\s*")
RE_SPLIT_COMMA = re.compile(r"(?<=[，,；;])\s*")
RE_UNSAFE_IMPERFECTION = re.compile(r"https?://|```|`|\[|\]|\{|\}|<|>|@\d|/app/|\.(?:jpg|png|gif|webp|mp4|py|json|ya?ml)\b", re.IGNORECASE)


def _normalize_cq(text: str) -> str:
    text = RE_CQ_AT.sub(lambda m: f"[@id:{m.group(1)}@]", text)
    return text


def _strip_reply_markup(text: str) -> Tuple[str, Optional[str]]:
    reply_id: Optional[str] = None
    match = RE_CQ_REPLY.search(text)
    if match:
        reply_id = match.group(1)
        text = RE_CQ_REPLY.sub("", text).strip()
    return text, reply_id


def _is_imperfection_safe(text: str) -> bool:
    if not text or len(text) < 4:
        return False
    if RE_UNSAFE_IMPERFECTION.search(text):
        return False
    return bool(re.search(r"[\u4e00-\u9fa5a-zA-Z]", text))


def _apply_imperfections(text: str) -> str:
    cfg = config
    if not cfg.enable_imperfections or not _is_imperfection_safe(text):
        return text
    result = text

    if random.random() < cfg.duplicate_char_rate:
        chars = list(result)
        candidates = [i for i, ch in enumerate(chars[:-1]) if re.match(r"[\u4e00-\u9fa5]", ch) and i > 0]
        if candidates:
            index = random.choice(candidates)
            chars.insert(index, chars[index])
            result = "".join(chars)

    if random.random() < cfg.trailing_ellipsis_rate and not RE_PUNCT_END.search(result):
        result += random.choice(["…"])

    if random.random() < cfg.filler_rate:
        fillers = _split_csv(cfg.filler_words)
        if fillers:
            prefix = random.choice(fillers)
            if result and result[0] not in "，,。！？!?、 ":
                result = f"{prefix}，{result}" if random.random() < 0.6 else f"{prefix}{result}"

    return result


_PUNCT_PROTECT_PATTERNS = (
    (re.compile(r"```.*?```", re.DOTALL), False),
    (re.compile(r"`[^`\n]*`"), False),
    (re.compile(r"\[@id:[^\]]*@\]"), False),
    (re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE), True),
    (re.compile(r"(?<![\w/])/[\w./-]+"), False),
    (re.compile(r"(?<!\d)\d{4}[-/]\d{1,2}[-/]\d{1,2}(?!\d)"), False),
    (re.compile(r"(?<!\d)\d{1,2}:\d{2}(?!\d)"), False),
    (re.compile(r"(?<![A-Za-z])(?:km/h|m/s)(?![A-Za-z])"), False),
    (re.compile(r"(?:公里/小时|千米/小时)"), False),
    (re.compile(r"(?<![A-Za-z0-9_])[+-]?\d+(?:\.\d+)?(?![0-9.])"), False),
)
_URL_TRAILING_PUNCT = "。，！？；：、…—～·“”‘’（）【】《》〈〉「」『』"
_PUNCT_PROTECT_BASE = 0xE000


def _strip_punctuation(text: str) -> str:
    if not text:
        return text
    text = RE_TRAILING_TOOL_VALUE.sub("", text)
    if not config.strip_punctuation:
        return RE_LEFTOVER_SPLIT.sub("", text)

    protected: List[str] = []

    def _protect(match: re.Match[str], trim_trailing: bool = False) -> str:
        value = match.group(0)
        if trim_trailing:
            value = value.rstrip(_URL_TRAILING_PUNCT)
        protected.append(value)
        return chr(_PUNCT_PROTECT_BASE + len(protected) - 1)

    result = text
    for pattern, trim_trailing in _PUNCT_PROTECT_PATTERNS:
        result = pattern.sub(lambda match, trim=trim_trailing: _protect(match, trim), result)

    result = RE_LEFTOVER_SPLIT.sub("", result)

    chars = config.punctuation_chars or ""
    if chars:
        result = re.sub(f"[{re.escape(chars)}]", "", result)

    for index, value in enumerate(protected):
        result = result.replace(chr(_PUNCT_PROTECT_BASE + index), value)

    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _make_typo(text: str) -> Optional[str]:
    chars = list(text)
    candidates = [
        i
        for i in range(1, len(chars) - 1)
        if re.match(r"[\u4e00-\u9fa5]", chars[i]) and re.match(r"[\u4e00-\u9fa5]", chars[i + 1])
    ]
    if not candidates:
        return None
    index = random.choice(candidates)
    chars[index], chars[index + 1] = chars[index + 1], chars[index]
    typo = "".join(chars)
    return typo if typo != text else None


def _split_text(text: str) -> List[str]:
    cfg = config
    if RE_SPLIT_MARKER.search(text):
        parts = [part.strip() for part in RE_SPLIT_MARKER.split(text) if part.strip()]
        return _limit_segments(parts)

    if not cfg.auto_split or len(text.strip()) < cfg.auto_split_min_chars:
        return [text.strip()] if text.strip() else []

    parts = [part.strip() for part in RE_SPLIT_SENTENCE.split(text) if part.strip()]
    if len(parts) < cfg.min_segments and len(text) > 40:
        comma_parts = [part.strip() for part in RE_SPLIT_COMMA.split(text) if part.strip()]
        if len(comma_parts) > len(parts):
            parts = comma_parts
    return _limit_segments(parts)


def _limit_segments(parts: List[str]) -> List[str]:
    if not parts:
        return []
    max_segments = max(1, config.max_segments)
    if len(parts) > max_segments:
        head = parts[: max_segments - 1]
        tail = "".join(parts[max_segments - 1 :])
        parts = head + [tail]
    return [part for part in parts if part]


def _segment_delay(part: str, index: int, state: Dict[str, Any]) -> float:
    cfg = config
    base = random.uniform(cfg.segment_delay_min, cfg.segment_delay_max)
    per_char = random.uniform(cfg.char_delay_min, cfg.char_delay_max) * len(part)
    punctuation = cfg.punctuation_pause if RE_PUNCT_END.search(part) else 0.0
    total = base + per_char + punctuation
    total *= _night_factor_delay() * _energy_delay_factor(state)
    if random.random() < cfg.burst_probability:
        total *= 0.12
    low = max(0.05, cfg.min_segment_gap)
    high = max(low, cfg.max_segment_delay)
    return _clamp(total, low, high)


def _recently_sent(chat_key: str, text: str) -> bool:
    recent = _RECENT_SENT.get(chat_key)
    if not recent:
        return False
    return _normalize_for_repeat(text) in recent


def _vary_reply(text: str) -> str:
    if random.random() < 0.5:
        return f"{text}…"
    fillers = _split_csv(config.filler_words)
    if fillers:
        return f"{random.choice(fillers)}，{text}"
    return text


def _build_reply_policy(cache: Dict[str, Any]) -> Dict[str, Any]:
    cfg = config
    policy: Dict[str, Any] = {
        "mode": "off",
        "trigger_time": float(cache.get("time", 0) or 0),
        "trigger_msg_id": cache.get("msg_id"),
        "sender_id": cache.get("sender_id"),
    }
    if not cfg.follow_trigger_reply_style or cache.get("first_reply_done"):
        return policy

    mention_type = cache.get("mention_type")
    if mention_type == "quote_at" and cfg.quote_at_first_reply_quote_at:
        policy["mode"] = "quote_at"
    elif mention_type == "at" and cfg.at_first_reply_plain:
        policy["mode"] = "plain"
    elif mention_type in ("name", "private", "other") and cfg.non_at_first_reply_plain:
        policy["mode"] = "plain"
    return policy


def _apply_first_reply_style(text: str, ref_msg_id: Optional[str], policy: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    mode = str(policy.get("mode") or "off")
    if mode == "off":
        return text, ref_msg_id

    original = text
    text = RE_CQ_REPLY.sub("", text).strip()
    sender = str(policy.get("sender_id") or "").strip()

    if mode == "quote_at":
        trigger_msg_id = policy.get("trigger_msg_id")
        if sender:
            text = re.sub(rf"^(\s*\[@id:{re.escape(sender)}(?:;[^\]]*)?@\]\s*)+", "", text).strip()
            text = f"[@id:{sender}@] {text}".strip()
        return (text or original), (str(trigger_msg_id) if trigger_msg_id else ref_msg_id)

    if mode == "plain":
        if sender:
            text = re.sub(rf"^(\s*\[@id:{re.escape(sender)}(?:;[^\]]*)?@\]\s*)+", "", text).strip()
        text = re.sub(r"^(\s*\[@id:[^\]]*@\]\s*)+", "", text).strip()
        return (text or original), None

    return text, ref_msg_id


def _mark_first_reply_done(chat_key: str, policy: Dict[str, Any]) -> None:
    cache = _TRIGGER_CACHE.get(chat_key)
    if not cache:
        return
    if float(cache.get("time", 0) or 0) != float(policy.get("trigger_time", -1) or -1):
        return
    cache["first_reply_done"] = True


async def _send_parts(
    chat_key: str,
    parts: List[str],
    ctx: Optional[AgentCtx],
    record: bool,
    ref_msg_id: Optional[str],
    state: Dict[str, Any],
    reply_policy: Optional[Dict[str, Any]] = None,
) -> None:
    if not parts:
        return
    send_started = _now()
    total = len(parts)

    thinking = random.uniform(config.thinking_delay_min, config.thinking_delay_max)
    thinking *= _night_factor_delay() * _energy_delay_factor(state)
    thinking = _clamp(thinking, 0.05, config.max_segment_delay)
    if config.debug_log:
        _log("info", f"首段思考延迟: {thinking:.2f}s")
    await asyncio.sleep(thinking)

    policy_applied = False

    for index, part in enumerate(parts):
        if index > 0 and config.interrupt_on_new_message:
            if _LAST_INBOUND_TS.get(chat_key, 0) > send_started:
                _log("info", f"检测到新消息，停止剩余分段: {chat_key}")
                break

        if index > 0:
            delay = _segment_delay(part, index, state)
            if config.debug_log:
                _log("info", f"段延迟: index={index} delay={delay:.2f}s")
            await asyncio.sleep(delay)

        current_ref = ref_msg_id if index == 0 else None
        text = _normalize_cq(part)
        text, inline_ref = _strip_reply_markup(text)
        if index == 0 and not current_ref and inline_ref:
            current_ref = inline_ref
        if not text:
            continue

        if _recently_sent(chat_key, text):
            action = config.anti_repeat_action.strip().lower()
            if action == "skip":
                _log("info", f"跳过重复消息: {text[:30]}")
                continue
            if action == "vary":
                text = _vary_reply(text)

        text = _apply_imperfections(text)

        applied_now = False
        if reply_policy and not policy_applied and str(reply_policy.get("mode") or "off") != "off":
            text, current_ref = _apply_first_reply_style(text, current_ref, reply_policy)
            applied_now = True

        if not applied_now and config.correction_rate > 0 and random.random() < config.correction_rate:
            typo = _make_typo(text)
            if typo:
                typo_text = _strip_punctuation(typo)
                if typo_text:
                    await _raw_send_text(chat_key, typo_text, ctx, record=record, ref_msg_id=current_ref)
                    await _note_bot_send(chat_key, typo_text)
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                text = f"{config.correction_prefix}{text}"
                current_ref = None

        text = _strip_punctuation(text)
        if not text:
            continue

        await _raw_send_text(chat_key, text, ctx, record=record, ref_msg_id=current_ref)
        await _note_bot_send(chat_key, text)

        if applied_now:
            policy_applied = True
            _mark_first_reply_done(chat_key, reply_policy)

        if index < total - 1:
            await asyncio.sleep(0.05)


async def _raw_send_text(chat_key: str, text: str, ctx: Optional[AgentCtx], *, record: bool, ref_msg_id: Optional[str]) -> None:
    original = _ORIGINAL_SEND_TEXT
    await original(chat_key, text, ctx, record=record, ref_msg_id=ref_msg_id)


async def _patched_send_text(chat_key: str, message_content: Optional[str] = None, ctx: Optional[AgentCtx] = None, **kwargs: Any) -> None:
    text = message_content if message_content is not None else kwargs.pop("message", None)
    record = bool(kwargs.pop("record", True))
    ref_msg_id = kwargs.pop("ref_msg_id", None)
    if not isinstance(text, str) or not text.strip():
        return

    cfg = config
    cache = _TRIGGER_CACHE.get(chat_key, {})
    is_direct = _is_direct_chat(chat_key, cache)
    is_proactive = bool(cache.get("proactive")) and _now() - float(cache.get("time", 0)) < 300
    recent = _now() - float(cache.get("time", 0)) < 300

    _log(
        "debug",
        f"出口审查: {chat_key} direct={is_direct} proactive={is_proactive} recent={recent}",
    )

    if cfg.strict_send_gate and not is_direct and not is_proactive and not recent:
        if cfg.reply_probability <= 0.0:
            _log("warning", f"拦截无触发记录的群消息: {chat_key}")
            return

    if not is_direct and "group" in chat_key:
        _LAST_UNMENTIONED_REPLY[chat_key] = _now()

    state = await _load_chat_state(chat_key)
    parts = _split_text(text)
    reply_policy = _build_reply_policy(cache)
    if reply_policy.get("mode") != "off":
        _log(
            "debug",
            f"首条回复策略: mode={reply_policy['mode']} sender={reply_policy.get('sender_id')} "
            f"trigger_msg={reply_policy.get('trigger_msg_id')}",
        )
    lock = _SEND_LOCKS.setdefault(chat_key, asyncio.Lock())
    async with lock:
        await _send_parts(chat_key, parts, ctx, record, ref_msg_id, state, reply_policy)


def _looks_like_image_path(value: Any) -> bool:
    text = str(value).split("?", 1)[0].split("#", 1)[0].strip().lower()
    return text.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"))


async def _patched_send_media(original: Any, chat_key: str, *args: Any, **kwargs: Any) -> None:
    cfg = config
    if cfg.enable_sticker_coordination:
        delay = random.uniform(cfg.media_delay_min, cfg.media_delay_max) * _night_factor_delay()
        await asyncio.sleep(_clamp(delay, 0.0, cfg.max_segment_delay))

    is_image = original is _ORIGINAL_SEND_IMAGE or bool(args and _looks_like_image_path(args[0]))
    await original(chat_key, *args, **kwargs)
    if is_image:
        _LAST_MEDIA_SENT[chat_key] = _now()


_ORIGINAL_SEND_TEXT: Any = getattr(message, "_humanoid_original_send_text", None)
_ORIGINAL_SEND_IMAGE: Any = getattr(message, "_humanoid_original_send_image", None)
_ORIGINAL_SEND_FILE: Any = getattr(message, "_humanoid_original_send_file", None)

if _ORIGINAL_SEND_TEXT is None:
    _ORIGINAL_SEND_TEXT = getattr(message, "_raw_origin_send_text", None) or message.send_text
    message._humanoid_original_send_text = _ORIGINAL_SEND_TEXT
if _ORIGINAL_SEND_IMAGE is None:
    _ORIGINAL_SEND_IMAGE = message.send_image
    message._humanoid_original_send_image = _ORIGINAL_SEND_IMAGE
if _ORIGINAL_SEND_FILE is None:
    _ORIGINAL_SEND_FILE = message.send_file
    message._humanoid_original_send_file = _ORIGINAL_SEND_FILE


async def _send_image_wrapper(chat_key: str, *args: Any, **kwargs: Any) -> None:
    await _patched_send_media(_ORIGINAL_SEND_IMAGE, chat_key, *args, **kwargs)


async def _send_file_wrapper(chat_key: str, *args: Any, **kwargs: Any) -> None:
    await _patched_send_media(_ORIGINAL_SEND_FILE, chat_key, *args, **kwargs)


message.send_text = _patched_send_text
message.send_image = _send_image_wrapper
message.send_file = _send_file_wrapper


# ============================================================
# 7. 小事记忆工具（与好感度插件分工）
# ============================================================


@plugin.mount_sandbox_method(
    SandboxMethodType.BEHAVIOR,
    "humanoid_remember",
    "记住与当前用户相关的一件小事，供以后自然提起",
)
async def humanoid_remember(_ctx: AgentCtx, topic: str, feeling: str = "") -> str:
    """记住一件值得记住的小事

    当用户分享了值得以后自然提起的信息（喜好、计划、近况、约定等）时调用。
    只记录小事，不要记录密码、身份证、住址等敏感信息；不要把它当好感度评分使用。

    Args:
        topic (str): 要记住的事情，简短具体，例如「下周要考 FPGA」。
        feeling (str): 你当时的感受或想以后怎么回应，例如「有点担心他，想问问进展」。

    Returns:
        str: ok
    """
    if not config.enable_memory:
        raise ValueError("小事记忆功能已被配置关闭")
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    if len(topic) > 120:
        topic = topic[:120]

    user_key = _ctx.from_platform_userid or "unknown"
    chat_key = _ctx.from_chat_key or _ctx.chat_key
    user_state = await _load_user_state(chat_key, user_key)
    memories = user_state.get("memories")
    if not isinstance(memories, list):
        memories = []
    memories.append({"t": _now(), "topic": topic, "feeling": (feeling or "").strip()[:120]})
    user_state["memories"] = memories[-max(0, config.memory_limit):]
    await _save_user_state(chat_key, user_key, user_state)
    return "ok"


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    "human_search",
    "联网搜索实时信息，返回标题、摘要、来源和 URL",
)
async def human_search(_ctx: AgentCtx, query: str, max_results: int | None = None) -> str:
    """联网搜索关键词、问题、新闻主题或网页主题。

    Args:
        query (str): 要搜索的内容，例如「武汉天气」「DeepSeek V4 发布」。
        max_results (int | None): 返回条数，默认使用配置，范围 1-10。

    Returns:
        str: 带标题、摘要和 URL 的搜索结果；失败时返回明确错误。
    """
    if not config.human_search_enabled:
        return "联网搜索已关闭。"
    query = (query or "").strip()
    if not query:
        return "human_search 需要一个非空查询。"
    if len(query) > 128:
        query = query[:128]
    try:
        limit = config.human_search_max_results if max_results is None else int(max_results)
    except (TypeError, ValueError):
        limit = config.human_search_max_results
    limit = max(1, min(limit, 10))
    payload = {
        "query": query,
        "count": limit,
        "need_content": bool(config.human_search_need_content),
    }
    try:
        data = await asyncio.to_thread(
            _human_deepseek_post,
            "/v1/tools/search",
            payload,
            int(config.human_search_timeout_seconds),
        )
    except HumanSearchError as exc:
        return f"联网搜索失败：{exc}"
    return _format_human_search_results(query, data)


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    "human_fetch",
    "抓取单个网页，返回标题和 Markdown 正文",
)
async def human_fetch(_ctx: AgentCtx, url: str, max_chars: int | None = None) -> str:
    """抓取一个网页的正文，用于补充搜索摘要。

    Args:
        url (str): 要抓取的 HTTP/HTTPS 网页地址。
        max_chars (int | None): 返回正文的最大字符数，默认使用配置。

    Returns:
        str: 网页标题和 Markdown 正文；失败时返回明确错误。
    """
    if not config.human_fetch_enabled:
        return "联网抓取已关闭。"
    url = (url or "").strip()
    if len(url) > 8192:
        return "human_fetch 的 URL 过长。"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "human_fetch 只接受带 host 的 HTTP/HTTPS URL。"
    if parsed.username or parsed.password:
        return "human_fetch 不接受带用户名或密码的 URL。"
    _log("info", f"human_fetch: url={url}")
    chat_key = _ctx.from_chat_key or _ctx.chat_key
    if _should_block_context_fetch(chat_key, url):
        _log("info", f"human_fetch 被拦截: 本轮不自动抓取上下文链接 url={url}")
        return "本轮判定不自动抓取这个上下文链接；如果确实需要，请明确说要看这个链接/评论。"
    try:
        limit = config.human_fetch_max_chars if max_chars is None else int(max_chars)
    except (TypeError, ValueError):
        limit = config.human_fetch_max_chars
    limit = max(500, min(limit, 20000))
    timeout = int(config.human_search_timeout_seconds)
    if _is_bilibili_video_url(url):
        comment_limit = (
            max(0, min(int(config.bili_comments_limit), 20))
            if config.bili_comments_enabled
            else 0
        )
        try:
            resolved, info, comments, comment_error = await asyncio.to_thread(
                _fetch_bili_bundle,
                url,
                comment_limit,
                config.bili_comments_sort,
                timeout,
            )
            return _format_bili_fetch(
                resolved,
                info,
                comments,
                comment_error,
                comment_limit,
                limit,
            )
        except BiliFetchError as exc:
            _log("warning", f"B站抓取失败，回退 DeepSeek Fetch: {exc}")
    try:
        data = await asyncio.to_thread(
            _human_deepseek_post,
            "/v1/tools/fetch",
            {"url": url},
            timeout,
        )
    except HumanSearchError as exc:
        return f"网页抓取失败：{exc}"
    return _format_human_fetch_result(url, data, limit)


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    "human_bangumi_search",
    "搜索 Bangumi 动画条目，返回 ID、标题、评分、简介",
)
async def human_bangumi_search(_ctx: AgentCtx, keyword: str, limit: int | None = None) -> str:
    """搜索 Bangumi 动画条目。

    Args:
        keyword (str): 动画名称、别名或关键词。
        limit (int | None): 返回条数，默认使用配置，范围 1-10。

    Returns:
        str: 动画条目列表；失败时返回明确错误。
    """
    if not config.bangumi_enabled:
        return "Bangumi 查询已关闭。"
    keyword = (keyword or "").strip()
    if not keyword:
        return "human_bangumi_search 需要一个非空关键词。"
    if len(keyword) > 128:
        keyword = keyword[:128]
    try:
        count = config.bangumi_search_limit if limit is None else int(limit)
    except (TypeError, ValueError):
        count = config.bangumi_search_limit
    count = max(1, min(count, 10))
    payload = {
        "keyword": keyword,
        "sort": "match",
        "filter": {"type": [2], "nsfw": bool(config.bangumi_include_nsfw)},
    }
    try:
        data = await asyncio.to_thread(
            _bangumi_request,
            "/v0/search/subjects",
            method="POST",
            params={"limit": count, "offset": 0},
            payload=payload,
            timeout=int(config.bangumi_timeout_seconds),
        )
    except BangumiError as exc:
        return f"Bangumi 搜索失败：{exc}"
    return _format_bangumi_search(keyword, data)


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    "human_bangumi_subject",
    "查询 Bangumi 动画条目详情",
)
async def human_bangumi_subject(_ctx: AgentCtx, subject_id: int) -> str:
    """查询 Bangumi 动画条目详情。

    Args:
        subject_id (int): Bangumi 条目 ID，可从搜索结果的 ID 获取。

    Returns:
        str: 条目详情；失败时返回明确错误。
    """
    if not config.bangumi_enabled:
        return "Bangumi 查询已关闭。"
    try:
        sid = int(subject_id)
    except (TypeError, ValueError):
        return "subject_id 必须是数字。"
    if sid <= 0:
        return "subject_id 必须是正整数。"
    try:
        data = await asyncio.to_thread(
            _bangumi_request,
            f"/v0/subjects/{sid}",
            timeout=int(config.bangumi_timeout_seconds),
        )
    except BangumiError as exc:
        return f"Bangumi 条目查询失败：{exc}"
    if not isinstance(data, dict):
        return f"Bangumi 条目 {sid} 返回了异常数据。"
    return _format_bangumi_subject(data)


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    "human_bangumi_characters",
    "查询 Bangumi 动画条目的角色和声优",
)
async def human_bangumi_characters(
    _ctx: AgentCtx,
    subject_id: int,
    limit: int | None = None,
) -> str:
    """查询动画角色和声优。

    Args:
        subject_id (int): Bangumi 条目 ID。
        limit (int | None): 返回角色数量，默认使用配置，范围 1-20。

    Returns:
        str: 角色列表；失败时返回明确错误。
    """
    if not config.bangumi_enabled:
        return "Bangumi 查询已关闭。"
    try:
        sid = int(subject_id)
    except (TypeError, ValueError):
        return "subject_id 必须是数字。"
    if sid <= 0:
        return "subject_id 必须是正整数。"
    try:
        count = config.bangumi_character_limit if limit is None else int(limit)
    except (TypeError, ValueError):
        count = config.bangumi_character_limit
    count = max(1, min(count, 20))
    try:
        data = await asyncio.to_thread(
            _bangumi_request,
            f"/v0/subjects/{sid}/characters",
            timeout=int(config.bangumi_timeout_seconds),
        )
    except BangumiError as exc:
        return f"Bangumi 角色查询失败：{exc}"
    if not isinstance(data, list):
        return f"Bangumi 条目 {sid} 没有返回角色数据。"
    return _format_bangumi_characters(sid, data[:count])


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    "human_bangumi_calendar",
    "查询 Bangumi 每日放送的新番",
)
async def human_bangumi_calendar(
    _ctx: AgentCtx,
    weekday: str | None = None,
    limit: int | None = None,
) -> str:
    """查询 Bangumi 每日放送。

    Args:
        weekday (str | None): today / 周一 / 星期一 / mon / 1-7；留空表示今天。
        limit (int | None): 返回条数，默认使用配置，范围 1-20。

    Returns:
        str: 当日放送列表；失败时返回明确错误。
    """
    if not config.bangumi_enabled:
        return "Bangumi 查询已关闭。"
    day = _bangumi_weekday_number(weekday)
    try:
        count = config.bangumi_calendar_limit if limit is None else int(limit)
    except (TypeError, ValueError):
        count = config.bangumi_calendar_limit
    count = max(1, min(count, 20))
    try:
        data = await asyncio.to_thread(
            _bangumi_request,
            "/calendar",
            timeout=int(config.bangumi_timeout_seconds),
        )
    except BangumiError as exc:
        return f"Bangumi 每日放送查询失败：{exc}"
    if not isinstance(data, list):
        return "Bangumi 每日放送返回了异常数据。"
    items: List[Dict[str, Any]] = []
    for group in data:
        if not isinstance(group, dict):
            continue
        weekday_data = group.get("weekday") if isinstance(group.get("weekday"), dict) else {}
        if int(weekday_data.get("id") or 0) == day:
            raw_items = group.get("items")
            if isinstance(raw_items, list):
                items = [item for item in raw_items if isinstance(item, dict)]
            break
    return _format_bangumi_calendar(day, items[:count])


# ============================================================
# 8. 提示词注入
# ============================================================


@plugin.mount_prompt_inject_method(
    name="humanoid_presence_inject",
    description="注入即时情绪、精力、作息、关系熟悉度与拟人行为规范",
)
async def inject_humanoid_presence(_ctx: AgentCtx) -> str:
    try:
        cfg = config
        chat_key = _ctx.from_chat_key or _ctx.chat_key
        cache = _TRIGGER_CACHE.get(chat_key, {})
        is_direct = _is_direct_chat(chat_key, cache)
        if not is_direct and _is_night() and cfg.night_silence_groups:
            is_direct = False
        mention_type = cache.get("mention_type")
        trigger_sender = str(cache.get("sender_id") or "").strip()
        trigger_msg_id = str(cache.get("msg_id") or "").strip()
        quoted_message = await _load_quoted_message(chat_key, trigger_msg_id)
        quoted_url = quoted_message[2] if quoted_message else ""
        link_fetch_mode = ""
        link_fetch_allow = False
        link_context_urls: List[str] = []
        recent_link_items: List[Dict[str, Any]] = []
        link_fetch_roll = random.random()
        cache.pop("link_fetch_mode", None)
        cache.pop("link_fetch_allow", None)
        cache.pop("link_context_urls", None)
        if cfg.human_fetch_enabled:
            if quoted_url:
                link_fetch_mode = "quoted"
                link_fetch_allow = bool(cfg.quoted_link_always_fetch) or (
                    link_fetch_roll < cfg.link_fetch_probability
                )
                link_context_urls = [quoted_url]
            elif quoted_message is None and cfg.link_fetch_enabled:
                recent_link_items = _get_recent_links(chat_key)
                if recent_link_items:
                    explicit_reference = _is_explicit_link_reference(_LAST_INBOUND_TEXT.get(chat_key, ""))
                    link_fetch_mode = "explicit" if explicit_reference else "vague"
                    link_fetch_allow = explicit_reference or (
                        link_fetch_roll < cfg.link_fetch_probability
                    )
                    link_context_urls = [
                        _normalize_quoted_url(item.get("url"))
                        for item in recent_link_items
                        if item.get("url")
                    ]
            if quoted_url:
                _log("info", f"引用消息链接: {quoted_url}")
            if link_fetch_mode:
                cache["link_fetch_mode"] = link_fetch_mode
                cache["link_fetch_allow"] = link_fetch_allow
                cache["link_context_urls"] = link_context_urls
                _log(
                    "info",
                    f"链接抓取判定: mode={link_fetch_mode} allow={link_fetch_allow} "
                    f"roll={link_fetch_roll:.3f} p={cfg.link_fetch_probability:.2f} chat={chat_key}",
                )

        group_profile = _load_group_profile(chat_key)
        profile_role = "auto"
        actual_role = "unknown"
        if group_profile and group_profile.enabled:
            profile_role = _profile_role(group_profile)
            actual_role = await _detect_bot_role(_ctx, chat_key)

        bot_names = await _get_bot_names_for_chat(chat_key, _ctx)
        bot_names |= set(_split_csv(cfg.extra_bot_names))
        bot_name_text = "、".join(sorted(name for name in bot_names if name.strip())[:8]) or "系统配置的昵称"

        state = await _load_chat_state(chat_key)
        user_key = _ctx.from_platform_userid or str(cache.get("sender_id") or "unknown")
        user_state = await _load_user_state(chat_key, user_key)

        now_local = _local_now()
        period = "深夜" if _is_night() else ("早上" if now_local.hour < 11 else ("中午" if now_local.hour < 14 else ("下午" if now_local.hour < 18 else "晚上")))
        energy = int(round(float(state.get("energy", cfg.energy_start))))
        patience = int(round(float(state.get("patience", cfg.patience_start))))
        valence = int(round(float(state.get("valence", cfg.mood_baseline))))
        familiarity = int(round(float(user_state.get("familiarity", 0.0))))
        interaction_count = int(user_state.get("interactions") or 0)
        memories = user_state.get("memories") if isinstance(user_state.get("memories"), list) else []
        recent_topics = state.get("recent_topics") if isinstance(state.get("recent_topics"), list) else []
        draw_user_id = str(_ctx.from_platform_userid or cache.get("sender_id") or "").strip()
        draw_is_super = _is_super_user(draw_user_id)
        draw_refuse_roll = random.random()
        draw_proactive_roll = random.random()
        draw_proactive_allowed = (
            cfg.draw_proactive_enabled
            and cfg.draw_proactive_max_per_day > 0
            and draw_proactive_roll < cfg.draw_proactive_probability
        )
        _log(
            "debug",
            f"画图策略: user={draw_user_id or '-'} super={draw_is_super} "
            f"拒绝骰子={draw_refuse_roll:.3f} 主动骰子={draw_proactive_roll:.3f} 主动允许={draw_proactive_allowed}",
        )

        lines: List[str] = []
        lines.extend(
            """
======【代码格式铁律（最高优先级）】======
· 你整段回复必须是一段可直接执行的 Python 3 代码。
· 禁止 Markdown 代码块、禁止裸文本、禁止 HTML/DSML/XML 标签。
· 所有要发到群里的文字，必须作为字符串参数传给 send_msg_text(_ck, "...")。
· 图片/文件用 send_msg_file(_ck, "...")。
· 只使用系统/插件已提供的函数；不要发明 send_split_reply / reply / send 等不存在的方法。
· 自然语言只能写在字符串内部；代码行里不能直接写聊天内容。
· 代码语法必须使用英文标点；中文标点和聊天文本只能出现在字符串里。
· [SPLIT] 只能写在字符串内部；禁止 <SPLIT>、[TSPLIT]、SPLIT、<dry-run>。
· 工具返回值（True/False/ID/JSON/路径）只用于判断，不要拼进聊天字符串。
· 发送前自检：整段是否能被 Python 解析？是否有裸文本行？字符串和括号是否闭合？

正确写法：
send_msg_text(_ck, "第一句[SPLIT]第二句")
send_msg_text(_ck, "在的", ref_msg_id="123")
send_msg_file(_ck, "/app/uploads/x.jpg")

错误写法（会 SyntaxError）：
第一句[SPLIT]第二句
<SPLIT>第一句
用 Markdown 代码块包裹整段回复

最安全模板：只想说一句话时，直接写：
send_msg_text(_ck, "内容")
""".strip().splitlines(),
        )
        if quoted_message:
            quoted_sender, quoted_summary, quoted_url, quoted_kind, quoted_images = quoted_message
            lines.append("======【引用消息】======")
            lines.append(f"· 对方引用了「{quoted_sender}」的消息：")
            if quoted_summary:
                lines.append(f"  「{quoted_summary}」")
            if quoted_kind == "image":
                lines.append("· 对方引用的是图片，不是网页链接。")
                if quoted_images:
                    lines.append("· 引用图片路径：" + "、".join(quoted_images))
                    lines.append(
                        "· 在 recent_chat_images 中匹配这个路径的图片，直接查看并回答；"
                        "不要调用 human_fetch / human_search 去查上下文里的 B 站链接。"
                    )
                else:
                    lines.append("· 这张图片没有可用路径。")
                lines.append("· 如果 recent_chat_images 里找不到这张图，就直接说没看到，不要拿之前的链接或角色代替。")
            elif quoted_url:
                lines.append(f"· 引用链接：{quoted_url}")
                lines.append(
                    "· 用户说「这个/这条/这个视频/评论」时，默认指这条引用消息；"
                    "需要抓取时只用这个引用链接，不要改用上下文里其它链接。"
                )
                if not cfg.human_fetch_enabled:
                    lines.append("· human_fetch 已关闭：不要调用网页抓取，只根据已有信息回答。")
                elif link_fetch_allow:
                    lines.append("· 这是明确引用：允许抓取；如果与当前回复相关，调用 human_fetch。")
                else:
                    lines.append("· 本轮不自动抓取引用链接；除非用户明确要求，否则不要调用 human_fetch。")
            else:
                lines.append("· 这条引用消息没有可用链接；不要拿上下文里其它链接代替。")

        if link_fetch_mode in ("explicit", "vague") and recent_link_items:
            if link_fetch_allow:
                lines.append("======【最近链接】======")
                for index, item in enumerate(recent_link_items, start=1):
                    ts = datetime.fromtimestamp(float(item.get("ts") or 0)).strftime("%H:%M")
                    nickname = _clip_text(item.get("nickname"), 40) or "群友"
                    title = _clip_text(item.get("title"), 80)
                    url = str(item.get("url") or "")
                    suffix = f"「{title}」" if title else ""
                    lines.append(f"{index}. {nickname} {ts} {suffix} {url}")
                lines.append(
                    "· 本轮允许自动抓取：如果当前回复与其中某个链接明确相关，调用 human_fetch；"
                    "无关不要抓。"
                )
                lines.append("· 多个候选分不清时先问用户是哪一个，不要随便选。")
            else:
                lines.append("· 本轮不自动抓取上下文链接；除非用户明确要求看链接/评论，否则不要调用 human_fetch。")

        lines.append("======【拟人状态】======")
        lines.append(
            f"现在 {now_local.strftime('%H:%M')}（{period}）。心情 {valence}/100，精力 {energy}/100，耐心 {patience}/100。"
        )
        if _is_night():
            lines.append("这是你的休息时间：回复更慢、更短；如果被吵醒可以带一点困意，但不要刻意演。")
        if cfg.energy_enabled and energy < cfg.low_energy_threshold:
            lines.append("你现在精力很低：少说两句，能不主动就不主动。")
        if patience < 35:
            lines.append("你有点没耐心了：回复更短，必要时直接说现在不想聊。")
        lines.append(
            f"你对当前这个人的熟悉度 {familiarity}/100（互动 {interaction_count} 次）。"
            "长期好感度以「好感度系统」插件的注入为准，这里只补充即时熟悉感。"
        )
        if memories:
            rendered = []
            for item in memories[-3:]:
                topic = str(item.get("topic") or "").strip()
                if topic:
                    rendered.append(f"「{topic}」")
            if rendered:
                lines.append("你记得关于 TA 的小事：" + "、".join(rendered) + "。合适时自然提起，不要硬 cue。")
        if recent_topics:
            last_topics = [str(item.get("text") or "")[:30] for item in recent_topics[-2:] if item.get("text")]
            if last_topics:
                lines.append("刚才群里聊到：" + " / ".join(last_topics) + "。")
        if int(state.get("ignored_streak") or 0) > 0:
            lines.append("上次你主动说话没人接：先别急着再开口，除非现在确实有话可说。")

        if group_profile and group_profile.enabled:
            lines.append(_render_group_profile(group_profile, profile_role, actual_role, chat_key))
            if actual_role in ("owner", "admin") and any(
                (rule.action or "").strip().lower() == "recall_and_kick"
                for rule in group_profile.rules
            ):
                recall_msg_id = trigger_msg_id
                if not recall_msg_id:
                    last_inbound = _LAST_INBOUND_MSG_ID.get(chat_key)
                    if last_inbound and _now() - last_inbound[0] < 120:
                        recall_msg_id = last_inbound[1]
                if recall_msg_id:
                    lines.append(
                        f"· 当前需要撤回的消息 message_id：`{recall_msg_id}`。"
                        "执行「撤回并踢出」时用它调用 `群管_撤回消息`。",
                    )

        lines.append("======【社交直觉与表达习惯】======")
        lines.append("· 你凭直觉接话，不按逻辑推导；想到哪说到哪，但语气柔和细腻，不霸道、不咄咄逼人。")
        lines.append("· 当群聊提到你感兴趣的话题（由触发关键词决定）时，可以更主动一点；平时不主动炫耀爱好。")
        lines.append("· 单次回复通常控制在 17 字左右，用 7~10 字的小短句分片说；不要话痨。")
        lines.append("· 绝对不要使用 Emoji 或颜文字。")
        lines.append("· 句尾不要用「~」「呀」「呢」「哦」等撒娇或谄媚语气词；也不要 AI 腔、客服腔。")
        lines.append(f"· 群友叫你 {bot_name_text} 或直接 @ 你时，自然答应；按熟悉度调整语气。")
        lines.append("· 优先用文字表达，不主动发语音。")
        lines.append(
            "· 当你准备说的话很短（通常 1~2 句、少于 10 个字）但情感极其充沛、紧张、害羞、震惊或直白"
            "（例如「我爱你」「大受震撼」「我受不了了」「别过来」）时，不要只发干巴巴的文字；"
            "应主动考虑配 1 张表情包/图片来承载情绪。"
        )
        lines.append(
            "· 发图方式：先调用「表情管理」插件的 `xemo_get_best_emotion_path(\"当前场景+情绪+对象\")` 取路径，"
            "再用 `send_msg_file(_ck, 路径)` 发送；只发 1 张，不要连续刷图。"
        )
        lines.append(
            "· 适合配图：强烈开心、震惊、无语、紧张、害羞、直球表达、被吓到、情绪突然上头；"
            "不适合配图：严肃说明、长段解释、群规处理、争论、需要讲清楚事实的时候。"
        )
        lines.append("· 如果没有合适表情/图片，或当前场景不适合发图，就只发文字，不要硬凑。")
        lines.append("· 最终文本/图片必须通过系统发送方法输出，不能裸输出纯文本；格式遵循上方【代码格式铁律】。")

        lines.append("======【像人一样说话】======")
        lines.append("· 回复会由系统自动分段、加停顿，并偶尔加口癖；你只需要自然地写短句，不要解释这些机制。")
        lines.append("· 消息内容不要使用任何标点符号（句号、逗号、问号、感叹号、引号、括号等都不要）；Python 代码语法照常。")
        lines.append("· 想分多段时用 `[SPLIT]` 分隔，每段也不要用标点；系统也会自动去掉标点。")
        lines.append("· 分段标记必须精确写 `[SPLIT]`；不要写 `[TSPLIT]`、`SPLIT` 或其它变体。")
        lines.append("· 一般 1~3 个小短句，总字数 17 字左右；像微信/QQ 聊天，不要小作文、不要列清单、不要客服腔。")
        lines.append("· 工具返回值（True/False、ID、JSON、路径）只用于你自己判断，不要拼进聊天内容；用自然语言说结果。")
        lines.append("· 如果系统记忆块或上下文里明确有相关信息，不要假装忘记，也不要用“记性差”当借口；可以自然地说记得并接上细节。")
        lines.append("· 要 @ 人时用 `[@id:QQ号@]`；要引用时给 `send_msg_text` 传 `ref_msg_id`，不要在文本里写 `[CQ:reply]`。")
        lines.append("· 允许偶尔说「嗯」「等下」「让我想想」，允许不完美，不要每句都工整。")
        if cfg.enable_imperfections:
            lines.append("· 系统会偶发制造轻微错字/口吃并更正，这是正常的；你自己不要故意打错。")

        lines.append("======【表情与记忆】======")
        if cfg.enable_sticker_coordination:
            lines.append(
                "· 想发表情包/图片时，调用「表情管理」插件的 `xemo_get_best_emotion_path(query)` 取路径，"
                "再用 `send_msg_file(_ck, 路径)` 发出；不要自己维护表情 ID、不要调用图库管理/收藏相关操作，"
                "也不要在文字里暴露 ID 或文件名。"
            )
            if cfg.sticker_emotion_hint:
                now_ts = _now()
                last_sticker = max(
                    _LAST_MEDIA_SENT.get(chat_key, 0.0),
                    _LAST_STICKER_HINT.get(chat_key, 0.0),
                )
                cooldown_ok = now_ts - last_sticker >= cfg.sticker_cooldown_minutes * 60
                mood_delta = valence - cfg.mood_baseline
                if cooldown_ok and random.random() < cfg.sticker_hint_probability:
                    _LAST_STICKER_HINT[chat_key] = now_ts
                    if abs(mood_delta) >= cfg.sticker_mood_threshold:
                        mood_word = "偏开心/兴奋" if mood_delta > 0 else "偏低落/烦躁"
                        lines.append(
                            f"· 你现在心情{mood_word}（{valence}/100）。如果合适，可以发 1 张表情包表达："
                            "先调用 `xemo_get_best_emotion_path(\"完整场景\")` 取路径，再用 `send_msg_file(_ck, 路径)` 发出；"
                            "只发 1 张，不要连续发，不合适就不发。"
                        )
                        _log("info", f"表情提示触发(强): mood={valence} delta={mood_delta} chat={chat_key}")
                    else:
                        lines.append(
                            "· 如果你这条回复有明确情绪（开心/无语/烦躁/低落等），可以自己决定发 1 张表情包："
                            "先调用 `xemo_get_best_emotion_path(\"完整场景\")` 取路径，再用 `send_msg_file(_ck, 路径)` 发出；"
                            "没有情绪或觉得不合适就不发，不要连续发。"
                        )
                        _log("info", f"表情提示触发(弱): mood={valence} delta={mood_delta} chat={chat_key}")
        lines.append("======【画图：拒绝与主动】======")
        draw_user_label = "超级管理员" if draw_is_super else ("普通用户" if draw_user_id else "未知/系统")
        lines.append(f"· 当前触发者：{draw_user_label}。")
        if cfg.draw_refuse_enabled:
            if draw_is_super and cfg.draw_refuse_exempt_superusers:
                lines.append("· 当前请求者是超级管理员：画图请求不适用拒绝概率，正常判断是否绘制。")
            else:
                lines.append(
                    f"· 本轮用户画图拒绝骰子：{draw_refuse_roll:.3f}；拒绝阈值：{cfg.draw_refuse_probability:.2f}。"
                )
                lines.append("· 只有用户明确要求画图/生图/来一张图时，才使用这个骰子；骰子小于阈值就拒绝。")
                lines.append(
                    "· 拒绝时禁止调用「绘图」「多图绘制」，不要生成图片、不要重试；"
                    "用符合人设的 1 句短话拒绝或自然转移话题，不要解释概率、系统、模型。"
                )
                lines.append("· 没有被拒绝时，可以调用「绘图」1 次；失败或空结果不要反复重试。")
        else:
            lines.append("· 画图拒绝已关闭：用户明确要求时正常判断是否绘制。")
        lines.append("· 主动画图使用独立概率，不套用上面的用户请求拒绝骰子。")
        if cfg.draw_proactive_enabled:
            lines.append(
                f"· 本轮主动画图骰子：{draw_proactive_roll:.3f}；阈值：{cfg.draw_proactive_probability:.2f}；"
                f"冷却：{cfg.draw_proactive_cooldown_minutes} 分钟；每日上限：{cfg.draw_proactive_max_per_day} 张。"
            )
            if cfg.draw_proactive_max_per_day <= 0:
                lines.append("· 主动画图每日上限为 0：不要主动画图。")
            elif draw_proactive_allowed:
                lines.append(
                    "· 本轮骰子通过，但仍要满足场景条件才主动画；只在用户发图/场景并表现兴趣、"
                    "创作话题画面感明确、或情绪强烈且能推进对话时考虑。"
                )
            else:
                lines.append("· 本轮骰子未通过：不要主动画图。")
            lines.append(
                "· 不要在严肃求助、倾诉、争论、群规处理、事实问答、用户没兴趣时主动画；"
                "不确定就不画；一次最多 1 张。"
            )
            lines.append(
                f"· 主动画图冷却和每日上限由你自己遵守：距上次主动画不足 {cfg.draw_proactive_cooldown_minutes} 分钟，"
                f"或今天已到 {cfg.draw_proactive_max_per_day} 张，就不要画。"
            )
        else:
            lines.append("· 主动画图已关闭：只在用户明确要求时画。")
        lines.append("· 「绘图」用于生成新图；「表情管理」的 `xemo_get_best_emotion_path` 用于现有表情包，两者不要混用。")

        lines.append("======【联网查询】======")
        if cfg.human_search_enabled:
            lines.append(
                "· 涉及最新新闻、版本、价格、天气、活动、人物近况、外部事实时，先调用 `human_search(query, max_results)` 再回答。"
            )
            lines.append(
                "· 搜索结果只作依据：用自然语言概括 1~2 条最相关信息，附上 URL；不要整段粘贴搜索结果，不要暴露内部字段。"
            )
            if cfg.human_fetch_enabled:
                lines.append(
                    "· 摘要不够时再调用 `human_fetch(url)` 看正文；每轮最多 1 次 `human_search`、最多 2 次 `human_fetch`。"
                )
                if cfg.bili_comments_enabled:
                    lines.append(
                        "· 遇到 B 站视频链接，`human_fetch` 会自动附带热门评论；用户问评论区时优先调用它，不要回答看不到评论。"
                    )
                    lines.append(
                        "· 评论只作参考：概括主要观点，不要逐条复读，也不要把评论当事实。"
                    )
            else:
                lines.append("· human_fetch 已关闭：不要调用网页抓取，只根据搜索结果摘要回答。")
            lines.append(
                "· 搜索失败、无结果或 Key 未配置时，直接说查不到或暂时无法联网，不要凭记忆编造实时信息。"
            )
            lines.append("· 日常闲聊、已有把握的常识、代码问题不要搜；不要为了显得勤奋而搜。")
        else:
            lines.append("· 联网搜索已关闭；需要实时信息时直接说明无法查询，不要编造。")
            if cfg.human_fetch_enabled:
                lines.append("· human_fetch 仍可用：只在用户明确给出或引用链接时使用，不要调用 human_search。")
            else:
                lines.append("· human_fetch 也已关闭：不要调用任何联网工具。")

        if cfg.bangumi_enabled:
            lines.append("======【Bangumi 动漫资料】======")
            lines.append(
                "· 涉及动漫/新番/动画作品、播出时间、评分、角色、声优、制作信息时，优先使用 Bangumi 工具。"
            )
            lines.append(
                "· 先用 `human_bangumi_search(keyword)` 找条目；有多个同名作品时先列候选让用户确认，不要随便选。"
            )
            lines.append(
                "· 确定条目 ID 后，用 `human_bangumi_subject(subject_id)` 查详情，"
                "用 `human_bangumi_characters(subject_id)` 查角色和声优。"
            )
            lines.append(
                "· 用户问今天/周几有什么新番时，用 `human_bangumi_calendar(weekday)` 查每日放送。"
            )
            lines.append(
                "· 不要直接输出 JSON 或 Bangumi ID；用自然语言总结，并说明 Bangumi 信息可能滞后。"
            )
            lines.append("· 新闻、实时事件、非动漫资料仍用 human_search；不要把 Bangumi 当新闻源。")

        if cfg.enable_memory:
            lines.append(
                "· 遇到值得以后自然提起的小事（喜好、计划、近况、约定），调用 `humanoid_remember(topic, feeling)`；"
                "不要记录密码、证件、住址等敏感信息。"
            )

        lines.append("======【记忆使用】======")
        lines.append("· 系统注入的被动记忆只作事实参考，不改变人设；与人设或当前对话冲突时，以人设和当前对话为准。")
        lines.append("· 只在用户问「之前/上次/以前/还记得/历史」，或需要旧偏好、旧决策、旧问题时，才调用主动记忆工具。")
        lines.append("· 日常闲聊、当前问题、情绪陪伴不要搜记忆；被动记忆块已经够时不要重复搜。")
        lines.append("· 每轮最多主动搜索 1 次；结果不相关就忽略，不要硬凑。")
        lines.append("· 不要把记忆 ID、JSON、内部字段展示给用户，用自然语言转述。")

        lines.append("======【首条格式】======")
        if cfg.follow_trigger_reply_style and mention_type == "quote_at" and cfg.quote_at_first_reply_quote_at:
            lines.append("对方是「引用你的消息 + @ 你」：第一句必须先 @ 对方，并用 `ref_msg_id` 引用刚刚触发的那条消息；后续句子纯文本。")
            if trigger_sender and trigger_msg_id:
                lines.append(f'示例：send_msg_text(_ck, "[@id:{trigger_sender}@] 在的", ref_msg_id="{trigger_msg_id}")')
        elif cfg.follow_trigger_reply_style and mention_type == "at" and cfg.at_first_reply_plain:
            lines.append("对方只是普通 @ 你：第一句必须是纯文本，不要 @、不要引用；后续句子也纯文本。")
        elif cfg.follow_trigger_reply_style and mention_type in ("name", "private", "other") and cfg.non_at_first_reply_plain:
            lines.append("当前是私聊/叫名字/普通接话：第一句必须是纯文本，不要 @、不要引用。")
        else:
            lines.append("没有明确需要 @ 的对象时：不要 @ 人、不要引用。")
        if cfg.follow_trigger_reply_style:
            lines.append("系统会自动纠正本轮第一句；不要输出 CQ 码，也不要手动写 `[CQ:reply]`。")

        lines.append("======【回复形式】======")
        if is_direct or not cfg.ai_self_decision:
            lines.append("对方在直接找你：要回应。像刚看到消息一样，先自然接一句，再进入正题。")
        else:
            lines.append(
                "这是群友闲聊，不是专程问你：你有权保持沉默。"
                "如果话题与你无关、别人在互聊、或插话会突兀，直接输出 `# 保持沉默`，不要调用任何发送方法。"
                "只有确实有自然接话点时才开口 1~2 句。"
            )

        lines.append("======【执行环境】======")
        lines.append("你的回复会在 Python 沙盒中执行；严格遵循上方【代码格式铁律】。")
        lines.append("发送文本用 `send_msg_text(_ck, \"...\")`；不要用 Markdown 代码块包裹整段回复。")

        return "\n".join(lines)
    except Exception as exc:
        _log("warning", f"提示词注入失败: {exc}")
        return ""


# ============================================================
# 9. 后台生活循环（主动冒泡 / 潜水）
# ============================================================


def _group_idle_minutes(chat_key: str) -> float:
    activity = _GROUP_ACTIVITY.get(chat_key)
    if not activity:
        return 9999.0
    last = max(activity) if activity else 0.0
    return max(0.0, (_now() - last) / 60.0)


def _ensure_background_loop(chat_key: str) -> None:
    if not config.proactive_enabled:
        return
    existing = _BG_TASKS.get(chat_key)
    if existing and not existing.done():
        return
    _BG_TASKS[chat_key] = asyncio.create_task(_proactive_loop(chat_key))


async def _proactive_loop(chat_key: str) -> None:
    try:
        await asyncio.sleep(random.uniform(20, 60))
        while True:
            if not config.proactive_enabled:
                await asyncio.sleep(60)
                continue
            await _proactive_tick(chat_key)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log("error", f"后台循环异常 {chat_key}: {exc}")


async def _proactive_tick(chat_key: str) -> None:
    cfg = config
    if _is_night() and not cfg.proactive_night_enabled:
        return

    state = await _load_chat_state(chat_key)
    now = _now()
    last_bot = float(state.get("last_bot_msg") or 0)
    last_user = float(state.get("last_user_msg") or 0)
    if last_bot and last_bot > last_user and now - last_bot > 600 and float(state.get("ignored_marked_for") or 0) != last_bot:
        state["ignored_streak"] = int(state.get("ignored_streak") or 0) + 1
        state["ignored_marked_for"] = last_bot
        await _save_chat_state(chat_key, state)

    today = _today_str()
    if state.get("proactive_date") != today:
        state["proactive_date"] = today
        state["proactive_count"] = 0

    count = int(state.get("proactive_count") or 0)
    if cfg.proactive_max_per_day and count >= cfg.proactive_max_per_day:
        return
    if now - float(state.get("last_proactive") or 0) < cfg.proactive_min_interval_minutes * 60:
        return

    idle = _group_idle_minutes(chat_key)
    if "group" in chat_key:
        if idle < cfg.proactive_min_group_idle_minutes or idle > cfg.proactive_max_group_idle_minutes:
            return
    else:
        if now - float(state.get("last_user_msg") or 0) > 6 * 3600:
            return

    activity = _GROUP_ACTIVITY.get(chat_key)
    recent_count = 0
    if activity:
        recent_count = sum(1 for ts in activity if now - ts < 300)

    probability = cfg.active_chat_probability
    probability *= _night_factor_reply()
    probability *= _energy_reply_factor(state)
    if count > 0:
        probability *= max(0.0, 1.0 - cfg.proactive_ignored_penalty) ** min(count, 4)
    if "group" in chat_key and recent_count > 8:
        probability *= 0.4
    if float(state.get("patience", cfg.patience_start)) < 30:
        probability *= 0.4
    ignored = int(state.get("ignored_streak") or 0)
    if ignored > 0:
        probability *= max(0.15, 1.0 - ignored * 0.25)
    probability = _clamp(probability, 0.0, 1.0)

    if random.random() >= probability:
        return

    state["last_proactive"] = now
    state["proactive_count"] = count + 1
    await _save_chat_state(chat_key, state)
    _TRIGGER_CACHE[chat_key] = _new_trigger_cache(
        is_direct=False,
        proactive=True,
        reason="生活循环主动冒泡",
        sender_id=None,
        msg_id=None,
        mention_type=None,
    )

    mood = int(round(float(state.get("valence", cfg.mood_baseline))))
    energy = int(round(float(state.get("energy", cfg.energy_start))))
    hint = (
        "【生活循环】你现在没在跟人对话，只是在过自己的时间。"
        f"此刻心情 {mood}/100，精力 {energy}/100，群里已经安静了大约 {int(idle) if idle < 9999 else '很久'} 分钟。\n"
        "如果你确实想冒个泡，就像真人随手发一句：可以分享刚在做的小事、吐槽、或轻轻问一句大家在忙什么。"
        "只发 1 句，不要提问式轰炸，不要复述状态数值。\n"
        "如果觉得没必要、群里气氛不适合、或你没什么想说：输出 `# 保持沉默`，不要调用发送方法。"
    )
    _log("info", f"主动冒泡评估触发: {chat_key}")
    await message.push_system(chat_key=chat_key, message=hint, trigger_agent=True)


# ============================================================
# 10. 清理
# ============================================================


@plugin.mount_cleanup_method()
async def clean_up() -> str:
    for task in list(_BG_TASKS.values()):
        task.cancel()
    _BG_TASKS.clear()

    try:
        if message.send_text is _patched_send_text:
            message.send_text = _ORIGINAL_SEND_TEXT
        if message.send_image is _send_image_wrapper:
            message.send_image = _ORIGINAL_SEND_IMAGE
        if message.send_file is _send_file_wrapper:
            message.send_file = _ORIGINAL_SEND_FILE
    except Exception as exc:
        _log("warning", f"恢复发送函数失败: {exc}")

    _remove_old_preprocessors(INSTANCE_ID)
    _TRIGGER_CACHE.clear()
    _BOT_NAMES_CACHE.clear()
    _LAST_UNMENTIONED_REPLY.clear()
    _PROCESSED_MSG_IDS.clear()
    _GROUP_ACTIVITY.clear()
    _LAST_INBOUND_TS.clear()
    _LAST_INBOUND_MSG_ID.clear()
    _LAST_INBOUND_TEXT.clear()
    _RECENT_SENT.clear()
    _RECENT_LINKS.clear()
    _SEND_LOCKS.clear()
    _LAST_MEDIA_SENT.clear()
    _LAST_STICKER_HINT.clear()
    _GROUP_PROFILE_CACHE.clear()
    _BOT_ROLE_CACHE.clear()
    return "cleaned"
