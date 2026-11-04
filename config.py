# -*- coding: utf-8 -*-
"""
========================================================
config.py —— ftb-bate 配置文件（SNBT 输出版 · 白板）
========================================================
只需改这个文件，主程序不用动。
数据文件直接读取 IdDumper 模组导出的 JSON。
输出为 FTB Quests 1.20.1 原生 .snbt 文件。

【白板说明】
- 所有需要你填写的值都留空或保持占位。
- 带 【TODO】 的项必须按你的整合包填写。
- 带 【可选】 的项不填也能跑，但建议按需配置。

【重要约束 —— 防 FTB isExcludedByOtherQuestline 递归崩溃】
1. CHAPTER_GROUPS 里每个 group.title 必填且全局唯一，禁止空字符串。
2. CHAPTER_GROUPS[0].chapters[0].title 必须与 PACK_INTRO_CHAPTER_TITLE 完全一致。
3. COLS_PER_ROW 必须 ≥ 1，COL_SPACING / ROW_SPACING 必须 > 0。
4. 不要往 DIFFICULTY_TIERS 里加 reward_tables_ref（本工具用内嵌奖励）。
5. 生成端会强制单前置 + 严格链式，避免"分支合并"触发 FTB 排除判定 bug。
6. PROGRESSION_MODE 建议保持 linear，flexible 会启用排除判定逻辑。
========================================================
"""
import os

# ==================== 路径 ====================
# 【TODO】改成你导出文件所在的目录
# 手机示例："/storage/emulated/0/Download/py/dumpids"
# PC 示例：  r"D:\mc\dumpids"
BASE_DIR = ""

MODLIST_FILE      = os.path.join(BASE_DIR, "modlist.json")
ITEMS_FILE        = os.path.join(BASE_DIR, "items.json")
STRUCTURES_FILE   = os.path.join(BASE_DIR, "structures.json")
ENTITIES_FILE     = os.path.join(BASE_DIR, "entities.json")

OUTPUT_DIR          = os.path.join(BASE_DIR, "output")
CHAPTERS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "chapters")

# 【可选】日志文件路径，留空则用 "logs/ftb_bate.log"
LOG_FILE = os.path.join(BASE_DIR, "logs", "ftb_bate.log")


# ==================== API ====================
# 【TODO】填入你的 API Key，或通过环境变量 DEEPSEEK_API_KEY 提供
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL    = os.environ.get("LLM_MODEL", "deepseek-chat")


# ==================== 随机种子 ====================
# 【可选】固定整数可复现生成结果；None 表示每次随机
RANDOM_SEED = None


# ==================== MC 百科补充（模组级攻略） ====================
# 【修改】先关闭 MC百科 查询：当前 MCMOD_KEYWORD_MAP 为空，
# 开启会为每个模组发请求，最多阻塞 80 秒且大概率查不到东西。
# 等填好 MCMOD_KEYWORD_MAP 后再改成 True。
ENABLE_MCMOD_LOOKUP = False
MCMOD_API_BASE      = "https://search.mcmod.cn/s"
MCMOD_TIMEOUT       = 10
MCMOD_MAX_LOOKUP    = 8
MCMOD_CACHE_FILE    = os.path.join(BASE_DIR, "mcmod_cache.json")

# 【TODO】modid -> 模组中文名，提升 MC百科 查询命中率
MCMOD_KEYWORD_MAP = {
    # "example_modid": "模组中文名",
}


# ==================== 语言 ====================
# "zh" 或 "en"
QUEST_LANGUAGE = "zh"


# ==================== 任务书整体介绍 ====================
PACK_INTRO = (
    ""
)


# ==================== 进度模式 ====================
# 【修改】新增。FTB Quests 的 progression_mode。
#   "linear"   —— 推荐，任务按链式顺序完成，不会触发排除判定递归。
#   "flexible" —— FTB 默认，会启用任务排除判定（isExcludedByOtherQuestline），
#                 在任务图存在分支合并时可能无限递归导致 StackOverflowError。
# 主程序默认读 "linear"，这里显式写出方便查看和修改。
PROGRESSION_MODE = "linear"


# ==================== 整合包介绍章节 ====================
# 【TODO】是否生成介绍章节
GENERATE_PACK_INTRO = True

# 约束：PACK_INTRO_CHAPTER_TITLE 必须与 CHAPTER_GROUPS[0].chapters[0].title 完全一致
PACK_INTRO_CHAPTER_TITLE  = "整合包介绍"
PACK_INTRO_CHAPTER_FOCUS  = (
    "向玩家介绍本整合包的核心主题、主要玩法、推荐游玩顺序。"
    "任务以 checkmark 为主，让玩家读完介绍后点击确认即可。"
)
PACK_INTRO_CHAPTER_ICON   = "minecraft:book"
PACK_INTRO_TASK_COUNT     = 3

# 约束：必须与 CHAPTER_GROUPS[0].title 完全一致
PACK_INTRO_GROUP_TITLE    = "整合包介绍"


# ==================== 生成规模 ====================
TASKS_PER_CHAPTER = 55
BATCH_SIZE        = 10
FILE_RETRY        = 5

# 【可选】每章默认批次数与单次 AI 输出上限
DEFAULT_BATCHES_PER_CHAPTER = 3
MAX_TOKENS = 8000


# ==================== 坐标布局 ====================
# 约束：COLS_PER_ROW ≥ 1，COL_SPACING > 0，ROW_SPACING > 0
# 否则任务坐标重叠，会退化 FTB 的任务线视图判定，触发 isExcludedByOtherQuestline 递归
COLS_PER_ROW = 6
COL_SPACING  = 2.0
ROW_SPACING  = 1.5
START_X      = 0.0
START_Y      = 0.0


# ==================== 章节图标 ====================
ICON_FALLBACK = "minecraft:book"


# ==================== ▼ 难度奖励配置 ====================
ENABLE_DIFFICULTY_REWARDS = True

# 注意：不要往每个 tier 里加 reward_tables_ref
# 本工具使用"内嵌奖励"，不依赖 reward_tables
DIFFICULTY_TIERS = {
    "trivial": {
        "weight_range": (1, 2),
        "item_count_range": (1, 2),
        "description": "简单任务",
    },
    "easy": {
        "weight_range": (2, 4),
        "item_count_range": (2, 4),
        "description": "普通任务",
    },
    "medium": {
        "weight_range": (3, 6),
        "item_count_range": (3, 6),
        "description": "中等任务",
    },
    "hard": {
        "weight_range": (5, 10),
        "item_count_range": (5, 10),
        "description": "困难任务",
    },
    "extreme": {
        "weight_range": (8, 16),
        # 【修改】原为 (8, 20)，压低到 (8, 10) 降低登录同步负载，
        # 间接减少排除判定遍历量。
        "item_count_range": (8, 10),
        "description": "极限任务",
    },
}

# 只保留 FTB Quests 原生支持的四种任务类型
TASK_TYPE_DIFFICULTY = {
    "checkmark":   1,
    "item":        2,
    "kill":        3,
    "structure":   4,
}

COUNT_DIFFICULTY_FACTOR = 0.3
DEP_DEPTH_WEIGHT = 0.5

# 【可选】稀有模组前缀，命中后难度 +1
RARE_MOD_PREFIXES = [
    # "botania",
    # "draconicevolution",
    # "mekanism",
    # "ae2",
]

REWARD_FALLBACK_POOL = [
    "minecraft:emerald",
    "minecraft:diamond",
    "minecraft:gold_ingot",
    "minecraft:iron_ingot",
    "minecraft:experience_bottle",
    "minecraft:elytra",
    "minecraft:enchanted_golden_apple",
]
# ==================== ▲ 难度奖励配置 ====================


# ==================== 章节组配置 ====================
# 【TODO】按你的整合包填写。
#
# 【强制约束】
#   1. 每个 group.title 必填且全局唯一，禁止空字符串
#   2. CHAPTER_GROUPS[0].chapters[0].title 必须 == PACK_INTRO_CHAPTER_TITLE
#   3. 每个 chapter 的 title 在同一 group 内建议唯一
#   4. AI 生成的依赖 key 只在组内有效，跨组依赖会被丢弃
#   5. 生成端强制严格链式，task 图无分支合并节点
#
# 每章字段:
#   title            章节标题
#   focus            本章主题描述
#   extra            整体要求描述
#   item_prefixes    物品模组前缀列表（空列表 = 使用全物品池）
#   entity_prefixes  实体模组前缀列表（空列表 = 使用全实体池）
#   use_structures   是否使用 structure 任务
#   task_types       本章允许的任务类型
#   icon             章节图标物品 ID
#   batches          本章生成几个批次（默认 1，主程序当前未读取此字段）
CHAPTER_GROUPS = [
    {
        # 组 0：整合包介绍（必填、唯一）
        "title": "整合包介绍",
        "chapters": [
            {
                "title": "整合包介绍",   # 必须与 PACK_INTRO_CHAPTER_TITLE 完全一致
                "focus": "整合包核心玩法与主要模组介绍",
                "extra": "",
                "item_prefixes": [],
                "entity_prefixes": [],
                "use_structures": False,
                "task_types": ["checkmark"],
                "icon": "minecraft:book",
                "batches": 1,
            },
        ],
    },
    {
        # 组 1：主线（必填、唯一）—— 【TODO】按你的整合包填写
        "title": "主线",
        "chapters": [
            {
                "title": "",          # 【TODO】章节标题
                "focus": "",          # 【TODO】本章主题
                "extra": "",          # 【可选】额外要求
                "item_prefixes": [],  # 【可选】限定的模组前缀
                "entity_prefixes": [],
                "use_structures": False,
                "task_types": ["item", "checkmark"],
                "icon": "",           # 【可选】留空则用 ICON_FALLBACK
                "batches": 1,
            },
        ],
    },
]


# ==================== 奖励物品黑名单 ====================
REWARD_ITEM_BLACKLIST = [
    "minecraft:air", "minecraft:barrier", "minecraft:structure_void",
    "minecraft:command_block", "minecraft:chain_command_block",
    "minecraft:repeating_command_block", "minecraft:debug_stick",
    "minecraft:bedrock", "minecraft:light", "minecraft:structure_block",
    "minecraft:jigsaw", "minecraft:knowledge_book",
]

# 【可选】按关键词排除奖励物品
REWARD_ITEM_BLACKLIST_KEYWORDS = []


# ==================== 辅助函数 ====================
def flatten_chapters():
    """把 CHAPTER_GROUPS 展平为章节列表，附带组索引。"""
    flat = []
    for gi, group in enumerate(CHAPTER_GROUPS):
        for ci, ch in enumerate(group["chapters"]):
            ch = dict(ch)
            ch["_group_index"] = gi
            ch["_chapter_in_group"] = ci
            flat.append(ch)
    return flat


TOTAL_CHAPTERS = len(flatten_chapters())
CHAPTER_TITLES = [ch["title"] for ch in flatten_chapters()]


# ==================== 配置自检（import 时自动执行） ====================
def _validate_config():
    """在 import 时检查关键约束，提前暴露会导致 FTB 崩溃的配置。"""
    errors = []
    warns = []

    # 1. 组标题唯一且非空
    titles = []
    for gi, g in enumerate(CHAPTER_GROUPS):
        t = g.get("title", "")
        if not t:
            errors.append(f"CHAPTER_GROUPS[{gi}].title 为空，必须填写唯一的组标题")
        if t in titles:
            errors.append(f"章节组标题重复: '{t}'（组 {gi}），多个组不能共用同一标题")
        titles.append(t)

    # 2. 介绍章对齐
    if GENERATE_PACK_INTRO:
        if not CHAPTER_GROUPS or not CHAPTER_GROUPS[0].get("chapters"):
            errors.append("GENERATE_PACK_INTRO=True 但 CHAPTER_GROUPS[0] 没有章节")
        else:
            first_title = CHAPTER_GROUPS[0]["chapters"][0].get("title", "")
            if first_title != PACK_INTRO_CHAPTER_TITLE:
                errors.append(
                    f"CHAPTER_GROUPS[0].chapters[0].title = '{first_title}' "
                    f"与 PACK_INTRO_CHAPTER_TITLE = '{PACK_INTRO_CHAPTER_TITLE}' 不一致"
                )
            if CHAPTER_GROUPS[0].get("title") != PACK_INTRO_GROUP_TITLE:
                errors.append(
                    f"CHAPTER_GROUPS[0].title = '{CHAPTER_GROUPS[0].get('title')}' "
                    f"与 PACK_INTRO_GROUP_TITLE = '{PACK_INTRO_GROUP_TITLE}' 不一致"
                )

    # 3. 坐标参数合法
    if COLS_PER_ROW < 1:
        errors.append(f"COLS_PER_ROW = {COLS_PER_ROW}，必须 ≥ 1")
    if COL_SPACING <= 0:
        errors.append(f"COL_SPACING = {COL_SPACING}，必须 > 0")
    if ROW_SPACING <= 0:
        errors.append(f"ROW_SPACING = {ROW_SPACING}，必须 > 0")

    # 4. 进度模式检查
    if str(PROGRESSION_MODE).lower() == "flexible":
        warns.append(
            "PROGRESSION_MODE = flexible 会启用 FTB 排除判定逻辑，"
            "存在 isExcludedByOtherQuestline 递归风险，建议改为 linear"
        )

    # 5. 章节自身检查
    for gi, g in enumerate(CHAPTER_GROUPS):
        for ci, ch in enumerate(g.get("chapters", [])):
            if not ch.get("title"):
                warns.append(f"CHAPTER_GROUPS[{gi}].chapters[{ci}].title 为空")

    # 6. 汇报
    if errors:
        print("\n[配置错误] 以下问题会直接导致 FTB Quests 崩溃或生成异常：")
        for e in errors:
            print(f"  ✗ {e}")
        raise SystemExit("[配置错误] 请先修复 config.py")
    if warns:
        print("\n[配置警告]")
        for w in warns:
            print(f"  ! {w}")


_validate_config()