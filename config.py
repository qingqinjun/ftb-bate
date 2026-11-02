# -*- coding: utf-8 -*-
"""
========================================================
config.py —— ftb-bate 配置文件（白板模板）
========================================================
只需改这个文件，main.py 不用动。
使用前请把下面所有 【TODO】 处填好。
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
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL    = os.environ.get("LLM_MODEL", "deepseek-flash")


# ==================== 语言 ====================
# "zh" = 中文任务标题/描述
# "en" = English quest titles/descriptions
QUEST_LANGUAGE = "zh"


# ==================== 任务书整体介绍 ====================
# 会写进每次提示词开头，告诉 AI 这个整合包是什么
# 【TODO】改成你的整合包简介
PACK_INTRO = (
    "这是一个 Minecraft 整合包。"
)


# ==================== 生成规模 ====================
TASKS_PER_CHAPTER = 55   # 每章目标任务数
BATCH_SIZE        = 10   # 每次 API 请求生成多少任务
FILE_RETRY        = 5    # 文件读取失败重试次数


# ==================== 坐标布局 ====================
COLS_PER_ROW = 6
COL_SPACING  = 2.0
ROW_SPACING  = 1.5
START_X      = 0.0
START_Y      = 0.0


# ==================== 章节组配置 ====================
# 【TODO】按你的整合包填写。示例已清空，只留一个占位章节。
#
# 每个组:
#   title     组名（游戏里章节列表的分组标题）
#   chapters  章节列表，每章字段:
#       title            章节标题
#       focus            本章主题描述（写入提示词）
#       extra            整体要求描述（写入提示词）
#       item_prefixes    物品模组前缀列表，如 ["twilightforest"]
#       entity_prefixes  实体模组前缀列表，如 ["twilightforest", "legendary_monsters"]
#       use_structures   是否使用 structure 任务
#       icon             章节图标物品 ID（可留空字符串）
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
                "icon": "",
            },
        ],
    },
]


# ==================== 奖励表定义 ====================
# 每个 key 会生成 reward_tables/<key>.snbt
# 任务中的 random 奖励会引用这些真实存在的表
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


# 自动推导，不要在 main.py 里手写
TOTAL_CHAPTERS = len(flatten_chapters())
CHAPTER_TITLES = [ch["title"] for ch in flatten_chapters()]