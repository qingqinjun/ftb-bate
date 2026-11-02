# -*- coding: utf-8 -*-
"""
========================================================
ftb-bate —— FTB Quests 任务书自动生成器（通用空白模板）
========================================================
功能：
  1. 读取 modlist.txt / items.json / structure_dump.txt / entities_list.json
  2. 调用 DeepSeek API 按主线生成章节任务
  3. 每章约 50~60 个任务，任务之间不一定串联（允许分支、孤立任务）
  4. 每个任务自动附加奖励（经验/物品/随机奖励）
  5. 自动生成章节 SNBT 文件和全局配置 data.snbt
  6. 文件读取失败时自动重试 5 次，仍失败则跳过该文件
  7. 支持 FTB Quests 原生 structure 任务（发现结构自动完成）

说明：
  本文件为空白模板。配置区、章节上下文、提示词中的具体
  项目内容均已清空，请按 TODO 提示填写后再运行。

使用前：
  pip install requests
  export DEEPSEEK_API_KEY="你的key"
========================================================
"""

import json
import os
import random
import re
import sys
import time

import requests

# ==================== 配置区 ====================
try:
    from config import (
        BASE_DIR, MODLIST_FILE, ITEMS_FILE, STRUCTURE_FILE, ENTITIES_FILE,
        OUTPUT_DIR, API_KEY, BASE_URL, MODEL, PACK_INTRO,
        TOTAL_CHAPTERS, TASKS_PER_CHAPTER, BATCH_SIZE, FILE_RETRY,
        COLS_PER_ROW, COL_SPACING, ROW_SPACING, START_X, START_Y,
        CHAPTER_TITLES,
    )
    print("[配置] 已加载 config.py")
except ImportError:
    print("[配置] 未找到 config.py，尝试从环境变量读取…")
    # 兜底配置（保持原有默认值）
    BASE_DIR = os.environ.get("FTB_DATA_DIR", os.path.join(os.getcwd(), "data"))
    MODLIST_FILE = os.path.join(BASE_DIR, "modlist.txt")
    ITEMS_FILE = os.path.join(BASE_DIR, "items.json")
    STRUCTURE_FILE = os.path.join(BASE_DIR, "structure_dump.txt")
    ENTITIES_FILE = os.path.join(BASE_DIR, "entities_list.json")
    OUTPUT_DIR = BASE_DIR
    API_KEY = os.environ.get("DEEPSEEK_API_KEY")
    BASE_URL = "https://api.deepseek.com"
    MODEL = "deepseek-flash"
    PACK_INTRO = ""
    TOTAL_CHAPTERS = 10
    TASKS_PER_CHAPTER = 55
    BATCH_SIZE = 10
    FILE_RETRY = 5
    COLS_PER_ROW = 6
    COL_SPACING = 2.0
    ROW_SPACING = 1.5
    START_X = 0.0
    START_Y = 0.0
    CHAPTER_TITLES = []
# ================================================

def gen_hex_id():
    return f"{random.getrandbits(64):016X}"


def load_file_with_retry(filepath, loader, desc, retries=FILE_RETRY):
    """
    通用文件读取重试函数。
    loader: 接收文件路径并返回结果的函数
    desc: 用于日志的描述
    读取失败时重试 retries 次，仍失败返回 None
    """
    for attempt in range(1, retries + 1):
        try:
            result = loader(filepath)
            return result
        except FileNotFoundError:
            print(f"  [重试 {attempt}/{retries}] 找不到 {desc}: {filepath}")
        except json.JSONDecodeError as e:
            print(f"  [重试 {attempt}/{retries}] {desc} JSON 解析失败: {e}")
        except Exception as e:
            print(f"  [重试 {attempt}/{retries}] {desc} 读取异常: {e}")
        if attempt < retries:
            time.sleep(0.5)
    print(f"  [跳过] {desc} 读取失败 {retries} 次，跳过")
    return None


# ---------- 各类文件的解析函数 ----------

def _parse_items(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    for entry in data:
        if isinstance(entry, dict) and "id" in entry:
            result[entry["id"]] = entry.get("name", entry["id"])
    return result


def _parse_structures(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return [l for l in lines if ":" in l and not l.startswith("#")]


def _parse_modlist(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return set(re.findall(r'[a-z_0-9]+:[a-z_0-9]+', content.lower()))


def _parse_entities(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and "id" in entry:
                result[entry["id"]] = entry.get("name", entry["id"])
            elif isinstance(entry, str):
                result[entry] = entry
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = v
            elif isinstance(v, dict) and "id" in v:
                result[v["id"]] = v.get("name", v["id"])
    return result


def load_items(filepath):
    data = load_file_with_retry(filepath, _parse_items, "items.json")
    if data is None:
        return {}
    print(f"[加载] items.json: {len(data)} 个物品")
    return data


def load_structures(filepath):
    data = load_file_with_retry(filepath, _parse_structures, "structure_dump.txt")
    if data is None:
        return []
    print(f"[加载] structure_dump.txt: {len(data)} 个结构")
    return data


def load_modlist(filepath):
    data = load_file_with_retry(filepath, _parse_modlist, "modlist.txt")
    if data is None:
        return set()
    print(f"[加载] modlist.txt: 提取到 {len(data)} 个潜在 ID")
    return data


def load_entities(filepath):
    data = load_file_with_retry(filepath, _parse_entities, "entities_list.json")
    if data is None:
        return {}
    print(f"[加载] entities_list.json: {len(data)} 个实体")
    return data


def filter_items_by_mod(item_ids, mod_prefixes):
    result = []
    for prefix in mod_prefixes:
        result.extend([i for i in item_ids if i.startswith(prefix + ":")])
    return result


def filter_entities_by_mod(entity_ids, mod_prefixes):
    result = []
    for prefix in mod_prefixes:
        result.extend([e for e in entity_ids if e.startswith(prefix + ":")])
    return result


def chapter_context(chapter_index):
    """返回 (focus, extra, item_mod_prefixes, entity_mod_prefixes, use_structures)

    TODO: 根据 chapter_index 填写每章的生成上下文。
      focus               本章主题描述（写入提示词）
      extra               整体要求描述（写入提示词）
      item_mod_prefixes   需要筛选的物品模组前缀列表，如 ["examplemod"]
      entity_mod_prefixes 需要筛选的实体模组前缀列表
      use_structures      是否使用结构列表作为任务来源

    示例：
        if chapter_index == 0:
            return (
                "examplemod（示例模组）",
                "主线章节，按 progression 排列物品。",
                ["examplemod"],
                [],
                False,
            )
        elif chapter_index == 1:
            return (
                "结构探索",
                "探索章节，任务类型使用 structure，每个任务为发现一个结构。",
                [],
                [],
                True,
            )
        ...
    """
    return ("", "", [], [], False)


def build_prompt(item_ids, structures, entity_ids, chapter_index, batch_index, already):
    """
    构建某一批任务的提示词。
    already: 已生成的任务列表（含 key/title），用于让新任务参考。
    """
    title = CHAPTER_TITLES[chapter_index]
    focus, extra, mod_prefixes, entity_prefixes, use_struct = chapter_context(chapter_index)

    item_pool = filter_items_by_mod(item_ids, mod_prefixes) if mod_prefixes else []
    if not item_pool and chapter_index <= 6:
        item_pool = item_ids[:60]
    struct_pool = structures[:20] if use_struct else []
    entity_pool = filter_entities_by_mod(entity_ids, entity_prefixes) if entity_prefixes else []
    if chapter_index == 9 and not entity_pool:
        entity_pool = entity_ids[:30]

    prev_keys = [q["key"] for q in already]
    prev_desc = [f'{q["key"]}: {q["title"]}' for q in already[-8:]]

    if not already:
        chain_hint = (
            "这是本章第一批任务。第一个任务的 dependencies 必须为空数组 []，它作为本章根节点。"
            "后续任务可以自由连接，允许分支或孤立任务，不强制全部串联。"
        )
    else:
        chain_hint = (
            "这是后续批次。新任务可以引用已有任务的 key 作为依赖，但不必强制串联——"
            "允许独立任务、分支任务。dependencies 可以为空数组（表示无前置）。"
        )

    # 结构章节的类型提示
    if use_struct:
        type_hint = (
            '本章重点使用 type="structure" 任务：玩家发现该结构时自动完成。'
            '必须从【可用结构 ID】中选择真实存在的结构 ID 填入 "id"。'
            '可以搭配少量 item / checkmark 任务作为辅助。'
        )
    else:
        type_hint = (
            'type 只能是 "item" 或 "checkmark"。'
            'item 类型必须有真实存在的 "id"。'
        )

    prompt = f"""你是 Minecraft FTB Quests 任务书设计师。{PACK_INTRO}

为第 {chapter_index + 1} 章「{title}」生成第 {batch_index + 1} 批任务，共 {BATCH_SIZE} 个。

【本章焦点】{focus}
【整体要求】{extra}
【串联要求】{chain_hint}

【已有任务 key 列表】（dependencies 只能从这里选，或选本批前面任务的 key，也可为空）：
{json.dumps(prev_keys, ensure_ascii=False)}

【已有任务示例】（最近 8 个）：
{json.dumps(prev_desc, ensure_ascii=False)}

【可用物品 ID】（必须使用真实 ID，禁止编造）：
{json.dumps(item_pool[:40], ensure_ascii=False)}

【可用结构 ID】（structure 类型必须使用真实 ID，禁止编造）：
{json.dumps(struct_pool, ensure_ascii=False)}

【可用实体 ID】（击杀目标，必须使用真实 ID，禁止编造）：
{json.dumps(entity_pool[:40], ensure_ascii=False)}

【输出格式】严格输出 JSON 数组，不要 Markdown 代码块，不要解释文字：
[
  {{"key": "t1", "type": "item", "id": "modid:item_name", "title": "中文标题", "desc": "中文描述", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "中文标题", "desc": "中文描述", "dependencies": ["t1"]}},
  {{"key": "t3", "type": "structure", "id": "modid:structure_name", "title": "中文标题", "desc": "中文描述", "dependencies": ["t2"]}}
]

规则：
- 每批恰好 {BATCH_SIZE} 个任务
- key 在本章内唯一，用 t1/t2/... 这种短名
- {type_hint}
- dependencies 是 key 的数组，可为空数组（表示无前置），必须引用上面列出的已有 key 或本批前面任务的 key
- title ≤ 12 字，desc ≤ 30 字
- 绝对不要编造物品、结构或实体 ID
"""
    return prompt


def call_deepseek(prompt, max_retries=3):
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你只输出 JSON 数组，不输出任何解释，不使用 Markdown 代码块。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 3000,
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            parsed = json.loads(text)

            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break

            if isinstance(parsed, list) and parsed:
                return parsed
            print(f"  [重试 {attempt+1}] AI 返回空列表")
        except json.JSONDecodeError as e:
            print(f"  [重试 {attempt+1}] JSON 解析失败: {e}")
        except requests.exceptions.RequestException as e:
            print(f"  [重试 {attempt+1}] 网络请求失败: {e}")
        except (KeyError, IndexError) as e:
            print(f"  [重试 {attempt+1}] 响应结构异常: {e}")
        except Exception as e:
            print(f"  [重试 {attempt+1}] API 调用失败: {e}")
    return []


def normalize_batch(batch, already, batch_index, valid_structures=None):
    """
    清洗 AI 输出：
    - 补全缺失 key
    - 支持 item / checkmark / structure 三种类型
    - structure 类型交叉校验：ID 不在 valid_structures 中则降级为 checkmark
    - dependencies 只保留有效 key，允许空依赖（不强制串联）
    """
    valid_structures = set(valid_structures or [])
    cleaned = []
    existing_keys = {q["key"] for q in already}

    for i, q in enumerate(batch):
        if not isinstance(q, dict):
            continue
        key = str(q.get("key") or f"b{batch_index}_{i+1}")
        deps = q.get("dependencies") or []
        if isinstance(deps, str):
            deps = [deps]
        deps = [str(d) for d in deps if isinstance(d, (str, int))]

        raw_type = q.get("type")
        raw_id = q.get("id", "")

        if raw_type == "item" and raw_id:
            qtype = "item"
            qid = raw_id
        elif raw_type == "structure" and raw_id and raw_id in valid_structures:
            qtype = "structure"
            qid = raw_id
        elif raw_type == "structure" and raw_id:
            # 结构 ID 校验失败，降级为 checkmark，避免永远无法完成
            print(f"    [警告] 结构 ID 无效: {raw_id}，降级为 checkmark")
            qtype = "checkmark"
            qid = ""
        else:
            qtype = "checkmark"
            qid = ""

        cleaned.append({
            "key": key,
            "type": qtype,
            "id": qid,
            "title": str(q.get("title", "未命名任务")),
            "desc": str(q.get("desc", "")),
            "dependencies": deps,
        })

    # 去重 key
    seen = set()
    for q in cleaned:
        base = q["key"]
        n = 1
        while q["key"] in seen:
            n += 1
            q["key"] = f"{base}_{n}"
        seen.add(q["key"])

    # 过滤掉引用不存在 key 的依赖（允许空）
    valid = existing_keys | {q["key"] for q in cleaned}
    for q in cleaned:
        q["dependencies"] = [d for d in q["dependencies"] if d in valid and d != q["key"]]

    # 本章第一批：根节点依赖必须为空
    if cleaned and not already:
        cleaned[0]["dependencies"] = []

    return cleaned


def build_reward_snbt(quest_type="checkmark"):
    """
    为每个任务生成奖励 SNBT 片段。
    奖励类型：经验 + 物品（可选）+ 随机奖励（可选）
    structure 类型任务奖励更丰厚。
    """
    rewards = []

    if quest_type == "structure":
        # 结构任务：经验更多
        xp = random.choice([30, 40, 50, 60])
    else:
        xp = random.choice([5, 10, 15, 20])
    rewards.append(f'''{{
                type: "xp"
                amount: {xp}
            }}''')

    # 物品奖励：普通任务 50%，结构任务 100%
    item_chance = 1.0 if quest_type == "structure" else 0.5
    if random.random() < item_chance:
        if quest_type == "structure":
            pool = [
                "minecraft:diamond", "minecraft:emerald", "minecraft:gold_ingot",
                "minecraft:netherite_scrap", "minecraft:enchanted_golden_apple",
                "minecraft:experience_bottle",
            ]
        else:
            pool = [
                "minecraft:emerald", "minecraft:diamond", "minecraft:gold_ingot",
                "minecraft:iron_ingot", "minecraft:experience_bottle",
                "minecraft:enchanted_golden_apple",
            ]
        rid = random.choice(pool)
        count = random.choice([1, 2, 3])
        rewards.append(f'''{{
                item: "{rid}"
                count: {count}
                type: "item"
            }}''')

    # 随机奖励：普通 20%，结构 40%
    random_chance = 0.4 if quest_type == "structure" else 0.2
    if random.random() < random_chance:
        rewards.append(f'''{{
                type: "random"
                count: 1
                table_id: "{gen_hex_id()}"
            }}''')

    return "[" + ",".join(rewards) + "]"


def build_snbt_quest(quest, key_to_id, x, y):
    qid = key_to_id[quest["key"]]
    title = quest["title"].replace('"', '\\"')
    desc = quest["desc"].replace('"', '\\"')
    deps = [key_to_id[d] for d in quest["dependencies"] if d in key_to_id]
    dep_str = "[" + ", ".join(f'"{d}"' for d in deps) + "]" if deps else "[]"

    if quest["type"] == "item":
        tasks = f'''[{{
                item: "{quest["id"]}"
                type: "item"
            }}]'''
    elif quest["type"] == "structure":
        # FTB Quests 原生结构任务：玩家发现该结构自动完成
        tasks = f'''[{{
                structure: "{quest["id"]}"
                type: "structure"
            }}]'''
    else:
        tasks = '''[{
                type: "checkmark"
            }]'''

    rewards = build_reward_snbt(quest["type"])

    return f'''        {{
            id: "{qid}"
            x: {x}d
            y: {y}d
            dependencies: {dep_str}
            tasks: {tasks}
            rewards: {rewards}
            title: "{title}"
            description: ["{desc}"]
        }}'''


def generate_chapter_snbt(chapter_index, quests):
    chapter_id = gen_hex_id()
    filename = f"chapter_{chapter_index + 1:02d}"
    title = CHAPTER_TITLES[chapter_index]

    key_to_id = {q["key"]: gen_hex_id() for q in quests}

    parts = []
    for idx, q in enumerate(quests):
        col = idx % COLS_PER_ROW
        row = idx // COLS_PER_ROW
        x = START_X + col * COL_SPACING
        y = START_Y - row * ROW_SPACING
        parts.append(build_snbt_quest(q, key_to_id, x, y))

    content = f'''{{
    filename: "{filename}"
    id: "{chapter_id}"
    order_index: {chapter_index}
    title: "{title}"
    quests: [
{",".join(parts)}
    ]
}}'''
    return filename, content


def generate_data_snbt():
    content = '''{
    default_autoclaim_rewards: "disabled"
    default_consume_items: false
    default_quest_disable_jei: false
    default_quest_shape: "circle"
    default_reward_team: false
}'''
    out_path = os.path.join(OUTPUT_DIR, "data.snbt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[输出] data.snbt 已生成: {out_path}")


def generate_chapter(item_ids, structures, entity_ids, chapter_index):
    """分批生成一章，返回清洗后的任务列表"""
    all_quests = []
    batches = (TASKS_PER_CHAPTER + BATCH_SIZE - 1) // BATCH_SIZE
    valid_structures = set(structures)

    for b in range(batches):
        print(f"    批次 {b+1}/{batches} ...")
        prompt = build_prompt(item_ids, structures, entity_ids, chapter_index, b, all_quests)
        batch = call_deepseek(prompt)
        if not batch:
            print(f"    [警告] 批次 {b+1} 无结果，跳过")
            continue
        cleaned = normalize_batch(batch, all_quests, b, valid_structures)
        all_quests.extend(cleaned)
        print(f"    本批 {len(cleaned)} 个，累计 {len(all_quests)} 个")

    return all_quests


def main():
    print("=" * 60)
    print(" ftb-bate · FTB Quests 任务书自动生成器（空白模板）")
    print("=" * 60)

    if not API_KEY:
        print("[错误] 未检测到环境变量 DEEPSEEK_API_KEY")
        print('       请先执行: export DEEPSEEK_API_KEY="你的key"')
        sys.exit(1)

    if TOTAL_CHAPTERS <= 0:
        print("[错误] 请先在配置区填写 TOTAL_CHAPTERS（章节总数）")
        sys.exit(1)
    if not CHAPTER_TITLES or len(CHAPTER_TITLES) < TOTAL_CHAPTERS:
        print("[错误] 请先在配置区填写 CHAPTER_TITLES（长度需 >= TOTAL_CHAPTERS）")
        sys.exit(1)

    print("\n[步骤 1/5] 加载数据文件（失败自动重试 5 次）...")
    items = load_items(ITEMS_FILE)
    item_ids = list(items.keys())
    structures = load_structures(STRUCTURE_FILE)
    load_modlist(MODLIST_FILE)
    entities = load_entities(ENTITIES_FILE)
    entity_ids = list(entities.keys())

    if not item_ids:
        print("[警告] items.json 中没有任何物品 ID，生成的任务可能缺少物品 ID")
    if not entity_ids:
        print("[警告] entities_list.json 为空或读取失败，需要实体击杀的章节可能缺少实体 ID")
    if not structures:
        print("[警告] structure_dump.txt 为空，structure 类型任务将无法生成")

    print("\n[步骤 2/5] API 配置就绪...")
    print(f"[信息] 模型: {MODEL}")
    print(f"[信息] 端点: {BASE_URL}")

    print("\n[步骤 3/5] 逐章生成任务...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for i in range(TOTAL_CHAPTERS):
        print(f"\n[{i+1}/{TOTAL_CHAPTERS}] 生成「{CHAPTER_TITLES[i]}」...")
        quests = generate_chapter(item_ids, structures, entity_ids, i)

        if not quests:
            print(f"  [警告] 第 {i+1} 章未生成有效任务，使用占位任务")
            quests = [{
                "key": "t1", "type": "checkmark", "id": "",
                "title": "待补充", "desc": "API 未返回有效任务", "dependencies": []
            }]

        filename, content = generate_chapter_snbt(i, quests)
        out_path = os.path.join(OUTPUT_DIR, f"{filename}.snbt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  -> 已输出: {out_path}（{len(quests)} 个任务）")

    print("\n[步骤 4/5] 生成全局配置 data.snbt...")
    generate_data_snbt()

    print("\n" + "=" * 60)
    print(" 全部完成！")
    print(f" 输出目录: {OUTPUT_DIR}")
    print(" 部署方式:")
    print("   1. data.snbt 复制到:   config/ftbquests/quests/")
    print("   2. chapter_*.snbt 复制到: config/ftbquests/quests/chapters/")
    print("   3. 进游戏执行 /ftbquests reload")
    print("=" * 60)


if __name__ == "__main__":
    main()