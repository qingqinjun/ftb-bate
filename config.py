# -*- coding: utf-8 -*-
"""
========================================================
config.py —— ftb-bate 配置文件（IdDumper 模组适配版）
========================================================
只需改这个文件，main.py 不用动。
数据文件直接读取 IdDumper 模组导出的 JSON。
========================================================
"""
import os

# ==================== 路径 ====================
# 【TODO】改成你 4 个导出文件所在的目录
# IdDumper 的导出文件在【存档目录/dumpids/】下
BASE_DIR = "/storage/emulated/0/Download/py/dumpids"

MODLIST_FILE      = os.path.join(BASE_DIR, "modlist.json")
ITEMS_FILE        = os.path.join(BASE_DIR, "items.json")
STRUCTURES_FILE   = os.path.join(BASE_DIR, "structures.json")
ENTITIES_FILE     = os.path.join(BASE_DIR, "entities.json")
ADVANCEMENTS_FILE = os.path.join(BASE_DIR, "advancements.json")   # 新增
FLUIDS_FILE       = os.path.join(BASE_DIR, "fluids.json")         # 新增

OUTPUT_DIR          = os.path.join(BASE_DIR, "output")
CHAPTERS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "chapters")
REWARDS_OUTPUT_DIR  = os.path.join(OUTPUT_DIR, "reward_tables")


# ==================== API ====================
API_KEY = os.environ.get("DEEPSEEK_API_KEY")

BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL    = os.environ.get("LLM_MODEL", "deepseek-chat")


# ==================== MC 百科补充（模组级攻略） ====================
ENABLE_MCMOD_LOOKUP = True
MCMOD_API_BASE      = "https://search.mcmod.cn/s"
MCMOD_TIMEOUT       = 10
MCMOD_MAX_LOOKUP    = 8
MCMOD_CACHE_FILE    = os.path.join(BASE_DIR, "mcmod_cache.json")

MCMOD_KEYWORD_MAP = {
    # "example_modid": "模组中文名",
}


# ==================== 语言 ====================
QUEST_LANGUAGE = "zh"


# ==================== 模组 ID 前缀 ====================
MOD = {
    # "example": "example_modid",
}


# ==================== 任务书整体介绍 ====================
PACK_INTRO = (
    "这是一个 Minecraft 整合包。"
)


# ==================== 整合包介绍章节 ====================
ENABLE_PACK_INTRO_CHAPTER = True
PACK_INTRO_CHAPTER_TITLE  = "整合包介绍"
PACK_INTRO_CHAPTER_FOCUS  = (
    "向玩家介绍本整合包的核心主题、主要玩法、推荐游玩顺序。"
    "任务以 checkmark 为主，让玩家读完介绍后点击确认即可。"
)
PACK_INTRO_CHAPTER_ICON   = "minecraft:book"
PACK_INTRO_TASK_COUNT     = 3


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
        "item_count_range": (8, 20),
        "description": "极限任务",
    },
}

TASK_TYPE_DIFFICULTY = {
    "checkmark":   1,
    "item":        2,
    "kill":        3,
    "structure":   4,
    "advancement": 3,   # 新增
    "fluid":       2,   # 新增
}

COUNT_DIFFICULTY_FACTOR = 0.3
DEP_DEPTH_WEIGHT = 0.5

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
        "title": "默认组",
        "chapters": [
            {
                "title": "第一章",
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
    "basic": {
        "title": "基础奖励",
        "entries": [
            {"item": "minecraft:iron_ingot", "count": 4, "weight": 30},
            {"item": "minecraft:gold_ingot", "count": 2, "weight": 20},
            {"item": "minecraft:emerald", "count": 1, "weight": 15},
            {"item": "minecraft:experience_bottle", "count": 2, "weight": 15},
        ],
    },
    "structure": {
        "title": "探索者宝箱",
        "entries": [
            {"item": "minecraft:diamond", "count": 2, "weight": 25},
            {"item": "minecraft:emerald", "count": 4, "weight": 20},
            {"item": "minecraft:netherite_scrap", "count": 1, "weight": 10},
            {"item": "minecraft:enchanted_golden_apple", "count": 1, "weight": 5},
        ],
    },
    "cultivation": {
        "title": "修炼者奖励",
        "entries": [
            {"item": "minecraft:emerald", "count": 3, "weight": 25},
            {"item": "minecraft:diamond", "count": 2, "weight": 20},
            {"item": "minecraft:experience_bottle", "count": 4, "weight": 20},
            {"item": "minecraft:gold_ingot", "count": 4, "weight": 15},
        ],
    },
    "endgame": {
        "title": "终局奖励",
        "entries": [
            {"item": "minecraft:netherite_ingot", "count": 1, "weight": 20},
            {"item": "minecraft:diamond_block", "count": 1, "weight": 15},
            {"item": "minecraft:enchanted_golden_apple", "count": 3, "weight": 10},
            {"item": "minecraft:nether_star", "count": 1, "weight": 5},
        ],
    },
}


# ==================== 奖励物品自动构建 ====================
REWARD_AUTO_FROM_ITEMS = True
REWARD_TABLE_SIZE = 4
REWARD_ITEM_COUNT_RANGE = (1, 3)

REWARD_TABLE_POOLS = {
    "basic":       ["minecraft"],
    "structure":   [],
    "cultivation": [],
    "endgame":     [],
}

REWARD_ITEM_BLACKLIST = [
    "minecraft:air", "minecraft:barrier", "minecraft:structure_void",
    "minecraft:command_block", "minecraft:chain_command_block",
    "minecraft:repeating_command_block", "minecraft:debug_stick",
    "minecraft:bedrock", "minecraft:light", "minecraft:structure_block",
    "minecraft:jigsaw", "minecraft:knowledge_book",
]

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