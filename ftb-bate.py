# -*- coding: utf-8 -*-
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

def is_en():
    return str(getattr(cfg, "QUEST_LANGUAGE", "zh")).lower() == "en"

_LOG_FILE = None
def log(msg):
    print(msg)
    if _LOG_FILE:
        _LOG_FILE.write(msg + "\n")
        _LOG_FILE.flush()

def init_log(path):
    global _LOG_FILE
    d = os.path.dirname(path)
    if d: os.makedirs(d, exist_ok=True)
    _LOG_FILE = open(path, "a", encoding="utf-8")

def close_log():
    global _LOG_FILE
    if _LOG_FILE:
        _LOG_FILE.close()
        _LOG_FILE = None

_mcmod_cache = {}
_mcmod_cache_dirty = False
_modlist_map = {}

def _load_mcmod_cache():
    global _mcmod_cache, _mcmod_cache_dirty
    path = getattr(cfg, "MCMOD_CACHE_FILE", None)
    if not path or not os.path.isfile(path): return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _mcmod_cache = data
            _mcmod_cache_dirty = False
            log(f"[MC百科] 已加载缓存 {len(_mcmod_cache)} 条")
    except Exception as e:
        log(f"[MC百科] 缓存加载失败: {e}")

def _save_mcmod_cache():
    global _mcmod_cache_dirty
    if not _mcmod_cache_dirty: return
    path = getattr(cfg, "MCMOD_CACHE_FILE", None)
    if not path: return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_mcmod_cache, f, ensure_ascii=False, indent=2)
        log(f"[MC百科] 缓存已保存 {len(_mcmod_cache)} 条 -> {path}")
        _mcmod_cache_dirty = False
    except Exception as e:
        log(f"[MC百科] 缓存保存失败: {e}")

def _cn_keyword(keyword):
    if ":" not in keyword: return keyword
    prefix, rest = keyword.split(":", 1)
    name = _modlist_map.get(prefix)
    if name: return f"{name} {rest}"
    cn = getattr(cfg, "MCMOD_KEYWORD_MAP", {}).get(prefix)
    if cn: return f"{cn} {rest}"
    return keyword

def lookup_mcmod(keyword, timeout=None):
    global _mcmod_cache_dirty
    if not keyword or not getattr(cfg, "ENABLE_MCMOD_LOOKUP", False): return ""
    if keyword in _mcmod_cache: return _mcmod_cache[keyword]
    base = str(getattr(cfg, "MCMOD_API_BASE", "") or "").rstrip("/")
    if not base: return ""
    if timeout is None: timeout = getattr(cfg, "MCMOD_TIMEOUT", 10)
    query = _cn_keyword(keyword)
    try:
        resp = requests.get(base, params={"q": query}, timeout=timeout, headers={"User-Agent": "ftb-bate/1.0"})
        resp.raise_for_status()
        text = ""
        if "json" in resp.headers.get("Content-Type", "").lower():
            data = resp.json()
            if isinstance(data, dict):
                title = data.get("title") or data.get("name") or ""
                summary = data.get("summary") or data.get("desc") or ""
                parts = []
                if title: parts.append(f"标题: {title}")
                if summary: parts.append(f"简介: {str(summary)[:200]}")
                if parts: text = "；".join(parts)
        _mcmod_cache[keyword] = text
        _mcmod_cache_dirty = True
        return text
    except Exception:
        _mcmod_cache[keyword] = ""
        _mcmod_cache_dirty = True
        return ""

def _build_mcmod_section(item_pool, entity_pool):
    if not getattr(cfg, "ENABLE_MCMOD_LOOKUP", False): return ""
    max_n = int(getattr(cfg, "MCMOD_MAX_LOOKUP", 0) or 0)
    if max_n <= 0: return ""
    seen_modids = []
    for iid in list(item_pool) + list(entity_pool):
        if ":" not in iid: continue
        modid = iid.split(":", 1)[0]
        if modid not in seen_modids: seen_modids.append(modid)
        if len(seen_modids) >= max_n: break
    if not seen_modids: return ""
    lines = []
    for modid in seen_modids:
        hint = lookup_mcmod(f"{modid}:main")
        if hint: lines.append(f"- {modid}: {hint}")
    if not lines: return ""
    return "\n【MC百科补充资料】\n" + "\n".join(lines) + "\n"

def gen_hex_id():
    return f"{random.getrandbits(64):016X}"

class IdPool:
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
        if attempt < retries: time.sleep(0.5)
    log(f"  [跳过] {desc} 读取失败 {retries} 次，跳过")
    return None

def _clean_str(s): return str(s).strip() if s is not None else ""

def _find_data_array(data, known_keys, depth=0):
    if depth > 6: return None, ""
    if isinstance(data, list): return data, f"list@{depth}"
    if isinstance(data, dict):
        for key in known_keys:
            if key in data:
                inner, path = _find_data_array(data[key], known_keys, depth + 1)
                if inner is not None: return inner, f"{key}.{path}" if path else key
        for k, v in data.items():
            if isinstance(v, list): return v, f"{k}@{depth}"
            if isinstance(v, dict) and any(isinstance(x, str) and ":" in x for x in v.keys()): return v, f"{k}@dict"
    return None, ""

def _parse_items(filepath):
    with open(filepath, "r", encoding="utf-8") as f: data = json.load(f)
    arr, _ = _find_data_array(data, ("items", "item", "data", "list", "result", "values"))
    result = {}
    if isinstance(arr, list):
        for entry in arr:
            if isinstance(entry, str) and ":" in entry: result[entry] = entry
            elif isinstance(entry, dict):
                iid = entry.get("id") or entry.get("item") or entry.get("name")
                if iid and ":" in iid: result[iid] = iid
    return result

def _parse_structures(filepath):
    with open(filepath, "r", encoding="utf-8") as f: data = json.load(f)
    arr = data if isinstance(data, list) else []
    return [s for s in arr if ":" in s]

def _parse_modlist(filepath):
    with open(filepath, "r", encoding="utf-8") as f: data = json.load(f)
    result = {}
    if isinstance(data, dict):
        for k, v in data.items():
            name = str(v).split("|")[0].strip()
            result[k] = name if name else k
    return result

def _parse_entities(filepath):
    with open(filepath, "r", encoding="utf-8") as f: data = json.load(f)
    arr, _ = _find_data_array(data, ("entities", "entity", "data", "list"))
    result = {}
    if isinstance(arr, list):
        for entry in arr:
            if isinstance(entry, str) and ":" in entry: result[entry] = entry
            elif isinstance(entry, dict):
                eid = entry.get("id") or entry.get("entity") or entry.get("type")
                if eid and ":" in eid: result[eid] = eid
    return result

def load_items(f): return load_file_with_retry(f, _parse_items, "items.json") or {}
def load_structures(f): return load_file_with_retry(f, _parse_structures, "structures.json") or []
def load_modlist(f): return load_file_with_retry(f, _parse_modlist, "modlist.json") or {}
def load_entities(f): return load_file_with_retry(f, _parse_entities, "entities.json") or {}

def filter_by_prefix(ids, prefixes):
    out = []
    for p in prefixes: out.extend([i for i in ids if i.startswith(p + ":")])
    return out

def chapter_context(chapter_index):
    flat = cfg.flatten_chapters()
    ch = flat[chapter_index]
    return {
        "title": ch["title"], "focus": ch.get("focus", ""), "extra": ch.get("extra", ""),
        "item_prefixes": ch.get("item_prefixes", []), "entity_prefixes": ch.get("entity_prefixes", []),
        "use_structures": ch.get("use_structures", False), "task_types": ch.get("task_types", ["item", "checkmark"]),
        "icon": ch.get("icon", ""), "group_index": ch["_group_index"],
    }

def build_prompt(item_ids, structures, entity_ids, chapter_index, batch_index, already):
    ctx = chapter_context(chapter_index)
    allowed = [t for t in ctx["task_types"] if t in ("item", "checkmark", "structure", "kill")]
    if not structures and "structure" in allowed: allowed.remove("structure")
    if not entity_ids and "kill" in allowed: allowed.remove("kill")
    if not allowed: allowed = ["item", "checkmark"]

    item_pool = filter_by_prefix(item_ids, ctx["item_prefixes"]) if ctx["item_prefixes"] else item_ids[:60]
    struct_pool = structures[:20] if ctx["use_structures"] else []
    entity_pool = filter_by_prefix(entity_ids, ctx["entity_prefixes"]) if ctx["entity_prefixes"] else entity_ids[:30]

    prev_keys = [q["key"] for q in already]
    prev_desc = [f'{q["key"]}: {q["title"]}' for q in already[-8:]]
    
    mcmod_section = _build_mcmod_section(item_pool, entity_pool)

    return f"""你是 Minecraft FTB Quests 任务书设计师。{cfg.PACK_INTRO}
为第 {chapter_index + 1} 章「{ctx["title"]}」生成第 {batch_index + 1} 批任务，共 {cfg.BATCH_SIZE} 个。

【本章焦点】{ctx["focus"]}
【整体要求】{ctx["extra"]}
【已有任务 key 列表】：{json.dumps(prev_keys, ensure_ascii=False)}
【可用物品 ID】：{json.dumps(item_pool[:40], ensure_ascii=False)}
【可用结构 ID】：{json.dumps(struct_pool, ensure_ascii=False)}
【可用实体 ID】：{json.dumps(entity_pool[:80], ensure_ascii=False)}
{mcmod_section}
【输出格式】严格输出 JSON 数组：
[
  {{"key": "t1", "type": "item", "id": "modid:item", "count": 5, "title": "标题", "desc": "描述", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "标题", "desc": "描述", "dependencies": ["t1"]}}
]
规则：
- 每批恰好 {cfg.BATCH_SIZE} 个任务
- 类型仅限：{", ".join(allowed)}
- 绝对不要编造 ID
"""

def call_deepseek(prompt, max_retries=3):
    url = f"{cfg.BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": cfg.MODEL,
        "messages": [{"role": "system", "content": "你只输出 JSON 数组。"}, {"role": "user", "content": prompt}],
        "temperature": 0.7, "max_tokens": 3000,
    }
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed: return parsed
            log(f"  [重试 {attempt+1}] AI 返回空列表")
        except Exception as e:
            log(f"  [重试 {attempt+1}] 失败: {e}")
    return []

def normalize_batch(batch, already, batch_index, valid_structures, valid_entities, allowed_types):
    cleaned = []
    for i, q in enumerate(batch):
        if not isinstance(q, dict): continue
        key = str(q.get("key") or f"b{batch_index}_{i+1}")
        deps = q.get("dependencies") or []
        if isinstance(deps, str): deps = [deps]
        
        raw_type = q.get("type")
        raw_id = _clean_str(q.get("id", ""))
        qtype, qid, count = "checkmark", "", None

        if raw_type == "item" and raw_id and "item" in allowed_types:
            qtype, qid = "item", raw_id
            count = max(1, int(q.get("count", 1)))
        elif raw_type == "structure" and raw_id in valid_structures and "structure" in allowed_types:
            qtype, qid = "structure", raw_id
        elif raw_type == "kill" and raw_id in valid_entities and "kill" in allowed_types:
            qtype, qid = "kill", raw_id
            count = max(1, int(q.get("count", 1)))

        cleaned.append({"key": key, "type": qtype, "id": qid, "count": count, "title": str(q.get("title", "任务")), "desc": str(q.get("desc", "")), "dependencies": deps})

    seen = set()
    for q in cleaned:
        while q["key"] in seen: q["key"] += "_1"
        seen.add(q["key"])

    valid = {q["key"] for q in already} | seen
    for q in cleaned: q["dependencies"] = [d for d in q["dependencies"] if d in valid and d != q["key"]]
    if cleaned and not already: cleaned[0]["dependencies"] = []
    return cleaned

def break_cycles(quests):
    graph = {q["key"]: list(q["dependencies"]) for q in quests}
    color = {k: 0 for k in graph}
    def dfs(node):
        color[node] = 1
        for dep in list(graph[node]):
            if color.get(dep, 0) == 1: graph[node].remove(dep)
            elif color.get(dep, 0) == 0: dfs(dep)
        color[node] = 2
    for k in list(graph):
        if color[k] == 0: dfs(k)
    for q in quests: q["dependencies"] = graph[q["key"]]

_REWARD_TABLE_ID_CACHE = {}
def _reward_table_id(key):
    if key not in _REWARD_TABLE_ID_CACHE: _REWARD_TABLE_ID_CACHE[key] = gen_hex_id()
    return _REWARD_TABLE_ID_CACHE[key]

def _is_reward_blacklisted(iid):
    for p in getattr(cfg, "REWARD_ITEM_BLACKLIST", []):
        if iid == p or iid.startswith(p + ":"): return True
    return False

def _pick_reward_items(pool, n):
    candidates = [i for i in pool if not _is_reward_blacklisted(i)] or list(pool)
    return random.sample(candidates, min(n, len(candidates))) if candidates else []

def calc_task_difficulty(quest, all_quests):
    type_base = {"checkmark": 1, "item": 2, "kill": 3, "structure": 4}.get(quest["type"], 2)
    count_score = (quest.get("count") or 1) * 0.3
    raw = type_base + count_score
    return min(5, max(1, int(raw)))

def _build_single_reward_table(quest, difficulty, item_pool, fallback_pool):
    tier = getattr(cfg, "DIFFICULTY_TIERS", {}).get({1:"trivial", 2:"easy", 3:"medium", 4:"hard", 5:"extreme"}[difficulty], {})
    table_id = _reward_table_id(f"diff_{quest['key']}_{difficulty}")
    picks = _pick_reward_items(item_pool, random.randint(*tier.get("item_count_range", (1, 3))))
    
    entries = [f'{{type:"item",item:"{iid}",count:{random.randint(1,3)},weight:{random.randint(1,5)}}}' for iid in picks]
    if not entries: entries.append('{type:"item",item:"minecraft:experience_bottle",count:1,weight:1}')

    snbt = f'{{\n    id: "{table_id}"\n    title: "{quest["title"][:20]} (Lv{difficulty})"\n    loot_size: 1\n    entries: [\n        {",".join(entries)}\n    ]\n}}'
    return table_id, snbt

def _calc_layout(quests, cols_per_row, col_spacing, row_spacing, start_x, start_y):
    for i, q in enumerate(quests):
        row = i // cols_per_row
        col = i % cols_per_row
        q["x"] = start_x + col * col_spacing
        q["y"] = start_y - row * row_spacing
    return quests

def _quest_to_snbt(q):
    snbt = f'{{\n'
    snbt += f'    id: "{q["key"]}"\n'
    if "x" in q: snbt += f'    x: {q["x"]:.1f}d\n'
    if "y" in q: snbt += f'    y: {q["y"]:.1f}d\n'
    
    if q["type"] == "item":
        snbt += f'    type: "item"\n'
        snbt += f'    item: "{q["id"]}"\n'
        if q.get("count") and q["count"] > 1: snbt += f'    count: {q["count"]}L\n'
    elif q["type"] == "kill":
        snbt += f'    type: "kill"\n'
        snbt += f'    entity: "{q["id"]}"\n'
        if q.get("count") and q["count"] > 1: snbt += f'    count: {q["count"]}L\n'
    elif q["type"] == "structure":
        snbt += f'    type: "structure"\n'
        snbt += f'    structure: "{q["id"]}"\n'
    elif q["type"] == "checkmark":
        snbt += f'    type: "checkmark"\n'

    snbt += f'    title: "{q["title"].replace(chr(34), chr(39))}"\n'
    snbt += f'    description: ["{q["desc"].replace(chr(34), chr(39))}"]\n'
    
    if q.get("dependencies"):
        deps_str = ", ".join([f'"{d}"' for d in q["dependencies"]])
        snbt += f'    dependencies: [{deps_str}]\n'
        
    if q.get("reward_table_id"):
        snbt += f'    rewards: [\n'
        snbt += f'        {{ type: "random", table_id: "{q["reward_table_id"]}" }}\n'
        snbt += f'    ]\n'

    snbt += f'}}'
    return snbt

def _chapter_to_snbt(ch_id, ch_title, ch_icon, quests):
    snbt = f'{{\n'
    snbt += f'    id: "{ch_id}"\n'
    snbt += f'    title: "{ch_title}"\n'
    if ch_icon: snbt += f'    icon: "{ch_icon}"\n'
    snbt += f'    default_quest_shape: "circle"\n'
    snbt += f'    quests: [\n'
    
    quest_strs = []
    for q in quests:
        q_str = _quest_to_snbt(q)
        q_str = "\n".join("        " + line for line in q_str.splitlines())
        quest_strs.append(q_str)
        
    snbt += ",\n".join(quest_strs)
    snbt += f'\n    ]\n'
    snbt += f'}}'
    return snbt

def main():
    random.seed(getattr(cfg, "RANDOM_SEED", None))
    init_log(getattr(cfg, "LOG_FILE", "logs/ftb_bate.log"))
    log(f"===== FTB Quests 任务书生成器启动 =====")

    _load_mcmod_cache()
    
    item_names = load_items(cfg.ITEMS_FILE)
    item_ids = list(item_names.keys())
    structures = load_structures(cfg.STRUCTURES_FILE)
    entities = load_entities(cfg.ENTITIES_FILE)
    global _modlist_map
    _modlist_map = load_modlist(cfg.MODLIST_FILE)

    log(f"[汇总] 物品 {len(item_ids)} | 结构 {len(structures)} | 实体 {len(entities)} | 模组 {len(_modlist_map)}")

    output_dir = getattr(cfg, "OUTPUT_DIR", "output")
    chapters_dir = os.path.join(output_dir, "chapters")
    rewards_dir = os.path.join(output_dir, "reward_tables")
    os.makedirs(chapters_dir, exist_ok=True)
    os.makedirs(rewards_dir, exist_ok=True)

    all_quests = []
    intro_quests = []

    if getattr(cfg, "GENERATE_PACK_INTRO", True):
        log("\n===== 生成整合包介绍章节 =====")
        intro_prompt = f"""你是 Minecraft FTB Quests 任务书设计师。{cfg.PACK_INTRO}
生成一个【整合包介绍】章节，恰好 3 个 checkmark 任务。输出纯 JSON 数组。"""
        batch = call_deepseek(intro_prompt)
        if batch:
            intro_quests = normalize_batch(batch, [], 0, set(structures), set(entities.keys()), ["checkmark"])
            for i, q in enumerate(intro_quests): q["dependencies"] = [] if i == 0 else [intro_quests[i - 1]["key"]]
            _calc_layout(intro_quests, cfg.COLS_PER_ROW, cfg.COL_SPACING, cfg.ROW_SPACING, cfg.START_X, cfg.START_Y)
            
            intro_ch_id = ID_POOL.new()
            with open(os.path.join(chapters_dir, "intro.snbt"), "w", encoding="utf-8") as f:
                f.write(_chapter_to_snbt(intro_ch_id, cfg.PACK_INTRO_CHAPTER_TITLE, cfg.PACK_INTRO_CHAPTER_ICON, intro_quests))
            all_quests.extend(intro_quests)

    flat = cfg.flatten_chapters()
    chapter_list_snbt = "{\n    default_hide_dependency_lines: false\n    chapters: [\n"
    groups_dict = {}

    if intro_quests:
        chapter_list_snbt += f'        "{intro_ch_id}"\n'
        groups_dict.setdefault(0, []).append(intro_ch_id)

    for ci, ch in enumerate(flat):
        log(f"\n----- 第 {ci+1}/{len(flat)} 章: {ch['title']} -----")
        ctx = chapter_context(ci)
        chapter_quests = []

        for bi in range(ch.get("batches", 1)):
            prompt = build_prompt(item_ids, structures, list(entities.keys()), ci, bi, chapter_quests)
            batch = call_deepseek(prompt)
            if not batch: continue
            cleaned = normalize_batch(batch, chapter_quests, bi, set(structures), set(entities.keys()), ctx["task_types"])
            if not chapter_quests and cleaned: cleaned[0]["dependencies"] = []
            chapter_quests.extend(cleaned)

        if chapter_quests:
            break_cycles(chapter_quests)
            _calc_layout(chapter_quests, cfg.COLS_PER_ROW, cfg.COL_SPACING, cfg.ROW_SPACING, cfg.START_X, cfg.START_Y)
            ch_id = ID_POOL.new()
            with open(os.path.join(chapters_dir, f"chapter_{ci+1:02d}.snbt"), "w", encoding="utf-8") as f:
                f.write(_chapter_to_snbt(ch_id, ch['title'], ctx["icon"], chapter_quests))
            chapter_list_snbt += f'        "{ch_id}"\n'
            groups_dict.setdefault(ctx["group_index"] + 1, []).append(ch_id)

        all_quests.extend(chapter_quests)

    # 奖励
    all_tables = {}
    for q in all_quests:
        diff = calc_task_difficulty(q, all_quests)
        tid, snbt = _build_single_reward_table(q, diff, item_ids, getattr(cfg, "REWARD_FALLBACK_POOL", []))
        all_tables[tid] = snbt
        q["reward_table_id"] = tid

    for tid, snbt in all_tables.items():
        with open(os.path.join(rewards_dir, f"{tid}.snbt"), "w", encoding="utf-8") as f: f.write(snbt)

    # 结尾文件
    chapter_list_snbt += "    ]\n}"
    with open(os.path.join(output_dir, "chapter_groups.snbt"), "w", encoding="utf-8") as f: f.write(chapter_list_snbt)
    
    with open(os.path.join(output_dir, "data.snbt"), "w", encoding="utf-8") as f:
        f.write('{\n    version: 1\n    title: "整合包任务"\n    icon: "minecraft:book"\n}\n')

    group_snbt = "{\n    chapter_groups: [\n"
    for g_idx in sorted(groups_dict.keys()):
        group_snbt += "        {\n"
        group_snbt += f'            id: "{ID_POOL.new()}"\n'
        group_snbt += f'            title: "第 {g_idx} 阶段"\n'
        group_snbt += '            chapters: [\n'
        for ch_id in groups_dict[g_idx]: group_snbt += f'                "{ch_id}"\n'
        group_snbt += '            ]\n        },\n'
    group_snbt = group_snbt.rstrip(",\n") + "\n    ]\n}\n"
    with open(os.path.join(output_dir, "chapter_groups.snbt"), "w", encoding="utf-8") as f: f.write(group_snbt)

    _save_mcmod_cache()
    log(f"\n===== 完成 =====")

if __name__ == "__main__":
    main()
