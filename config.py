# -*- coding: utf-8 -*-
"""
========================================================
config.py —— ftb-bate 配置文件（白板模板）
========================================================
只需改这个文件，main.py 不用动。
使用前请把下面所有 【TODO】 处填好。
========================================================
支持任务类型：item / checkmark / structure / kill
MC百科：仅作【模组级攻略补充】，不查具体物品
章节图标：自动校验，不在 items.json 则回退到 minecraft:book
整合包介绍：自动生成一个独立章节，放在所有章节组之前
========================================================
"""
import os

# ==================== 路径 ====================
# 【TODO】改成你放 4 个数据文件 + 脚本的目录
BASE_DIR = "/storage/emulated/0/Download/py"

MODLIST_FILE   = os.path.join(BASE_DIR, "modlist.txt")
ITEMS_FILE     = os.path.join(BASE_DIR, "items.json")
STRUCTURE_FILE = os.path.join(BASE_DIR, "structure_dump.txt")
ENTITIES_FILE  = os.path.join(BASE_DIR, "entities_list.json")

OUTPUT_DIR          = os.path.join(BASE_DIR, "output")
CHAPTERS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "chapters")
REWARDS_OUTPUT_DIR  = os.path.join(OUTPUT_DIR, "reward_tables")


# ==================== API ====================
# Key 只从环境变量读取，禁止写死在代码里
API_KEY = os.environ.get("DEEPSEEK_API_KEY")

# 默认 DeepSeek；想换 OpenAI 兼容端点或 Ollama 就改这两个环境变量
# 官方模型名：deepseek-chat / deepseek-reasoner
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL    = os.environ.get("LLM_MODEL", "deepseek-chat")


# ==================== MC 百科补充（模组级攻略） ====================
# 注意：MC 百科只做【模组级】攻略补充，不查具体物品 ID。
# 查询时用 modlist.txt 里的模组中文名 + ID 后半段拼接，命中模组页或攻略页。
ENABLE_MCMOD_LOOKUP = True
MCMOD_API_BASE      = "https://search.mcmod.cn/s"
MCMOD_TIMEOUT       = 10
MCMOD_MAX_LOOKUP    = 8
MCMOD_CACHE_FILE    = os.path.join(BASE_DIR, "mcmod_cache.json")

# modlist.txt 找不到时的后备映射
# 【TODO】按整合包补充
MCMOD_KEYWORD_MAP = {
    # "example_modid": "模组中文名",
}


# ==================== 语言 ====================
QUEST_LANGUAGE = "zh"


# ==================== 模组 ID 前缀 ====================
# 【TODO】按整合包补充。章节前缀与奖励池会引用这里的键
MOD = {
    # "example": "example_modid",
}


# ==================== 任务书整体介绍 ====================
# 会写进每次提示词开头，告诉 AI 这个整合包是什么
# 【TODO】改成你的整合包简介（一两句话讲清主题）
PACK_INTRO = (
    "这是一个 Minecraft 整合包。"
)


# ==================== 整合包介绍章节 ====================
# 自动在所有章节组之前插入一个「整合包介绍」章节
# 章节内容由 AI 根据 PACK_INTRO + 模组列表生成，不需要手写任务
ENABLE_PACK_INTRO_CHAPTER = True
PACK_INTRO_CHAPTER_TITLE  = "整合包介绍"
PACK_INTRO_CHAPTER_FOCUS  = (
    "向玩家介绍本整合包的核心主题、主要玩法、推荐游玩顺序。"
    "任务以 checkmark 为主，让玩家读完介绍后点击确认即可。"
)
PACK_INTRO_CHAPTER_ICON   = "minecraft:book"
PACK_INTRO_TASK_COUNT     = 3   # 介绍章节生成多少个任务


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
# 章节 icon 字段若不在 items.json 中，自动回退到此图标
# 防止游戏内显示紫黑方块/乱码
ICON_FALLBACK = "minecraft:book"


# ==================== 章节组配置 ====================
# 【TODO】按你的整合包填写。
#
# 每章字段:
#   title            章节标题
#   focus            本章主题描述（写入提示词）
#   extra            整体要求描述（写入提示词）
#   item_prefixes    物品模组前缀列表（空列表 = 使用全物品池）
#   entity_prefixes  实体模组前缀列表（空列表 = 使用全实体池）
#   use_structures   是否使用 structure 任务
#   task_types       本章允许的任务类型（item / checkmark / structure / kill）
#   icon             章节图标物品 ID（不在 items.json 时自动回退 ICON_FALLBACK）
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
            },
        ],
    },
]


# ==================== 奖励表定义（手写后备） ====================
# 仅当 REWARD_AUTO_FROM_ITEMS = False 或物品池为空时使用
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

# 【TODO】奖励表物品池映射：table_key -> 前缀列表（空列表 = 使用全部物品）
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