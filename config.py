# -*- coding: utf-8 -*-
"""
========================================================
config.py —— ftb-bate 配置文件（IdDumper 模组适配版 · 白板）
========================================================
只需改这个文件，主程序不用动。
数据文件直接读取 IdDumper 模组导出的 JSON。

【白板说明】
- 所有需要你填写的值都留空或保持占位。
- 带 【TODO】 的项必须按你的整合包填写。
- 带 【可选】 的项不填也能跑，但建议按需配置。
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
REWARDS_OUTPUT_DIR  = os.path.join(OUTPUT_DIR, "reward_tables")

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
ENABLE_MCMOD_LOOKUP = True
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


# ==================== 模组 ID 前缀 ====================
# 【可选】自定义 modid 别名表，主程序当前未强制使用
MOD = {
    # "example": "example_modid",
}


# ==================== 任务书整体介绍 ====================
PACK_INTRO = (
    ""
)


# ==================== 整合包介绍章节 ====================
# 【TODO】是否生成介绍章节
GENERATE_PACK_INTRO = True
PACK_INTRO_CHAPTER_TITLE  = "整合包介绍"
PACK_INTRO_CHAPTER_FOCUS  = (
    "向玩家介绍本整合包的核心主题、主要玩法、推荐游玩顺序。"
    "任务以 checkmark 为主，让玩家读完介绍后点击确认即可。"
)
PACK_INTRO_CHAPTER_ICON   = "minecraft:book"
PACK_INTRO_TASK_COUNT     = 3
# 介绍章节所属组的标题（group 0）
PACK_INTRO_GROUP_TITLE    = "整合包介绍"


# ==================== 生成规模 ====================
TASKS_PER_CHAPTER = 55
BATCH_SIZE        = 10
FILE_RETRY        = 5


# ==================== 坐标布局 ====================
COLS_PER_ROW = 6
COL_SPACING  = 2.0
ROW_SPACING  = 1.5
START_X      = 0.0
START_Y      = 0.0


# ==================== 章节图标 ====================
ICON_FALLBACK = "minecraft:book"


# ==================== ▼ 难度奖励配置 ====================
ENABLE_DIFFICULTY_REWARDS = True

DIFFICULTY_TIERS = {
    "trivial": {
        "weight_range": (1, 2),
        "item_count_range": (1, 2),
        "reward_tables_ref": [],
        "description": "简单任务",
    },
    "easy": {
        "weight_range": (2, 4),
        "item_count_range": (2, 4),
        "reward_tables_ref": [],
        "description": "普通任务",
    },
    "medium": {
        "weight_range": (3, 6),
        "item_count_range": (3, 6),
        "reward_tables_ref": [],
        "description": "中等任务",
    },
    "hard": {
        "weight_range": (5, 10),
        "item_count_range": (5, 10),
        "reward_tables_ref": [],
        "description": "困难任务",
    },
    "extreme": {
        "weight_range": (8, 16),
        "item_count_range": (8, 20),
        "reward_tables_ref": [],
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

DIFFICULTY_TABLE_PREFIX = "diff"
# ==================== ▲ 难度奖励配置 ====================


# ==================== 章节组配置 ====================
# 【TODO】按你的整合包填写。
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
#   batches          本章生成几个批次（默认 1）
CHAPTER_GROUPS = [
    {
        "title": "",
        "chapters": [
            {
                "title": "",
                "focus": "",
                "extra": "",
                "item_prefixes": [],
                "entity_prefixes": [],
                "use_structures": False,
                "task_types": ["item", "checkmark"],
                "icon": "",
                "batches": 1,
            },
        ],
    },
]


# ==================== 奖励表定义（手写后备） ====================
REWARD_TABLES = {
    # "basic": {
    #     "title": "",
    #     "entries": [
    #         {"item": "", "count": 1, "weight": 1},
    #     ],
    # },
}


# ==================== 奖励物品自动构建 ====================
REWARD_AUTO_FROM_ITEMS = True
REWARD_TABLE_SIZE = 4
REWARD_ITEM_COUNT_RANGE = (1, 3)

# 【可选】按前缀限定各奖励池，主程序当前未强制使用
REWARD_TABLE_POOLS = {
    # "basic": [],
}

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