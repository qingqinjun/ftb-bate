# -*- coding: utf-8 -*-
"""
========================================================
ftb-bate —— FTB Quests 任务书自动生成器
========================================================
支持：
  - 章节组 / 章节 / 任务三层结构
  - item / checkmark / structure / kill 四种任务类型
  - 真实 reward_tables 生成，random 奖励引用真实表
  - 奖励物品优先从 items.json 动态构建
  - 依赖循环检测与修复
  - 章节 icon 自动校验，不在 items.json 时回退 ICON_FALLBACK
  - 整合包介绍章节自动生成（置于所有章节组之前）
  - 日志持久化
  - 数据文件递归解包
  - 任务语言切换（zh / en）
  - MC 百科：模组级攻略补充，优先读 modlist.txt 的模组中文名
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


# ==================== ▼ MC百科：模组级攻略补充 ====================
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
    """modid:item -> 模组中文名 item；用于 MC 百科模组级搜索。"""
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
    """只对模组级查询：把一批 ID 按 modid 去重，每个 modid 查一次。"""
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
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return [l for l in lines if ":" in l and not l.startswith("#")]


def _parse_modlist(filepath):
    """解析 modlist.txt，返回 dict: modid -> 模组名。"""
    modid_to_name = {}
    pat = re.compile(
        r'^\s*(?P<name>.+?)\s{2,}(?P<modid>[a-z_0-9]+)\s{2,}(?P<ver>[^\s<]+)?'
    )
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            stripped = line.lstrip()
            if stripped.startswith("Название") or stripped.startswith("---"):
                continue
            m = pat.match(line)
            if not m:
                continue
            name = m.group("name").strip()
            modid = m.group("modid").strip()
            if not modid or ":" in modid:
                continue
            if name and modid and modid not in modid_to_name:
                modid_to_name[modid] = name
    return modid_to_name


def _parse_entities(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    arr, source = _find_data_array(
        data, ("entities", "entity", "data", "list", "items", "result", "values")
    )
    if arr is None:
        log(f"  [警告] 无法从 entities_list.json 中找到实体数组")
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
        return {}
    log(f"[加载] modlist.txt: {len(data)} 个模组名映射")
    return data


def load_entities(filepath):
    data = load_file_with_retry(filepath, _parse_entities, "entities_list.json")
    if data is None:
        return {}
    log(f"[加载] entities_list.json: {len(data)} 个实体")
    return data


def filter_by_prefix(ids, prefixes):
    out = []
    for p in prefixes:
        out.extend([i for i in ids if i.startswith(p + ":")])
    return out


# ==================== 图标校验 ====================
def resolve_icon(icon, valid_items):
    """章节 icon 校验：为空或不在 items.json 时回退 ICON_FALLBACK。"""
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

    return f"""你是 Minecraft FTB Quests 任务书设计师。{cfg.PACK_INTRO}

为第 {chapter_index + 1} 章「{ctx["title"]}」生成第 {batch_index + 1} 批任务，共 {cfg.BATCH_SIZE} 个。

【本章焦点】{ctx["focus"]}
【整体要求】{ctx["extra"]}
【串联要求】{chain_hint}

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

    return f"""You are a Minecraft FTB Quests designer. {cfg.PACK_INTRO}

Generate batch {batch_index + 1} of Chapter {chapter_index + 1} "{ctx["title"]}", total {cfg.BATCH_SIZE} quests.

[Chapter focus] {ctx["focus"]}
[Overall requirements] {ctx["extra"]}
[Chaining rule] {chain_hint}

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
    table_id = _reward_table_id(key)
    return table_id, f'''{{
    id: "{table_id}"
    title: "{spec["title"]}"
    loot_size: 1
    entries: [
        {",".join(entries)}
    ]
}}'''


def build_reward_snbt(quest_type, table_id, item_pool=None):
    rewards = []
    if quest_type == "structure":
        xp = random.choice([30, 40, 50, 60])
        item_chance, random_chance = 1.0, 0.6
    elif quest_type == "kill":
        xp = random.choice([10, 15, 20, 25])
        item_chance, random_chance = 0.6, 0.3
    else:
        xp = random.choice([5, 10, 15, 20])
        item_chance, random_chance = 0.5, 0.2

    rewards.append(f'{{type:"xp",amount:{xp}}}')

    if random.random() < item_chance:
        rid = _pick_random_item_for_quest(item_pool)
        lo, hi = getattr(cfg, "REWARD_ITEM_COUNT_RANGE", (1, 3))
        cnt = random.randint(lo, hi)
        rewards.append(f'{{type:"item",item:"{rid}",count:{cnt}}}')

    if random.random() < random_chance and table_id:
        rewards.append(f'{{type:"random",count:1,table_id:"{table_id}"}}')

    return "[" + ",".join(rewards) + "]"


# ==================== SNBT 生成 ====================
def build_snbt_quest(quest, key_to_id, x, y, reward_table_id, item_pool=None):
    qid = key_to_id[quest["key"]]
    title = quest["title"].replace('"', '\\"')
    desc = quest["desc"].replace('"', '\\"')
    deps = [key_to_id[d] for d in quest["dependencies"] if d in key_to_id]
    dep_str = "[" + ", ".join(f'"{d}"' for d in deps) + "]" if deps else "[]"

    if quest["type"] == "item":
        cnt = quest.get("count") or 1
        tasks = f'[{{type:"item",item:"{quest["id"]}",count:{cnt}}}]'
    elif quest["type"] == "structure":
        tasks = f'[{{type:"structure",structure:"{quest["id"]}"}}]'
    elif quest["type"] == "kill":
        cnt = quest.get("count") or 1
        tasks = f'[{{type:"kill",entity:"{quest["id"]}",count:{cnt}}}]'
    else:
        tasks = '[{type:"checkmark"}]'

    rewards = build_reward_snbt(quest["type"], reward_table_id, item_pool)

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


def generate_chapter_snbt(chapter_index, quests, group_id, item_ids,
                          icon_override=None, title_override=None, filename_override=None):
    ctx = chapter_context(chapter_index) if chapter_index is not None else {}
    chapter_id = ID_POOL.new()

    if filename_override:
        filename = filename_override
    elif chapter_index is not None:
        filename = f"chapter_{chapter_index + 1:02d}"
    else:
        filename = "chapter_intro"

    title = title_override or ctx.get("title", "章节")

    key_to_id = {q["key"]: ID_POOL.new() for q in quests}

    chapter_pool = (filter_by_prefix(item_ids, ctx.get("item_prefixes", []))
                    if ctx.get("item_prefixes") else item_ids[:])
    if not chapter_pool:
        chapter_pool = item_ids[:]

    if ctx.get("use_structures"):
        rtable_key = "structure"
    elif chapter_index is not None and chapter_index >= cfg.TOTAL_CHAPTERS - 1:
        rtable_key = "endgame"
    elif chapter_index is not None and chapter_index < 4:
        rtable_key = "cultivation"
    else:
        rtable_key = "basic"
    reward_table_id = _reward_table_id(rtable_key)

    parts = []
    for idx, q in enumerate(quests):
        col = idx % cfg.COLS_PER_ROW
        row = idx // cfg.COLS_PER_ROW
        x = cfg.START_X + col * cfg.COL_SPACING
        y = cfg.START_Y - row * cfg.ROW_SPACING
        parts.append(build_snbt_quest(q, key_to_id, x, y,
                                      reward_table_id, chapter_pool))

    icon = icon_override if icon_override is not None else ctx.get("icon", "")
    icon = resolve_icon(icon, set(item_ids)) if icon else ""
    icon_line = f'    icon: "{icon}"\n' if icon else ""

    content = f'''{{
    filename: "{filename}"
    id: "{chapter_id}"
    group: "{group_id}"
    order_index: 0
    title: "{title}"
{icon_line}    quests: [
{",".join(parts)}
    ]
}}'''
    return filename, content


# ==================== 章节组 / 全局配置 ====================
def generate_chapter_groups():
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


def generate_reward_tables(item_ids):
    os.makedirs(cfg.REWARDS_OUTPUT_DIR, exist_ok=True)
    pools_map = getattr(cfg, "REWARD_TABLE_POOLS", {})
    for key in cfg.REWARD_TABLES:
        prefixes = pools_map.get(key, [])
        pool = filter_by_prefix(item_ids, prefixes) if prefixes else item_ids[:]
        if not pool:
            log(f"  [提示] 奖励表 {key} 无对应物品池，将使用后备池")
            pool = item_ids[:]

        table_id, content = build_reward_table_snbt(key, pool)
        path = os.path.join(cfg.REWARDS_OUTPUT_DIR, f"{key}.snbt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        log(f"[输出] reward_tables/{key}.snbt -> id={table_id}（候选 {len(pool)} 个）")


# ==================== 整合包介绍章节 ====================
def generate_intro_chapter(group_id, item_ids):
    if not getattr(cfg, "ENABLE_PACK_INTRO_CHAPTER", False):
        return None

    title = getattr(cfg, "PACK_INTRO_CHAPTER_TITLE", "整合包介绍")
    icon = getattr(cfg, "PACK_INTRO_CHAPTER_ICON", "minecraft:book")

    log(f"\n[介绍章节] 生成「{title}」...")
    prompt = build_intro_prompt()
    batch = call_deepseek(prompt)
    if not batch:
        log(f"  [警告] 介绍章节 AI 无返回，跳过")
        return None

    allowed = ["checkmark"]
    cleaned = normalize_batch(batch, [], 0, [], [], allowed)
    if not cleaned:
        log(f"  [警告] 介绍章节无有效任务，跳过")
        return None

    n_cycles = break_cycles(cleaned)
    if n_cycles:
        log(f"  [修复] 断开 {n_cycles} 条循环依赖")

    filename, content = generate_chapter_snbt(
        None, cleaned, group_id, item_ids,
        icon_override=icon,
        title_override=title,
        filename_override="chapter_00",
    )
    path = os.path.join(cfg.CHAPTERS_OUTPUT_DIR, f"{filename}.snbt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"  -> 已输出: {path}（{len(cleaned)} 个任务）")
    return filename


# ==================== 章节生成 ====================
def generate_chapter(item_ids, structures, entity_ids, chapter_index):
    all_quests = []
    batches = (cfg.TASKS_PER_CHAPTER + cfg.BATCH_SIZE - 1) // cfg.BATCH_SIZE
    valid_structures = set(structures)
    valid_entities   = set(entity_ids)

    allowed_types = list(chapter_context(chapter_index)["task_types"])
    if not structures and "structure" in allowed_types:
        allowed_types.remove("structure")
    if not entity_ids and "kill" in allowed_types:
        allowed_types.remove("kill")
    if not allowed_types:
        allowed_types = ["item", "checkmark"]

    for b in range(batches):
        log(f"    批次 {b+1}/{batches} ...")
        prompt = build_prompt(item_ids, structures, entity_ids,
                              chapter_index, b, all_quests)
        batch = call_deepseek(prompt)
        if not batch:
            log(f"    [警告] 批次 {b+1} 无结果，跳过")
            continue
        cleaned = normalize_batch(
            batch, all_quests, b,
            valid_structures, valid_entities,
            allowed_types,
        )
        all_quests.extend(cleaned)
        log(f"    本批 {len(cleaned)} 个，累计 {len(all_quests)} 个")

    n_cycles = break_cycles(all_quests)
    if n_cycles:
        log(f"    [修复] 断开 {n_cycles} 条循环依赖")

    return all_quests


# ==================== 主流程 ====================
def main():
    global _modlist_map

    init_log(os.path.join(cfg.OUTPUT_DIR, "generate.log"))
    try:
        log("=" * 60)
        log(" ftb-bate · FTB Quests 任务书自动生成器")
        log(f" 语言: {'English' if is_en() else '中文'}")
        log(f" 输出目录: {cfg.OUTPUT_DIR}")
        log(f" MC百科: {'开启' if getattr(cfg, 'ENABLE_MCMOD_LOOKUP', False) else '关闭'}")
        log(f" 奖励: {'动态构建' if getattr(cfg, 'REWARD_AUTO_FROM_ITEMS', False) else '手写表'}")
        log(f" 介绍章节: {'开启' if getattr(cfg, 'ENABLE_PACK_INTRO_CHAPTER', False) else '关闭'}")
        log("=" * 60)

        if not cfg.API_KEY:
            log("[错误] 未检测到 DEEPSEEK_API_KEY 环境变量")
            sys.exit(1)
        if cfg.TOTAL_CHAPTERS <= 0:
            log("[错误] CHAPTER_GROUPS 中没有章节")
            sys.exit(1)

        _load_mcmod_cache()

        log("\n[步骤 1/6] 加载数据文件...")
        items      = load_items(cfg.ITEMS_FILE)
        item_ids   = list(items.keys())
        structures = load_structures(cfg.STRUCTURE_FILE)
        _modlist_map = load_modlist(cfg.MODLIST_FILE)
        entities   = load_entities(cfg.ENTITIES_FILE)
        entity_ids = list(entities.keys())

        if not item_ids:
            log("[警告] items.json 为空")

        log("\n[步骤 2/6] 准备输出目录...")
        os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
        os.makedirs(cfg.CHAPTERS_OUTPUT_DIR, exist_ok=True)
        os.makedirs(cfg.REWARDS_OUTPUT_DIR, exist_ok=True)

        log("\n[步骤 3/6] 生成章节组...")
        group_ids = generate_chapter_groups()
        intro_group_id = group_ids[0] if group_ids else ID_POOL.new()

        log("\n[步骤 4/6] 生成整合包介绍章节 + 奖励表...")
        generate_intro_chapter(intro_group_id, item_ids)
        generate_reward_tables(item_ids)

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
            filename, content = generate_chapter_snbt(
                i, quests, group_ids[ctx["group_index"]], item_ids
            )
            path = os.path.join(cfg.CHAPTERS_OUTPUT_DIR, f"{filename}.snbt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            log(f"  -> 已输出: {path}（{len(quests)} 个任务）")

        log("\n[步骤 6/6] 生成全局配置 data.snbt...")
        generate_data_snbt()

        log("\n" + "=" * 60)
        log(" 全部完成！")
        log(f" 输出目录: {cfg.OUTPUT_DIR}")
        log("=" * 60)
    finally:
        _save_mcmod_cache()
        close_log()


if __name__ == "__main__":
    main()