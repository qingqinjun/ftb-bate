# -*- coding: utf-8 -*-
"""
========================================================
ftb-bate —— FTB Quests 任务书自动生成器--本程序完全免费
========================================================
支持：
  - 章节组 / 章节 / 任务三层结构
  - item / checkmark / structure / kill 四种原生任务类型
  - 真实 reward_tables 生成，random 奖励引用真实表
  - 奖励物品优先从 items.json 动态构建
  - 依赖循环检测与修复
  - 章节 icon 自动校验，不在 items.json 时回退 ICON_FALLBACK
  - 整合包介绍章节自动生成（置于所有章节组之前）
  - 日志持久化
  - 数据文件递归解包
  - 任务语言切换（zh / en）
  - MC 百科：模组级攻略补充，优先读 modlist 的模组中文名
  - 奖励跟随任务难度动态变化
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
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    _LOG_FILE = open(path, "a", encoding="utf-8")


def close_log():
    global _LOG_FILE
    if _LOG_FILE:
        _LOG_FILE.close()
        _LOG_FILE = None


# ==================== ▼ MC百科 ====================
_mcmod_cache = {}
_mcmod_cache_dirty = False
_modlist_map = {}   # modid -> 模组名


def _load_mcmod_cache():
    global _mcmod_cache, _mcmod_cache_dirty
    path = getattr(cfg, "MCMOD_CACHE_FILE", None)
    if not path or not os.path.isfile(path):
        return
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
    if not _mcmod_cache_dirty:
        return
    path = getattr(cfg, "MCMOD_CACHE_FILE", None)
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_mcmod_cache, f, ensure_ascii=False, indent=2)
        log(f"[MC百科] 缓存已保存 {len(_mcmod_cache)} 条 -> {path}")
        _mcmod_cache_dirty = False
    except Exception as e:
        log(f"[MC百科] 缓存保存失败: {e}")


def _extract_summary_from_html(html, keyword):
    title = ""
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        title = re.sub(r"\s+", " ", title)

    desc = ""
    for pat in (
        r'<meta\s+name="description"\s+content="([^"]*)"',
        r'<meta\s+property="og:description"\s+content="([^"]*)"',
        r'<meta\s+name="Description"\s+content="([^"]*)"',
    ):
        m = re.search(pat, html, re.I)
        if m:
            desc = m.group(1).strip()
            break

    if not title and not desc:
        return ""
    parts = [f"关键词 {keyword}"]
    if title:
        parts.append(f"页面标题: {title[:100]}")
    if desc:
        parts.append(f"简介: {desc[:200]}")
    return "；".join(parts)


def _cn_keyword(keyword):
    if ":" not in keyword:
        return keyword
    prefix, rest = keyword.split(":", 1)

    name = _modlist_map.get(prefix)
    if name:
        return f"{name} {rest}"

    cn = getattr(cfg, "MCMOD_KEYWORD_MAP", {}).get(prefix)
    if cn:
        return f"{cn} {rest}"

    return keyword


def lookup_mcmod(keyword, timeout=None):
    global _mcmod_cache_dirty
    if not keyword:
        return ""
    if not getattr(cfg, "ENABLE_MCMOD_LOOKUP", False):
        return ""
    if keyword in _mcmod_cache:
        return _mcmod_cache[keyword]

    base = str(getattr(cfg, "MCMOD_API_BASE", "") or "").rstrip("/")
    if not base:
        _mcmod_cache[keyword] = ""
        return ""

    if timeout is None:
        timeout = getattr(cfg, "MCMOD_TIMEOUT", 10)

    query = _cn_keyword(keyword)
    try:
        resp = requests.get(
            base,
            params={"q": query, "key": query, "search": query},
            timeout=timeout,
            headers={"User-Agent": "ftb-bate/1.0"},
        )
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "").lower()

        text = ""
        if "json" in ctype:
            try:
                data = resp.json()
                title = summary = ""
                if isinstance(data, dict):
                    title = data.get("title") or data.get("name") or ""
                    summary = (data.get("summary") or data.get("desc")
                               or data.get("description") or "")
                    if not (title or summary) and isinstance(data.get("data"), dict):
                        d = data["data"]
                        title = d.get("title") or d.get("name") or ""
                        summary = (d.get("summary") or d.get("desc")
                                   or d.get("description") or "")
                parts = []
                if title:
                    parts.append(f"标题: {title}")
                if summary:
                    parts.append(f"简介: {str(summary)[:200]}")
                if parts:
                    text = "；".join(parts)
            except Exception:
                text = ""

        if not text:
            text = _extract_summary_from_html(resp.text, query)

        _mcmod_cache[keyword] = text
        _mcmod_cache_dirty = True
        return text
    except Exception as e:
        log(f"  [MC百科] 查询 {keyword} 失败: {e}")
        _mcmod_cache[keyword] = ""
        _mcmod_cache_dirty = True
        return ""


def _build_mcmod_section(item_pool, entity_pool):
    if not getattr(cfg, "ENABLE_MCMOD_LOOKUP", False):
        return ""
    max_n = int(getattr(cfg, "MCMOD_MAX_LOOKUP", 0) or 0)
    if max_n <= 0:
        return ""

    seen_modids = []
    for iid in list(item_pool) + list(entity_pool):
        if ":" not in iid:
            continue
        modid = iid.split(":", 1)[0]
        if modid not in seen_modids:
            seen_modids.append(modid)
        if len(seen_modids) >= max_n:
            break

    if not seen_modids:
        return ""

    log(f"  [MC百科] 本批查询 {len(seen_modids)} 个模组 ...")
    lines = []
    for modid in seen_modids:
        hint = lookup_mcmod(f"{modid}:main")
        if hint:
            lines.append(f"- {modid}: {hint}")

    if not lines:
        return ""
    return (
        "\n【MC百科补充资料】（模组级攻略，仅供参考，不要编造 ID）\n"
        + "\n".join(lines)
        + "\n"
    )
# ==================== ▲ MC百科 ====================


# ==================== 工具函数 ====================
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
        if attempt < retries:
            time.sleep(0.5)
    log(f"  [跳过] {desc} 读取失败 {retries} 次，跳过")
    return None


def _clean_str(s):
    return str(s).strip() if s is not None else ""


def _find_data_array(data, known_keys, depth=0):
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
    """读 structures.json（字符串数组），返回 ID 列表。"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    arr = None
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        arr, _ = _find_data_array(data, ("structures", "structure", "data", "list"))
    if not arr:
        return []
    out = []
    for e in arr:
        s = _clean_str(e)
        if s and ":" in s:
            out.append(s)
    return out


def _parse_modlist(filepath):
    """读 modlist.json（{modid: "name | version"}），返回 modid -> 模组名。"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    if isinstance(data, dict):
        for k, v in data.items():
            kid = _clean_str(k)
            if not kid:
                continue
            name = _clean_str(v)
            if "|" in name:
                name = name.split("|", 1)[0].strip()
            result[kid] = name or kid
    return result


def _parse_entities(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    arr, source = _find_data_array(
        data, ("entities", "entity", "data", "list", "items", "result", "values")
    )
    if arr is None:
        log(f"  [警告] 无法从 entities.json 中找到实体数组")
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
    data = load_file_with_retry(filepath, _parse_structures, "structures.json")
    if data is None:
        return []
    log(f"[加载] structures.json: {len(data)} 个结构")
    return data


def load_modlist(filepath):
    data = load_file_with_retry(filepath, _parse_modlist, "modlist.json")
    if data is None:
        return {}
    log(f"[加载] modlist.json: {len(data)} 个模组名映射")
    return data


def load_entities(filepath):
    data = load_file_with_retry(filepath, _parse_entities, "entities.json")
    if data is None:
        return {}
    log(f"[加载] entities.json: {len(data)} 个实体")
    return data


def filter_by_prefix(ids, prefixes):
    out = []
    for p in prefixes:
        out.extend([i for i in ids if i.startswith(p + ":")])
    return out


# ==================== 图标校验 ====================
def resolve_icon(icon, valid_items):
    icon = _clean_str(icon)
    fallback = getattr(cfg, "ICON_FALLBACK", "minecraft:book")
    if not icon:
        return ""
    if valid_items and icon not in valid_items:
        log(f"    [图标] {icon} 不在 items.json，回退为 {fallback}")
        return fallback
    return icon


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
        "task_types": ch.get("task_types", ["item", "checkmark"]),
        "icon": ch.get("icon", ""),
        "group_index": ch["_group_index"],
    }


# ==================== 提示词 ====================
def _prompt_zh(ctx, chapter_index, batch_index, already, item_pool, struct_pool,
               entity_pool, allowed, mcmod_section=""):
    prev_keys = [q["key"] for q in already]
    prev_desc = [f'{q["key"]}: {q["title"]}' for q in already[-8:]]

    if not already:
        chain_hint = (
            "这是本章第一批任务。第一个任务的 dependencies 必须为空数组 []，它作为本章根节点。"
            "后续任务可以自由连接，允许分支或孤立任务，不强制全部串联。"
        )
    else:
        chain_hint = (
            "这是后续批次。新任务可以引用已有任务的 key 作为依赖，但不必强制串联。"
            "允许独立任务、分支任务。dependencies 可以为空数组。"
        )

    type_lines = []
    if "item" in allowed:
        type_lines.append('item 类型：需要真实物品 "id"，可选 "count"（整数，默认 1）')
    if "checkmark" in allowed:
        type_lines.append('checkmark 类型：仅需 title/desc，用于仪式、对话、阶段标记')
    if "structure" in allowed:
        type_lines.append('structure 类型：必须从【可用结构 ID】中选择真实 "id"')
    if "kill" in allowed:
        type_lines.append('kill 类型：必须从【可用实体 ID】逐字复制 "id"，并给 "count"')
    type_hint = "本章允许的任务类型：\n- " + "\n- ".join(type_lines)

    difficulty_hint = (
        f"【难度感知】当前是第 {batch_index + 1} 批，"
        f"批次越靠后任务应越难（count 更大、依赖更深、优先用高难度任务类型）。"
        f"奖励会根据难度自动调整。"
    )

    return f"""你是 Minecraft FTB Quests 任务书设计师。{cfg.PACK_INTRO}

为第 {chapter_index + 1} 章「{ctx["title"]}」生成第 {batch_index + 1} 批任务，共 {cfg.BATCH_SIZE} 个。

【本章焦点】{ctx["focus"]}
【整体要求】{ctx["extra"]}
【串联要求】{chain_hint}
{difficulty_hint}

【已有任务 key 列表】（dependencies 只能从这里选，或选本批前面任务的 key）：
{json.dumps(prev_keys, ensure_ascii=False)}

【已有任务示例】（最近 8 个）：
{json.dumps(prev_desc, ensure_ascii=False)}

【可用物品 ID】（必须使用真实 ID，禁止编造）：
{json.dumps(item_pool[:40], ensure_ascii=False)}

【可用结构 ID】（structure 类型必须使用真实 ID）：
{json.dumps(struct_pool, ensure_ascii=False)}

【可用实体 ID】（kill 类型必须逐字复制）：
{json.dumps(entity_pool[:80], ensure_ascii=False)}
{mcmod_section}
【输出格式】严格输出 JSON 数组，不要 Markdown 代码块：
[
  {{"key": "t1", "type": "item", "id": "modid:item_name", "count": 5, "title": "中文标题", "desc": "中文描述", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "中文标题", "desc": "中文描述", "dependencies": ["t1"]}},
  {{"key": "t3", "type": "structure", "id": "modid:structure_name", "title": "中文标题", "desc": "中文描述", "dependencies": ["t2"]}},
  {{"key": "t4", "type": "kill", "id": "minecraft:zombie", "count": 10, "title": "中文标题", "desc": "中文描述", "dependencies": []}}
]

规则：
- 每批恰好 {cfg.BATCH_SIZE} 个任务
- key 在本章内唯一，用 t1/t2/... 短名
- {type_hint}
- dependencies 是 key 数组，可为空
- title ≤ 12 字，desc ≤ 30 字
- 绝对不要编造物品、结构或实体 ID
"""


def _prompt_en(ctx, chapter_index, batch_index, already, item_pool, struct_pool,
               entity_pool, allowed, mcmod_section=""):
    prev_keys = [q["key"] for q in already]
    prev_desc = [f'{q["key"]}: {q["title"]}' for q in already[-8:]]

    if not already:
        chain_hint = (
            "First batch of this chapter. The first quest's dependencies MUST be []; "
            "later quests may branch freely."
        )
    else:
        chain_hint = (
            "Follow-up batch. New quests may reference existing keys; chaining is optional."
        )

    type_lines = []
    if "item" in allowed:
        type_lines.append('item quest: real "id" required; optional integer "count"')
    if "checkmark" in allowed:
        type_lines.append('checkmark quest: title/desc only')
    if "structure" in allowed:
        type_lines.append('structure quest: "id" MUST be a real structure ID')
    if "kill" in allowed:
        type_lines.append('kill quest: "id" MUST be copied verbatim; add integer "count"')
    type_hint = "Allowed quest types:\n- " + "\n- ".join(type_lines)

    difficulty_hint = (
        f"[Difficulty] This is batch {batch_index + 1}; later batches should be harder "
        f"(higher count, deeper dependencies, prefer harder task types). "
        f"Rewards scale with difficulty automatically."
    )

    return f"""You are a Minecraft FTB Quests designer. {cfg.PACK_INTRO}

Generate batch {batch_index + 1} of Chapter {chapter_index + 1} "{ctx["title"]}", total {cfg.BATCH_SIZE} quests.

[Chapter focus] {ctx["focus"]}
[Overall requirements] {ctx["extra"]}
[Chaining rule] {chain_hint}
{difficulty_hint}

[Existing quest keys]:
{json.dumps(prev_keys, ensure_ascii=False)}

[Recent quest examples]:
{json.dumps(prev_desc, ensure_ascii=False)}

[Available item IDs] (must be real):
{json.dumps(item_pool[:40], ensure_ascii=False)}

[Available structure IDs]:
{json.dumps(struct_pool, ensure_ascii=False)}

[Available entity IDs]:
{json.dumps(entity_pool[:80], ensure_ascii=False)}
{mcmod_section}
[Output format] Output ONLY a JSON array, no Markdown:
[
  {{"key": "t1", "type": "item", "id": "modid:item_name", "count": 5, "title": "English title", "desc": "English description", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "English title", "desc": "English description", "dependencies": ["t1"]}},
  {{"key": "t3", "type": "structure", "id": "modid:structure_name", "title": "English title", "desc": "English description", "dependencies": ["t2"]}},
  {{"key": "t4", "type": "kill", "id": "minecraft:zombie", "count": 10, "title": "English title", "desc": "English description", "dependencies": []}}
]

Rules:
- Exactly {cfg.BATCH_SIZE} quests
- key unique within this chapter
- {type_hint}
- dependencies is a key array, may be empty
- title ≤ 5 words, desc ≤ 15 words
- All title/desc MUST be in English
- NEVER invent IDs
"""


def build_prompt(item_ids, structures, entity_ids, chapter_index, batch_index, already):
    ctx = chapter_context(chapter_index)

    allowed = list(ctx["task_types"])
    if not structures and "structure" in allowed:
        allowed.remove("structure")
    if not entity_ids and "kill" in allowed:
        allowed.remove("kill")
    if not allowed:
        allowed = ["item", "checkmark"]

    item_pool = filter_by_prefix(item_ids, ctx["item_prefixes"]) if ctx["item_prefixes"] else []
    if not item_pool:
        item_pool = item_ids[:60]
    struct_pool = structures[:20] if ctx["use_structures"] else []
    entity_pool = filter_by_prefix(entity_ids, ctx["entity_prefixes"]) if ctx["entity_prefixes"] else []
    if not entity_pool and ctx["entity_prefixes"]:
        entity_pool = entity_ids[:30]

    mcmod_section = _build_mcmod_section(item_pool, entity_pool)

    if is_en():
        return _prompt_en(ctx, chapter_index, batch_index, already,
                          item_pool, struct_pool, entity_pool, allowed, mcmod_section)
    return _prompt_zh(ctx, chapter_index, batch_index, already,
                      item_pool, struct_pool, entity_pool, allowed, mcmod_section)


# ==================== 整合包介绍章节提示词 ====================
def build_intro_prompt():
    mods = sorted(set(_modlist_map.values()))
    mod_lines = "\n".join(f"- {m}" for m in mods[:40]) if mods else "（无 modlist）"
    n = int(getattr(cfg, "PACK_INTRO_TASK_COUNT", 3))

    if is_en():
        return f"""You are a Minecraft FTB Quests designer. {cfg.PACK_INTRO}

Generate an INTRODUCTORY chapter with exactly {n} checkmark quests that teach the player what this modpack is about.
All quests MUST be type "checkmark" (title/desc only, no id).
All titles/descs MUST be in English.

[Mods in this pack]
{mod_lines}

[Output format] Output ONLY a JSON array:
[
  {{"key": "t1", "type": "checkmark", "title": "Welcome", "desc": "Overview of the pack", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "Core Mods", "desc": "Main gameplay mods", "dependencies": ["t1"]}}
]

Rules:
- Exactly {n} quests
- title ≤ 5 words, desc ≤ 15 words
"""

    return f"""你是 Minecraft FTB Quests 任务书设计师。{cfg.PACK_INTRO}

生成一个【整合包介绍】章节，恰好 {n} 个 checkmark 任务，向玩家介绍本整合包。
全部任务必须是 type="checkmark"（只有 title/desc，不要 id）。

【本整合包的模组列表】
{mod_lines}

【输出格式】严格输出 JSON 数组：
[
  {{"key": "t1", "type": "checkmark", "title": "欢迎", "desc": "整合包总览", "dependencies": []}},
  {{"key": "t2", "type": "checkmark", "title": "核心模组", "desc": "主要玩法模组", "dependencies": ["t1"]}}
]

规则：
- 恰好 {n} 个任务
- title ≤ 12 字，desc ≤ 30 字
"""


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
            {"role": "system", "content": "You output only a JSON array, no explanation, no Markdown."
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
def normalize_batch(batch, already, batch_index,
                    valid_structures=None, valid_entities=None,
                    allowed_types=None):
    valid_structures = set(valid_structures or [])
    valid_entities   = set(valid_entities or [])
    allowed_types    = set(allowed_types or ["item", "checkmark"])

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
        qtype, qid, count = "checkmark", "", None

        if raw_type == "item" and raw_id and "item" in allowed_types:
            qtype, qid = "item", raw_id
            try:
                count = max(1, int(q.get("count", 1)))
            except (TypeError, ValueError):
                count = 1
        elif (raw_type == "structure" and raw_id
              and raw_id in valid_structures and "structure" in allowed_types):
            qtype, qid = "structure", raw_id
        elif (raw_type == "kill" and raw_id
              and raw_id in valid_entities and "kill" in allowed_types):
            qtype, qid = "kill", raw_id
            try:
                count = max(1, int(q.get("count", 1)))
            except (TypeError, ValueError):
                count = 1
        else:
            if raw_type in ("structure", "kill") and raw_id:
                log(f"    [警告] {raw_type} ID 无效或未被允许: {raw_id}，降级为 checkmark")
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

    seen = set()
    for q in cleaned:
        base = q["key"]
        n = 1
        while q["key"] in seen:
            n += 1
            q["key"] = f"{base}_{n}"
        seen.add(q["key"])

    valid = existing_keys | {q["key"] for q in cleaned}
    for q in cleaned:
        q["dependencies"] = [d for d in q["dependencies"] if d in valid and d != q["key"]]

    if cleaned and not already:
        cleaned[0]["dependencies"] = []

    return cleaned


# ==================== 依赖循环检测 ====================
def break_cycles(quests):
    graph = {q["key"]: list(q["dependencies"]) for q in quests}
    color = {k: 0 for k in graph}
    removed = [0]

    def dfs(node):
        color[node] = 1
        for dep in list(graph[node]):
            c = color.get(dep, 0)
            if c == 1:
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

_REWARD_FALLBACK_POOL = [
    "minecraft:emerald", "minecraft:diamond", "minecraft:gold_ingot",
    "minecraft:iron_ingot", "minecraft:experience_bottle",
]


def _reward_table_id(key):
    if key not in _REWARD_TABLE_ID_CACHE:
        _REWARD_TABLE_ID_CACHE[key] = gen_hex_id()
    return _REWARD_TABLE_ID_CACHE[key]


def _is_reward_blacklisted(iid):
    blacklist = getattr(cfg, "REWARD_ITEM_BLACKLIST", [])
    for p in blacklist:
        if iid == p or ((":" not in p) and iid.startswith(p + ":")):
            return True
    keywords = getattr(cfg, "REWARD_ITEM_BLACKLIST_KEYWORDS", [])
    low = iid.lower()
    for kw in keywords:
        if kw and kw in low:
            return True
    return False


def _pick_reward_items(pool, n):
    if not pool:
        return []
    candidates = [i for i in pool if not _is_reward_blacklisted(i)]
    if not candidates:
        candidates = list(pool)
    if len(candidates) <= n:
        return candidates[:]
    return random.sample(candidates, n)


def _pick_random_item_for_quest(item_pool):
    if item_pool:
        candidates = [i for i in item_pool if not _is_reward_blacklisted(i)]
        if candidates:
            return random.choice(candidates)
    return random.choice(_REWARD_FALLBACK_POOL)


def build_reward_table_snbt(key, item_pool=None):
    spec = cfg.REWARD_TABLES.get(key)

    if getattr(cfg, "REWARD_AUTO_FROM_ITEMS", False) and item_pool:
        n = getattr(cfg, "REWARD_TABLE_SIZE", 4)
        picks = _pick_reward_items(item_pool, n)
        if picks:
            entries = []
            lo, hi = getattr(cfg, "REWARD_ITEM_COUNT_RANGE", (1, 3))
            for i, iid in enumerate(picks):
                w = max(1, len(picks) - i)
                cnt = random.randint(lo, hi)
                entries.append(
                    f'{{type:"item",item:"{iid}",count:{cnt},weight:{w}}}'
                )
            title = spec["title"] if spec else key.title()
            table_id = _reward_table_id(key)
            return table_id, f'''{{
    id: "{table_id}"
    title: "{title}"
    loot_size: 1
    entries: [
        {",".join(entries)}
    ]
}}'''

    if spec is None:
        log(f"  [警告] 奖励表 {key} 不存在且无可用物品池，跳过")
        return _reward_table_id(key), "{}"

    entries = []
    for e in spec["entries"]:
        entries.append(
            f'{{type:"item",item:"{e["item"]}",count:{e["count"]},weight:{e.get("weight",1)}}}'
        )
    title = spec.get("title", key)
    table_id = _reward_table_id(key)
    return table_id, f'''{{
    id: "{table_id}"
    title: "{title}"
    loot_size: {spec.get("loot_size", 1)}
    entries: [
        {",".join(entries)}
    ]
}}'''


# ==================== 难度奖励系统 ====================
def _default_difficulty_tiers():
    return {
        "trivial": {"weight_range": (1, 2), "item_count_range": (1, 2),
                    "reward_tables_ref": ["common"], "description": "简单任务"},
        "easy": {"weight_range": (2, 4), "item_count_range": (2, 4),
                 "reward_tables_ref": ["common", "uncommon"], "description": "普通任务"},
        "medium": {"weight_range": (3, 6), "item_count_range": (3, 6),
                   "reward_tables_ref": ["uncommon", "rare"], "description": "中等任务"},
        "hard": {"weight_range": (5, 10), "item_count_range": (5, 10),
                 "reward_tables_ref": ["rare", "epic"], "description": "困难任务"},
        "extreme": {"weight_range": (8, 16), "item_count_range": (8, 20),
                    "reward_tables_ref": ["epic", "legendary"], "description": "极限任务"},
    }


def _default_task_type_difficulty():
    return {"checkmark": 1, "item": 2, "kill": 3, "structure": 4}


def calc_task_difficulty(quest, all_quests):
    if not getattr(cfg, "ENABLE_DIFFICULTY_REWARDS", True):
        return 1

    type_base_map = getattr(cfg, "TASK_TYPE_DIFFICULTY",
                            _default_task_type_difficulty())
    type_base = type_base_map.get(quest["type"], 2)

    count_factor = getattr(cfg, "COUNT_DIFFICULTY_FACTOR", 0.3)
    count_val = quest.get("count") or 1
    count_score = count_val * count_factor

    depth_weight = getattr(cfg, "DEP_DEPTH_WEIGHT", 0.5)
    depth = _calc_dep_depth(quest, all_quests)
    depth_score = depth * depth_weight

    rare_mods = getattr(cfg, "RARE_MOD_PREFIXES", [])
    mod_bonus = 0
    qid = quest.get("id", "")
    if ":" in qid:
        modid = qid.split(":", 1)[0]
        if modid in rare_mods:
            mod_bonus = 1

    raw = type_base + count_score + depth_score + mod_bonus

    if raw <= 1.5:
        return 1
    elif raw <= 2.5:
        return 2
    elif raw <= 4.0:
        return 3
    elif raw <= 6.0:
        return 4
    else:
        return 5


def _calc_dep_depth(quest, all_quests):
    key_to_quest = {q["key"]: q for q in all_quests}
    visited = set()
    max_depth = 0

    def dfs(node_key, current_depth):
        nonlocal max_depth
        if node_key in visited:
            return
        visited.add(node_key)
        max_depth = max(max_depth, current_depth)
        node = key_to_quest.get(node_key)
        if node:
            for dep in node.get("dependencies", []):
                dfs(dep, current_depth + 1)

    dfs(quest["key"], 0)
    return max_depth


def difficulty_to_tier_name(difficulty):
    return {1: "trivial", 2: "easy", 3: "medium", 4: "hard", 5: "extreme"}.get(difficulty, "easy")


def _tier_for_difficulty(difficulty):
    tiers = getattr(cfg, "DIFFICULTY_TIERS", _default_difficulty_tiers())
    tier_name = difficulty_to_tier_name(difficulty)
    return tiers.get(tier_name, tiers.get("easy", {}))


def _select_reward_items_for_tier(tier, item_pool, fallback_pool):
    lo, hi = tier.get("item_count_range", (1, 3))
    n = random.randint(int(lo), max(int(lo), int(hi)))

    pool = list(item_pool) if item_pool else []
    pool = [i for i in pool if not _is_reward_blacklisted(i)]

    fb = list(fallback_pool) if fallback_pool else []
    fb = [i for i in fb if not _is_reward_blacklisted(i)]

    if len(pool) < n:
        pool = pool + fb

    if not pool:
        return []

    n = min(n, len(pool))
    return random.sample(pool, n)


def _build_single_reward_table(quest, difficulty, item_pool, fallback_pool):
    tier = _tier_for_difficulty(difficulty)
    tier_name = difficulty_to_tier_name(difficulty)
    table_id = _reward_table_id(f"diff_{quest['key']}_{difficulty}")

    picks = _select_reward_items_for_tier(tier, item_pool, fallback_pool)

    entries = []
    if picks:
        weight_range = tier.get("weight_range", (1, 3))
        lo, hi = tier.get("item_count_range", (1, 3))
        for iid in picks:
            w = random.randint(int(weight_range[0]), int(weight_range[1]))
            cnt = random.randint(int(lo), max(int(lo), int(hi)))
            entries.append(
                f'{{type:"item",item:"{iid}",count:{cnt},weight:{w}}}'
            )
    else:
        entries.append(
            f'{{type:"item",item:"minecraft:experience_bottle",count:1,weight:1}}'
        )

    loot_size = 1 if difficulty <= 3 else random.randint(1, 2)

    snbt = f'''{{
    id: "{table_id}"
    title: "{quest["title"][:20]} (Lv{difficulty})"
    loot_size: {loot_size}
    entries: [
        {",".join(entries)}
    ]
}}'''

    return table_id, snbt, tier_name


def assign_difficulty_rewards(quests, item_pool):
    if not getattr(cfg, "ENABLE_DIFFICULTY_REWARDS", True):
        return {}

    fallback_pool = getattr(cfg, "REWARD_FALLBACK_POOL", _REWARD_FALLBACK_POOL)

    log(f"[难度奖励] 开始为 {len(quests)} 个任务计算难度并生成奖励...")

    reward_map = {}
    diff_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for q in quests:
        diff = calc_task_difficulty(q, quests)
        diff_distribution[diff] = diff_distribution.get(diff, 0) + 1

        table_id, snbt, tier_name = _build_single_reward_table(
            q, diff, item_pool, fallback_pool
        )

        reward_map[q["key"]] = {
            "table_id": table_id,
            "snbt": snbt,
            "difficulty": diff,
            "tier": tier_name,
        }

    log(f"[难度奖励] 难度分布: " + ", ".join(
        f"Lv{k}={v}" for k, v in sorted(diff_distribution.items()) if v > 0
    ))
    log(f"[难度奖励] 共生成 {len(reward_map)} 张难度奖励表")

    return reward_map


def build_difficulty_reward_tables(quests, item_pool):
    reward_map = assign_difficulty_rewards(quests, item_pool)

    tables = {}
    q_to_table = {}
    for qkey, info in reward_map.items():
        tables[info["table_id"]] = info["snbt"]
        q_to_table[qkey] = info["table_id"]

    return tables, q_to_table


def attach_rewards_to_quests(quests, item_pool):
    if not getattr(cfg, "ENABLE_DIFFICULTY_REWARDS", True):
        return {}

    tables, q_to_table = build_difficulty_reward_tables(quests, item_pool)

    for q in quests:
        if q["key"] in q_to_table:
            q["reward_table_id"] = q_to_table[q["key"]]

    return tables


# ==================== 主流程 ====================
def main():
    random.seed(getattr(cfg, "RANDOM_SEED", None))
    if getattr(cfg, "RANDOM_SEED", None) is not None:
        log(f"[随机] 已设置随机种子: {cfg.RANDOM_SEED}")

    init_log(getattr(cfg, "LOG_FILE", "logs/ftb_bate.log"))
    log(f"===== FTB Quests 任务书生成器启动 =====")
    log(f"[时间] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"[语言] {'English' if is_en() else '中文'}")
    log(f"[难度奖励] {'开启' if getattr(cfg, 'ENABLE_DIFFICULTY_REWARDS', True) else '关闭'}")

    # ---- 加载数据 ----
    items_path = getattr(cfg, "ITEMS_FILE", "dumpids/items.json")
    structs_path = getattr(cfg, "STRUCTURES_FILE", "dumpids/structures.json")
    modlist_path = getattr(cfg, "MODLIST_FILE", "dumpids/modlist.json")
    entities_path = getattr(cfg, "ENTITIES_FILE", "dumpids/entities.json")

    _load_mcmod_cache()

    global _modlist_map
    _modlist_map = load_modlist(modlist_path)
    item_names = load_items(items_path)
    item_ids = list(item_names.keys())
    structures = load_structures(structs_path)
    entity_ids = list(load_entities(entities_path).keys())

    log(f"[汇总] 物品 {len(item_ids)} | 结构 {len(structures)} | 实体 {len(entity_ids)} | 模组 {len(_modlist_map)}")

    # ---- 生成整合包介绍章节 ----
    all_quests = []
    intro_quests = []

    if getattr(cfg, "GENERATE_PACK_INTRO", True):
        log("\n===== 生成整合包介绍章节 =====")
        intro_prompt = build_intro_prompt()
        batch = []
        for attempt in range(2):
            batch = call_deepseek(intro_prompt)
            if batch:
                break
            log("  [重试] 整合包介绍章节生成失败，重试...")

        if batch:
            intro_quests = normalize_batch(
                batch, [], 0,
                valid_structures=set(structures),
                valid_entities=set(entity_ids),
                allowed_types=["checkmark"],
            )
            for i, q in enumerate(intro_quests):
                q["dependencies"] = [] if i == 0 else [intro_quests[i - 1]["key"]]
            all_quests.extend(intro_quests)
            log(f"  [完成] 整合包介绍章节: {len(intro_quests)} 个任务")

    # ---- 逐章生成 ----
    flat = cfg.flatten_chapters()
    log(f"\n===== 共 {len(flat)} 个章节，开始生成 =====")

    for ci, ch in enumerate(flat):
        log(f"\n----- 第 {ci+1}/{len(flat)} 章: {ch['title']} -----")
        ctx = chapter_context(ci)

        n_batches = ch.get("batches", 1)
        chapter_quests = []

        for bi in range(n_batches):
            log(f"  [批次 {bi+1}/{n_batches}]")
            prompt = build_prompt(
                item_ids, structures, entity_ids,
                ci, bi, chapter_quests
            )

            batch = call_deepseek(prompt)
            if not batch:
                log(f"    [跳过] 批次 {bi+1} 生成失败")
                continue

            cleaned = normalize_batch(
                batch, chapter_quests, bi,
                valid_structures=set(structures),
                valid_entities=set(entity_ids),
                allowed_types=ctx["task_types"],
            )

            if not chapter_quests and cleaned:
                cleaned[0]["dependencies"] = []

            chapter_quests.extend(cleaned)
            log(f"    [完成] 本批次 {len(cleaned)} 个任务，本章累计 {len(chapter_quests)} 个")

        if chapter_quests:
            n_fixed = break_cycles(chapter_quests)
            if n_fixed:
                log(f"    [循环修复] 断开了 {n_fixed} 个循环依赖")

        all_quests.extend(chapter_quests)

    # ---- 全局循环检测 ----
    log(f"\n===== 全局循环检测 =====")
    total_fixed = break_cycles(all_quests)
    if total_fixed:
        log(f"  [全局循环修复] 断开了 {total_fixed} 个循环依赖")
    else:
        log(f"  [全局循环检测] 无循环依赖 ✓")

    # ---- 难度奖励生成 ----
    difficulty_tables = {}
    if getattr(cfg, "ENABLE_DIFFICULTY_REWARDS", True):
        log(f"\n===== 难度奖励生成 =====")
        difficulty_tables = attach_rewards_to_quests(all_quests, item_ids)

        sample_n = min(5, len(all_quests))
        log(f"  [预览] 前 {sample_n} 个任务的奖励:")
        for q in all_quests[:sample_n]:
            if "reward_table_id" in q:
                diff = calc_task_difficulty(q, all_quests)
                log(f"    - {q['key']} ({q['type']}, Lv{diff}): {q.get('reward_table_id', 'N/A')[:16]}...")
    else:
        log(f"\n===== 难度奖励已关闭，跳过 =====")

    # ---- 构建原有奖励表 ----
    log(f"\n===== 生成奖励表 =====")
    all_reward_tables = {}

    if hasattr(cfg, 'REWARD_TABLES') and cfg.REWARD_TABLES:
        for key, spec in cfg.REWARD_TABLES.items():
            tid, snbt = build_reward_table_snbt(key, item_ids)
            all_reward_tables[tid] = snbt
            log(f"  [奖励表] {key} -> {tid[:16]}...")

    all_reward_tables.update(difficulty_tables)
    log(f"  [总计] 共 {len(all_reward_tables)} 张奖励表")

    # ---- 输出文件 ----
    output_dir = getattr(cfg, "OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)

    rt_path = os.path.join(output_dir, "reward_tables.snbt")
    with open(rt_path, "w", encoding="utf-8") as f:
        for tid, snbt in all_reward_tables.items():
            f.write(snbt + "\n\n")
    log(f"  [写出] 奖励表 -> {rt_path}")

    quests_out = []
    for q in all_quests:
        q_out = {
            "key": q["key"],
            "type": q["type"],
            "title": q["title"],
            "desc": q["desc"],
            "dependencies": q["dependencies"],
        }
        if q.get("id"):
            q_out["id"] = q["id"]
        if q.get("count"):
            q_out["count"] = q["count"]
        if q.get("reward_table_id"):
            q_out["reward_table"] = q["reward_table_id"]
        quests_out.append(q_out)

    q_path = os.path.join(output_dir, "quests.json")
    with open(q_path, "w", encoding="utf-8") as f:
        json.dump(quests_out, f, ensure_ascii=False, indent=2)
    log(f"  [写出] 任务 -> {q_path} ({len(quests_out)} 个)")

    _save_mcmod_cache()
    log(f"\n===== 完成 =====")
    log(f"[统计] 总任务 {len(all_quests)} 个 | 奖励表 {len(all_reward_tables)} 张")
    close_log()


if __name__ == "__main__":
    main()