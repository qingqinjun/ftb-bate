# -*- coding: utf-8 -*-
"""
========================================================
config.example.py —— 配置模板
========================================================
使用方法：
  1. 把本文件复制一份，重命名为 config.py
  2. 按需修改下面的配置项
  3. 运行 python ftb_bate.py 即可

注意：
  - config.py 已被 .gitignore 忽略，不会误传到 GitHub
  - API Key 只从环境变量 DEEPSEEK_API_KEY 读取，不要写在这里
========================================================
"""

import os

# ==================== 路径配置 ====================
# 数据文件所在目录（modlist.txt / items.json / structure_dump.txt / entities_list.json）
# 默认读取环境变量 FTB_DATA_DIR，没有则用当前目录下的 data/
BASE_DIR = os.environ.get("FTB_DATA_DIR", os.path.join(os.getcwd(), "data"))

MODLIST_FILE = os.path.join(BASE_DIR, "modlist.txt")
ITEMS_FILE = os.path.join(BASE_DIR, "items.json")
STRUCTURE_FILE = os.path.join(BASE_DIR, "structure_dump.txt")
ENTITIES_FILE = os.path.join(BASE_DIR, "entities_list.json")
OUTPUT_DIR = BASE_DIR

# ==================== API 配置 ====================
# Key 只从环境变量读取，禁止写死
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-flash"

# ==================== 整合包信息 ====================
# 整合包一句话介绍（会写入 AI 提示词开头）
PACK_INTRO = (
    "整合包以修仙之路（immortal_cultivation_mod）为核心，"
    "长生诀、铁魔法、车万女仆为辅助，终章挑战暮色森林与传奇怪物。"
)

# ==================== 章节配置 ====================
# 章节总数（9 原章节 + 1 暮色森林 = 10）
TOTAL_CHAPTERS = 10

# 按章节顺序填写标题（长度需 >= TOTAL_CHAPTERS）
CHAPTER_TITLES = [
    "主线·启灵入道", "主线·练气筑基", "主线·金丹大道", "主线·元婴化神",
    "支线·长生诀", "支线·铁魔法", "支线·车万女仆", "探索·结构发现", "综合·终局挑战",
    "暮色·传奇怪物",
]

# ==================== 任务数量 ====================
# 每章目标任务数（50~60）
TASKS_PER_CHAPTER = 55
# 每次请求 AI 生成多少个任务（太大容易 JSON 截断）
BATCH_SIZE = 10

# ==================== 重试配置 ====================
# 文件读取重试次数
FILE_RETRY = 5

# ==================== 坐标布局 ====================
COLS_PER_ROW = 6
COL_SPACING = 2.0
ROW_SPACING = 1.5
START_X = 0.0
START_Y = 0.0