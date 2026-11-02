# -*- coding: utf-8 -*-
"""
========================================================
ftb-bate —— FTB Quests 任务书自动生成器
========================================================
支持：
  - 章节组 / 章节 / 任务三层结构
  - item / checkmark / structure / kill 四种任务类型
  - 真实 reward_tables 生成，random 奖励引用真实表
  - 依赖循环检测与修复
  - 章节 icon 字段
  - 日志持久化
  - 数据文件递归解包：支持任意嵌套，包括
      {"total_entities": N, "entities": [...]}
      {"data": {"entities": [...]}}
      ["modid:id", ...]
      {"modid:id": "中文名"}
      [{"id": "...", "name": "..."}]
  - 任务语言切换（中文 / 英文），由 config.QUEST_LANGUAGE 控制
========================================================
"""
import json
import os
import random
import re
import sys
import time

import requests

try:
    import config as cfg
    print("[配置] 已加载 config.py")
except ImportError:
    print("[错误] 未找到 config.py，请先按模板创建")
    sys.exit(1)


# ==================== 语言 ====================
def is_en():
    return str(getattr(cfg, "QUEST_LANGUAGE", "zh")).lower() == "en"


# ==================== 日志 ====================
_LOG_FILE = None


def log(msg):
    print(msg)
    if _LOG_FILE:
        _LOG_FILE.write(msg + "\n")
        _LOG_FILE.flush()


def init_log(path):
    global _LOG_FILE
    _LOG_FILE = open(path, "a", encoding="utf-8")


def close_log():
    global _LOG_FILE
    if _LOG_FILE:
        _LOG_FILE.close()
        _LOG_FILE = None


# ==================== 工具函数 ====================
def gen_hex_id():
    return f"{random.getrandbits(64):016X}"


class IdPool:
    """全局唯一 ID 池，防止碰撞。"""

    def __init__(self):
        self.used = set()

    def new(self):
        while True:
            i = gen_hex_id()
            if i not in self.used:
                self.used.add(i)
                return i


ID_POOL = IdPool()


def load_file_with_retry(filepath, loader, desc, retries=None):
    retries = retries or cfg.FILE_RETRY
    for attempt in range(1, retries + 1):
        try:
            return loader(filepath)
        except FileNotFoundError:
            log(f"  [重试 {attempt}/{retries}] 找不到 {desc}: {filepath}")
        except json.JSONDecodeError as e:
            log(f"  [重试 {attempt}/{retries}] {desc} JSON 解析失败: {e}")
        except Exception as e:
            log(f"  [重试 {attempt}/{retries}] {desc} 读取异常: {e}")
        if attempt < retries:
            time.sleep(0.5)
    log(f"  [跳过] {desc} 读取失败 {retries} 次，跳过")
    return None


def _clean_str(s):
    return str(s).strip() if s is not None else ""


def _find_data_array(data, known_keys, depth=0):
    """
    递归从任意嵌套结构中找出目标数组（实体/物品等）。
    返回 (list_or_dict, 来源路径描述)。
    """
    if depth > 6:
        return None, ""
    if isinstance(data, list):
        return data, f"list@{depth}"
    if isinstance(data, dict):
        for key in known_keys:
            if key in data:
                inner, path = _find_data_array(data[key], known_keys, depth + 1)
                if inner is not None:
                    return inner, f"{key}.{path}" if path else key
        # 未知键名，找第一个 list 或 {id:name} 字典
        for k, v in data.items():
            if isinstance(v, list):
                return v, f"{k}@{depth}"
            if isinstance(v, dict) and any(
                isinstance(x, str) and ":" in x for x in v.keys()
            ):
                return v, f"{k}@dict"
    return None, ""


# ==================== 数据解析 ====================
def _parse_items(filepath):
    """递归解包 items.json，支持字符串数组 / {id:name} 字典 / 对象数组。"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    arr, _ = _find_data_array(
        data, ("items", "item", "data", "list", "result", "values")
    )
    result = {}
    if isinstance(arr, list):
        for entry in arr:
            if isinstance(entry, str):
                iid = _clean_str(entry)
                if iid and ":" in iid:
                    result[iid] = iid
            elif isinstance(entry, dict):
                iid = ""
                for k in ("id", "item", "registry_name", "name", "key", "resource_location"):
                    if k in entry and isinstance(entry[k], str):
                        iid = _clean_str(entry[k])
                        break
                if not iid or ":" not in iid:
                    continue
                iname = ""
                for k in ("name", "display_name", "translation_key", "zh_name"):
                    if k in entry and isinstance(entry[k], str) and entry[k] != iid:
                        iname = _clean_str(entry[k])
                        break
                result[iid] = iname or iid
    elif isinstance(arr, dict):
        for k, v in arr.items():
            kid = _clean_str(k)
            if not kid or ":" not in kid:
                continue
            result[kid] = _clean_str(v) if isinstance(v, str) and v else kid
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
    """
    递归解析 entities_list.json：支持
      {"total_entities": N, "entities": [...]}
      {"data": {"entities": [...]}}
      ["modid:entity", ...]
      {"modid:entity": "中文名"}
      [{"id": "...", "name": "..."}]
    每条 strip()，只保留含 ":" 的合法 ID。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    arr, source = _find_data_array(
        data, ("entities", "entity", "data", "list", "items", "result", "values")
    )
    if arr is None:
        log(f"  [警告] 无法从 entities_list.json 中找到实体数组"
            f"（顶层类型: {type(data).__name__}）")
        return {}

    result = {}
    if isinstance(arr, list):
        for entry in arr:
            if isinstance(entry, str):
                eid = _clean_str(entry)
                if eid and ":" in eid:
                    result[eid] = eid
            elif isinstance(entry, dict):
                eid = ""
                for k in ("id", "entity", "registry_name", "type", "key",
                          "name", "resource_location"):
                    if k in entry and isinstance(entry[k], str):
                        eid = _clean_str(entry[k])
                        break
                if not eid or ":" not in eid:
                    continue
                ename = ""
                for k in ("name", "display_name", "translation_key", "zh_name"):
                    if k in entry and isinstance(entry[k], str) and entry[k] != eid:
                        ename = _clean_str(entry[k])
                        break
                result[eid] = ename or eid
    elif isinstance(arr, dict):
        for k, v in arr.items():
            kid = _clean_str(k)
            if not kid or ":" not in kid:
                continue
            result[kid] = _clean_str(v) if isinstance(v, str) and v else kid

    log(f"  [解析] 实体数组来源: {source}，解析出 {len(result)} 条")
    return result


def load_items(filepath):
    data = load_file_with_retry(filepath, _parse_items, "items.json")
    if data is None:
        return {}
    log(f"[加载] items.json: {len(data)} 个物品")
    return data


def load_structures(filepath):
    data = load_file_with_retry(filepath, _parse_structures, "structure_dump.txt")
    if data is None:
        return []
    log(f"[加载] structure_dump.txt: {len(data)} 个结构")
    return data


def load_modlist(filepath):
    data = load_file_with_retry(filepath, _parse_modlist, "modlist.txt")
    if data is None:
        return set()
    log(f"[加载] modlist.txt: 提取到 {len(data)} 个潜在 ID")
    return data


def load_entities(filepath):
    data = load_file_with_retry(filepath, _parse_entities, "entities_list.json")
    if data is None:
        return {}
    log(f"[加载] entities_list.json: {len(data)} 个实体")
    if data:
        log(f"[诊断] 实体样本: {list(data.keys())[:5]}")
        for prefix in ("twilightforest", "legendary_monsters"):
            hit = sum(1 for k in data if k.startswith(prefix + ":"))
            log(f"[诊断] {prefix}: {hit} 条")
    return data


def filter_by_prefix(ids, prefixes):
    out = []
    for p in prefixes:
        out.extend([i for i in ids if i.startswith(p + ":")])
    return out


# ==================== 章节上下文 ====================
def chapter_context(chapter_index):
    flat = cfg.flatten_chapters()
    ch = flat[chapter_index]
    return {
        "title": ch["title"],
        "focus": ch.get("focus", ""),
        "extra": ch.get("extra", ""),
        "item_prefixes": ch.get("item_prefixes", []),
        "entity_prefixes": ch.get("entity_prefixes", []),
        "use_structures": ch.get("use_structures", False),
        "icon": ch.get("icon", ""),
        "group_index": ch["_group_index"],
    }


# ==================== 提示词 ====================
def _prompt_zh(ctx, chapter_index, batch_index, already, item_pool, struct_pool, entity_pool):
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

    if ctx["use_structures"]:
        type_hint = (
            '本章重点使用 type="structure" 任务：玩家发现该结构时自动完成。'
            '必须从【可用结构 ID】中选择真实存在的结构 ID 填入 "id"。'
        )
    elif ctx["entity_prefixes"]:
        type_hint = (
            '本章可用 type: "item" / "checkmark" / "kill"。'
            'kill 类型必须有真实的 "id"（实体 ID）和 "count"（整数）。'
            'item 类型必须有真实物品 "id"。'
        )
    else:
        type_hint = 'type 只能是 "item" 或 "checkmark"。item 类型必须有真实存在的 "id"。'

    return f"""你是 Minecraft FTB Quests 任务书设计师。{cfg.PACK_INTRO}

为第 {chapter_index + 1} 章「{ctx["title"]}」生成第 {batch_index + 1} 批任务，共 {cfg.BATCH_SIZE} 个。

【本章焦点】{ctx["focus"]}
【整体要求】{ctx["extra"]}
【串联要求】{chain_hint}

【已有任务 key 列表】（dependencies 只能从这里选，或选本批前面任务的 key，也可为空）：
{json.dumps(prev_keys, ensure_ascii=False)}

【已有任务示例】（最近 8 个）：
{json.dumps(prev_desc, ensure_ascii=False)}

【可用物品 ID】（必须使用真实 ID，禁止编造）：
{json.dumps(item_pool[:40], ensure_ascii=False)}

【可用结构 ID】（structure 类型必须使用真实 ID，禁止编造）：
{json.dumps(struct_pool, ensure_ascii=False)}

【可用实体 ID】（kill 类型必须从以下列表**逐字复制**，禁止修改、禁止编造）：
{json.dumps(entity_pool[:80], ensure_ascii=False)}

【输出格式】严格输出 JSON 数组，不要 Markdown 代码块，不要解释文字：
[
  {{"key": "t1", "type": "item", "id": "modid:item_name", "title": "中文标题", "desc": "中文描述", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "中文标题", "desc": "中文描述", "dependencies": ["t1"]}},
  {{"key": "t3", "type": "structure", "id": "modid:structure_name", "title": "中文标题", "desc": "中文描述", "dependencies": ["t2"]}},
  {{"key": "t4", "type": "kill", "id": "minecraft:zombie", "count": 10, "title": "中文标题", "desc": "中文描述", "dependencies": []}}
]

规则：
- 每批恰好 {cfg.BATCH_SIZE} 个任务
- key 在本章内唯一，用 t1/t2/... 这种短名
- {type_hint}
- dependencies 是 key 的数组，可为空数组（表示无前置）
- title ≤ 12 字，desc ≤ 30 字
- 绝对不要编造物品、结构或实体 ID
"""


def _prompt_en(ctx, chapter_index, batch_index, already, item_pool, struct_pool, entity_pool):
    prev_keys = [q["key"] for q in already]
    prev_desc = [f'{q["key"]}: {q["title"]}' for q in already[-8:]]

    if not already:
        chain_hint = (
            "This is the first batch of this chapter. The first quest's dependencies MUST be an empty array []; "
            "it acts as the chapter root. Later quests may branch freely or be isolated. Full chaining is not required."
        )
    else:
        chain_hint = (
            "This is a follow-up batch. New quests may reference existing keys as dependencies, but chaining is not mandatory. "
            "Independent or branching quests are allowed. dependencies may be an empty array [] (no prerequisite)."
        )

    if ctx["use_structures"]:
        type_hint = (
            'This chapter focuses on type="structure" quests: completed automatically when the player finds the structure. '
            'The "id" MUST be a real structure ID from the provided list.'
        )
    elif ctx["entity_prefixes"]:
        type_hint = (
            'Allowed types: "item" / "checkmark" / "kill". '
            'kill quests MUST have a real "id" (entity ID) and an integer "count". '
            'item quests MUST have a real item "id".'
        )
    else:
        type_hint = 'type must be "item" or "checkmark". item quests MUST have a real "id".'

    return f"""You are a Minecraft FTB Quests designer. {cfg.PACK_INTRO}

Generate batch {batch_index + 1} of Chapter {chapter_index + 1} "{ctx["title"]}", total {cfg.BATCH_SIZE} quests.

[Chapter focus] {ctx["focus"]}
[Overall requirements] {ctx["extra"]}
[Chaining rule] {chain_hint}

[Existing quest keys] (dependencies may only reference these or earlier quests in this batch; empty array allowed):
{json.dumps(prev_keys, ensure_ascii=False)}

[Recent quest examples] (last 8):
{json.dumps(prev_desc, ensure_ascii=False)}

[Available item IDs] (must be real, do NOT invent):
{json.dumps(item_pool[:40], ensure_ascii=False)}

[Available structure IDs] (structure quests must use real IDs, do NOT invent):
{json.dumps(struct_pool, ensure_ascii=False)}

[Available entity IDs] (kill quests MUST copy these verbatim, do NOT modify or invent):
{json.dumps(entity_pool[:80], ensure_ascii=False)}

[Output format] Output ONLY a JSON array, no Markdown code block, no explanation:
[
  {{"key": "t1", "type": "item", "id": "modid:item_name", "title": "English title", "desc": "English description", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "English title", "desc": "English description", "dependencies": ["t1"]}},
  {{"key": "t3", "type": "structure", "id": "modid:structure_name", "title": "English title", "desc": "English description", "dependencies": ["t2"]}},
  {{"key": "t4", "type": "kill", "id": "minecraft:zombie", "count": 10, "title": "English title", "desc": "English description", "dependencies": []}}
]

Rules:
- Exactly {cfg.BATCH_SIZE} quests per batch
- key unique within this chapter, short names like t1/t2/...
- {type_hint}
- dependencies is an array of keys; empty array means no prerequisite
- title ≤ 5 words, desc ≤ 15 words
- All title/desc MUST be in English
- NEVER invent item, structure or entity IDs
"""


def build_prompt(item_ids, structures, entity_ids, chapter_index, batch_index, already):
    ctx = chapter_context(chapter_index)

    item_pool = filter_by_prefix(item_ids, ctx["item_prefixes"]) if ctx["item_prefixes"] else []
    if not item_pool:
        item_pool = item_ids[:60]
    struct_pool = structures[:20] if ctx["use_structures"] else []
    entity_pool = filter_by_prefix(entity_ids, ctx["entity_prefixes"]) if ctx["entity_prefixes"] else []
    if not entity_pool and ctx["entity_prefixes"]:
        entity_pool = entity_ids[:30]

    if is_en():
        return _prompt_en(ctx, chapter_index, batch_index, already, item_pool, struct_pool, entity_pool)
    return _prompt_zh(ctx, chapter_index, batch_index, already, item_pool, struct_pool, entity_pool)


# ==================== API 调用 ====================
def call_deepseek(prompt, max_retries=3):
    url = f"{cfg.BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.MODEL,
        "messages": [
            {"role": "system", "content": "You output only a JSON array, no explanation, no Markdown code block."
                                          if is_en() else
                                          "你只输出 JSON 数组，不输出任何解释，不使用 Markdown 代码块。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 3000,
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
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
            log(f"  [重试 {attempt+1}] AI 返回空列表")
        except json.JSONDecodeError as e:
            log(f"  [重试 {attempt+1}] JSON 解析失败: {e}")
        except requests.exceptions.RequestException as e:
            log(f"  [重试 {attempt+1}] 网络请求失败: {e}")
        except (KeyError, IndexError) as e:
            log(f"  [重试 {attempt+1}] 响应结构异常: {e}")
        except Exception as e:
            log(f"  [重试 {attempt+1}] API 调用失败: {e}")
    return []


# ==================== 结果清洗 ====================
def normalize_batch(batch, already, batch_index, valid_structures=None, valid_entities=None):
    valid_structures = set(valid_structures or [])
    valid_entities = set(valid_entities or [])
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
        raw_id = _clean_str(q.get("id", ""))

        if raw_type == "item" and raw_id:
            qtype, qid = "item", raw_id
            count = None
        elif raw_type == "structure" and raw_id and raw_id in valid_structures:
            qtype, qid = "structure", raw_id
            count = None
        elif raw_type == "kill" and raw_id and raw_id in valid_entities:
            qtype, qid = "kill", raw_id
            try:
                count = max(1, int(q.get("count", 1)))
            except (TypeError, ValueError):
                count = 1
        else:
            if raw_type in ("structure", "kill") and raw_id:
                log(f"    [警告] {raw_type} ID 无效: {raw_id}，降级为 checkmark")
            qtype, qid, count = "checkmark", "", None

        cleaned.append({
            "key": key,
            "type": qtype,
            "id": qid,
            "count": count,
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

    # 过滤无效依赖
    valid = existing_keys | {q["key"] for q in cleaned}
    for q in cleaned:
        q["dependencies"] = [d for d in q["dependencies"] if d in valid and d != q["key"]]

    # 本章第一批根节点依赖清空
    if cleaned and not already:
        cleaned[0]["dependencies"] = []

    return cleaned


# ==================== 依赖循环检测 ====================
def break_cycles(quests):
    """检测依赖图并断开循环，返回被断开的边数量。"""
    graph = {q["key"]: list(q["dependencies"]) for q in quests}
    color = {k: 0 for k in graph}  # 0=白 1=灰 2=黑
    removed = [0]

    def dfs(node):
        color[node] = 1
        for dep in list(graph[node]):
            c = color.get(dep, 0)
            if c == 1:  # 回边
                graph[node].remove(dep)
                removed[0] += 1
                log(f"    [循环] 断开依赖: {node} -> {dep}")
            elif c == 0:
                dfs(dep)
        color[node] = 2

    for k in list(graph):
        if color[k] == 0:
            dfs(k)

    if removed[0]:
        for q in quests:
            q["dependencies"] = graph[q["key"]]
    return removed[0]


# ==================== 奖励 ====================
_REWARD_TABLE_ID_CACHE = {}


def _reward_table_id(key):
    if key not in _REWARD_TABLE_ID_CACHE:
        _REWARD_TABLE_ID_CACHE[key] = gen_hex_id()
    return _REWARD_TABLE_ID_CACHE[key]


def build_reward_table_snbt(key):
    """根据 cfg.REWARD_TABLES[key] 生成 reward_tables/<key>.snbt 内容。"""
    spec = cfg.REWARD_TABLES[key]
    entries = []
    for e in spec["entries"]:
        entries.append(
            f'{{type:"item",item:"{e["item"]}",count:{e["count"]},weight:{e.get("weight",1)}}}'
        )
    table_id = _reward_table_id(key)
    return table_id, f'''{{
    id: "{table_id}"
    title: "{spec["title"]}"
    loot_size: 1
    entries: [
        {",".join(entries)}
    ]
}}'''


def build_reward_snbt(quest_type, table_id):
    """为任务生成奖励 SNBT 片段。"""
    rewards = []
    if quest_type == "structure":
        xp = random.choice([30, 40, 50, 60])
        item_chance = 1.0
        random_chance = 0.6
    elif quest_type == "kill":
        xp = random.choice([10, 15, 20, 25])
        item_chance = 0.6
        random_chance = 0.3
    else:
        xp = random.choice([5, 10, 15, 20])
        item_chance = 0.5
        random_chance = 0.2

    rewards.append(f'{{type:"xp",amount:{xp}}}')

    if random.random() < item_chance:
        pool = [
            "minecraft:emerald", "minecraft:diamond", "minecraft:gold_ingot",
            "minecraft:iron_ingot", "minecraft:experience_bottle",
        ]
        rid = random.choice(pool)
        cnt = random.choice([1, 2, 3])
        rewards.append(f'{{type:"item",item:"{rid}",count:{cnt}}}')

    if random.random() < random_chance and table_id:
        rewards.append(f'{{type:"random",count:1,table_id:"{table_id}"}}')

    return "[" + ",".join(rewards) + "]"


# ==================== SNBT 生成 ====================
def build_snbt_quest(quest, key_to_id, x, y, reward_table_id):
    qid = key_to_id[quest["key"]]
    title = quest["title"].replace('"', '\\"')
    desc = quest["desc"].replace('"', '\\"')
    deps = [key_to_id[d] for d in quest["dependencies"] if d in key_to_id]
    dep_str = "[" + ", ".join(f'"{d}"' for d in deps) + "]" if deps else "[]"

    if quest["type"] == "item":
        tasks = f'[{{type:"item",item:"{quest["id"]}"}}]'
    elif quest["type"] == "structure":
        tasks = f'[{{type:"structure",structure:"{quest["id"]}"}}]'
    elif quest["type"] == "kill":
        cnt = quest.get("count") or 1
        tasks = f'[{{type:"kill",entity:"{quest["id"]}",count:{cnt}}}]'
    else:
        tasks = '[{type:"checkmark"}]'

    rewards = build_reward_snbt(quest["type"], reward_table_id)

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


def generate_chapter_snbt(chapter_index, quests, group_id):
    ctx = chapter_context(chapter_index)
    chapter_id = ID_POOL.new()
    filename = f"chapter_{chapter_index + 1:02d}"
    title = ctx["title"]

    key_to_id = {q["key"]: ID_POOL.new() for q in quests}

    # 选择奖励表
    if ctx["use_structures"]:
        rtable_key = "structure"
    elif chapter_index >= cfg.TOTAL_CHAPTERS - 1:
        rtable_key = "endgame"
    else:
        rtable_key = "basic"
    reward_table_id = _reward_table_id(rtable_key)

    parts = []
    for idx, q in enumerate(quests):
        col = idx % cfg.COLS_PER_ROW
        row = idx // cfg.COLS_PER_ROW
        x = cfg.START_X + col * cfg.COL_SPACING
        y = cfg.START_Y - row * cfg.ROW_SPACING
        parts.append(build_snbt_quest(q, key_to_id, x, y, reward_table_id))

    icon_line = f'    icon: "{ctx["icon"]}"\n' if ctx["icon"] else ""

    content = f'''{{
    filename: "{filename}"
    id: "{chapter_id}"
    group: "{group_id}"
    order_index: {chapter_index}
    title: "{title}"
{icon_line}    quests: [
{",".join(parts)}
    ]
}}'''
    return filename, content


# ==================== 章节组 / 全局配置 ====================
def generate_chapter_groups():
    """生成 chapter_groups.snbt，返回每组的 group_id 列表。"""
    group_ids = []
    parts = []
    for g in cfg.CHAPTER_GROUPS:
        gid = ID_POOL.new()
        group_ids.append(gid)
        parts.append(f'        {{id:"{gid}",title:"{g["title"]}"}}')
    content = '{\n    chapter_groups: [\n' + ",\n".join(parts) + '\n    ]\n}'
    path = os.path.join(cfg.OUTPUT_DIR, "chapter_groups.snbt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"[输出] chapter_groups.snbt 已生成: {path}")
    return group_ids


def generate_data_snbt():
    content = '''{
    default_autoclaim_rewards: "disabled"
    default_consume_items: false
    default_quest_disable_jei: false
    default_quest_shape: "circle"
    default_reward_team: false
}'''
    path = os.path.join(cfg.OUTPUT_DIR, "data.snbt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"[输出] data.snbt 已生成: {path}")


def generate_reward_tables():
    os.makedirs(cfg.REWARDS_OUTPUT_DIR, exist_ok=True)
    for key in cfg.REWARD_TABLES:
        table_id, content = build_reward_table_snbt(key)
        path = os.path.join(cfg.REWARDS_OUTPUT_DIR, f"{key}.snbt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        log(f"[输出] reward_tables/{key}.snbt -> id={table_id}")


# ==================== 章节生成 ====================
def generate_chapter(item_ids, structures, entity_ids, chapter_index):
    all_quests = []
    batches = (cfg.TASKS_PER_CHAPTER + cfg.BATCH_SIZE - 1) // cfg.BATCH_SIZE
    valid_structures = set(structures)
    valid_entities = set(entity_ids)

    for b in range(batches):
        log(f"    批次 {b+1}/{batches} ...")
        prompt = build_prompt(item_ids, structures, entity_ids, chapter_index, b, all_quests)
        batch = call_deepseek(prompt)
        if not batch:
            log(f"    [警告] 批次 {b+1} 无结果，跳过")
            continue
        cleaned = normalize_batch(batch, all_quests, b, valid_structures, valid_entities)
        all_quests.extend(cleaned)
        log(f"    本批 {len(cleaned)} 个，累计 {len(all_quests)} 个")

    # 循环检测
    n_cycles = break_cycles(all_quests)
    if n_cycles:
        log(f"    [修复] 断开 {n_cycles} 条循环依赖")

    return all_quests


# ==================== 主流程 ====================
def main():
    init_log(os.path.join(cfg.OUTPUT_DIR, "generate.log") if os.path.isdir(cfg.OUTPUT_DIR) else "generate.log")
    try:
        log("=" * 60)
        log(" ftb-bate · FTB Quests 任务书自动生成器")
        log(f" 语言: {'English' if is_en() else '中文'}")
        log("=" * 60)

        if not cfg.API_KEY:
            log("[错误] 未检测到 DEEPSEEK_API_KEY 环境变量")
            sys.exit(1)
        if cfg.TOTAL_CHAPTERS <= 0:
            log("[错误] CHAPTER_GROUPS 中没有章节")
            sys.exit(1)

        log("\n[步骤 1/6] 加载数据文件...")
        items = load_items(cfg.ITEMS_FILE)
        item_ids = list(items.keys())
        structures = load_structures(cfg.STRUCTURE_FILE)
        load_modlist(cfg.MODLIST_FILE)
        entities = load_entities(cfg.ENTITIES_FILE)
        entity_ids = list(entities.keys())

        if not item_ids:
            log("[警告] items.json 为空")
        if not structures:
            log("[警告] structure_dump.txt 为空，structure 任务将降级")
        if not entity_ids:
            log("[警告] entities_list.json 为空，kill 任务将降级")

        log("\n[步骤 2/6] 准备输出目录...")
        os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
        os.makedirs(cfg.CHAPTERS_OUTPUT_DIR, exist_ok=True)
        os.makedirs(cfg.REWARDS_OUTPUT_DIR, exist_ok=True)

        log("\n[步骤 3/6] 生成章节组...")
        group_ids = generate_chapter_groups()

        log("\n[步骤 4/6] 生成奖励表...")
        generate_reward_tables()

        log("\n[步骤 5/6] 逐章生成任务...")
        for i in range(cfg.TOTAL_CHAPTERS):
            ctx = chapter_context(i)
            log(f"\n[{i+1}/{cfg.TOTAL_CHAPTERS}] 生成「{ctx['title']}」...")
            quests = generate_chapter(item_ids, structures, entity_ids, i)
            if not quests:
                log(f"  [警告] 第 {i+1} 章无有效任务，使用占位任务")
                quests = [{
                    "key": "t1", "type": "checkmark", "id": "", "count": None,
                    "title": "待补充", "desc": "API 未返回有效任务", "dependencies": []
                }]
            filename, content = generate_chapter_snbt(i, quests, group_ids[ctx["group_index"]])
            path = os.path.join(cfg.CHAPTERS_OUTPUT_DIR, f"{filename}.snbt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            log(f"  -> 已输出: {path}（{len(quests)} 个任务）")

        log("\n[步骤 6/6] 生成全局配置 data.snbt...")
        generate_data_snbt()

        log("\n" + "=" * 60)
        log(" 全部完成！")
        log(f" 输出目录: {cfg.OUTPUT_DIR}")
        log(" 部署方式:")
        log("   把整个输出目录复制到 config/ftbquests/quests/")
        log("   结构应为:")
        log("     quests/")
        log("       ├── data.snbt")
        log("       ├── chapter_groups.snbt")
        log("       ├── chapters/")
        log("       │   └── chapter_XX.snbt")
        log("       └── reward_tables/")
        log("           └── *.snbt")
        log("   进游戏执行 /ftbquests reload")
        log("=" * 60)
    finally:
        close_log()


if __name__ == "__main__":
    main()