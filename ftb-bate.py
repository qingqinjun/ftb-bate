# -*- coding: utf-8 -*-
"""
========================================================
ftb-bate —— FTB Quests 任务书自动生成器（白板安全版）
========================================================
特性：
  - 所有 cfg 键通过 C() 兜底，缺键不崩
  - 任务要求 tasks: [] 正确包裹
  - 奖励内嵌，无 reward_tables
  - BOSS 击杀固定 1，普通怪 3~10，描述自动对齐
  - 连线简化：只保留有效主线，不做全量孤立补齐
  - ID 使用合法十进制 Long 字符串
  - AI 截断自动修复
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


# ==================== 配置兜底读取 ====================
def C(key, default=None):
    return getattr(cfg, key, default)


# ==================== 语言 ====================
def is_en():
    return str(C("QUEST_LANGUAGE", "zh")).lower() == "en"


# ==================== 日志 ====================
_LOG_FILE = None


def log(msg):
    print(msg)
    if _LOG_FILE:
        _LOG_FILE.write(msg + "\n")
        _LOG_FILE.flush()


def init_log(path):
    global _LOG_FILE
    if not path:
        return
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
_modlist_map = {}


def _load_mcmod_cache():
    global _mcmod_cache, _mcmod_cache_dirty
    path = C("MCMOD_CACHE_FILE", None)
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
    path = C("MCMOD_CACHE_FILE", None)
    if not path:
        return
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
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
    cn = C("MCMOD_KEYWORD_MAP", {}).get(prefix)
    if cn:
        return f"{cn} {rest}"
    return keyword


def lookup_mcmod(keyword, timeout=None):
    global _mcmod_cache_dirty
    if not keyword or not C("ENABLE_MCMOD_LOOKUP", False):
        return ""
    if keyword in _mcmod_cache:
        return _mcmod_cache[keyword]
    base = str(C("MCMOD_API_BASE", "") or "").rstrip("/")
    if not base:
        _mcmod_cache[keyword] = ""
        return ""
    if timeout is None:
        timeout = C("MCMOD_TIMEOUT", 10)
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
    if not C("ENABLE_MCMOD_LOOKUP", False):
        return ""
    max_n = int(C("MCMOD_MAX_LOOKUP", 0) or 0)
    if max_n <= 0:
        return ""
    priority = [
        "immortal_cultivation_mod", "chang_sheng_jue",
        "irons_spellbooks", "touhou_little_maid",
        "twilightforest", "legendary_monsters",
    ]
    seen_modids = []
    for p in priority:
        if p not in seen_modids:
            seen_modids.append(p)
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
    return str(random.randint(1, 999999999999999))


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
    retries = retries or C("FILE_RETRY", 5)
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
        data = json.load(f)
    arr = None
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        arr, _ = _find_data_array(data, ("structures", "structure", "data", "list"))
    if not arr:
        return []
    out = []
    if isinstance(arr, list):
        for e in arr:
            if isinstance(e, str):
                s = _clean_str(e)
                if s and ":" in s:
                    out.append(s)
            elif isinstance(e, dict):
                s = ""
                for k in ("id", "structure", "registry_name", "name", "key",
                          "resource_location"):
                    if k in e and isinstance(e[k], str):
                        s = _clean_str(e[k])
                        break
                if s and ":" in s:
                    out.append(s)
    elif isinstance(arr, dict):
        for k in arr.keys():
            s = _clean_str(k)
            if s and ":" in s:
                out.append(s)
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _parse_modlist(filepath):
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


# ==================== 图标校验 ====================
def resolve_icon(icon, valid_items):
    icon = _clean_str(icon)
    fallback = C("ICON_FALLBACK", "minecraft:book")
    if not icon:
        return ""
    if valid_items and icon not in valid_items:
        log(f"    [图标] {icon} 不在 items.json，回退为 {fallback}")
        return fallback
    return icon


# ==================== BOSS 识别 ====================
BOSS_KEYWORDS = [
    "boss", "naga", "lich", "hydra", "dragon", "wither",
    "queen", "king", "giant", "titan", "demon", "elder",
]


def _is_boss_entity(eid):
    low = (eid or "").lower()
    for kw in BOSS_KEYWORDS:
        if kw in low:
            return True
    return False


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
               entity_pool, allowed, batch_size, mcmod_section=""):
    prev_keys = [q["key"] for q in already]
    prev_desc = [f'{q["key"]}: {q["title"]}' for q in already[-8:]]
    if not already:
        chain_hint = (
            "这是本章第一批任务。第一个任务的 dependencies 必须为空数组 []，它作为本章根节点。"
            "**注意：从第二个任务开始，必须使用 dependencies 形成剧情链，不能全空。**"
            "例如：t2 依赖 t1，t3 依赖 t2。"
        )
    else:
        chain_hint = (
            "这是后续批次。**务必使用 dependencies 形成剧情链！**"
            "例如：如果已有任务是'击杀娜迦'，新任务是'击杀巫妖王'，那么'击杀巫妖王'的 dependencies 必须包含'击杀娜迦'的 key。"
            "请根据你对 Minecraft 模组的了解，设计出有先后顺序、有逻辑关联的任务树。"
        )
    type_lines = []
    if "item" in allowed:
        type_lines.append('item 类型：**必须严格从【可用物品 ID】列表里选**，禁止自己编造！')
    if "checkmark" in allowed:
        type_lines.append('checkmark 类型：仅需 title/desc')
    if "structure" in allowed:
        type_lines.append('structure 类型：必须从【可用结构 ID】里选')
    if "kill" in allowed:
        type_lines.append('kill 类型：必须从【可用实体 ID】里选')
    type_hint = "本章允许的任务类型：\n- " + "\n- ".join(type_lines)
    pack_intro = C("PACK_INTRO", "")
    sample_items = item_pool[:100]
    sample_entities = entity_pool[:50]
    return f"""你是 Minecraft FTB Quests 资深任务书设计师。{pack_intro}

为第 {chapter_index + 1} 章「{ctx["title"]}」生成第 {batch_index + 1} 批任务，共 {batch_size} 个。

【本章焦点】{ctx["focus"]}
【整体要求】{ctx["extra"]}
【串联要求】{chain_hint}

【已有任务 key 列表】（dependencies 只能从这里选，或选本批前面任务的 key）：
{json.dumps(prev_keys, ensure_ascii=False)}

【已有任务示例】（最近 8 个）：
{json.dumps(prev_desc, ensure_ascii=False)}

**【可用物品 ID】（必须逐字复制，严禁自己编造，找不到合适的就选相近的）**：
{json.dumps(sample_items, ensure_ascii=False)}

**【可用结构 ID】（必须逐字复制）**：
{json.dumps(struct_pool, ensure_ascii=False)}

**【可用实体 ID】（必须逐字复制，严禁自己编造）**：
{json.dumps(sample_entities, ensure_ascii=False)}
{mcmod_section}
【输出格式】严格输出 JSON 数组，不要 Markdown 代码块：
[
  {{"key": "t1", "type": "item", "id": "这里必须填上面列表里的真实ID", "count": 5, "title": "中文标题", "desc": "中文描述", "dependencies": []}},
  {{"key": "t2", "type": "kill", "id": "这里必须填上面列表里的真实实体ID", "count": 1, "title": "中文标题", "desc": "中文描述", "dependencies": ["t1"]}}
]

规则：
- 每批恰好 {batch_size} 个任务
- key 在本章内唯一，用 t1/t2/... 短名
- {type_hint}
- **dependencies 必须体现前置逻辑，不能全是空数组！**
- title ≤ 12 字，desc ≤ 30 字
- **kill 类型：BOSS 类实体（名字带 boss/naga/lich/hydra/dragon 等）count 必须为 1，普通怪物 count 在 3~10 之间，描述要与 count 一致。**
- **如果你填的 ID 不在提供的列表里，整个任务将作废！**
- **输出必须紧凑：不要换行缩进，不要多余空格，每个任务一行**
"""


def build_intro_prompt():
    intro_title = C("PACK_INTRO_CHAPTER_TITLE", "整合包介绍")
    pack_intro = C("PACK_INTRO", "")
    n = int(C("PACK_INTRO_TASK_COUNT", 3))
    focus = C("PACK_INTRO_CHAPTER_FOCUS", "")
    return f"""你是 Minecraft FTB Quests 资深任务书设计师。

当前整合包介绍：{pack_intro}

介绍章节焦点：{focus}

请为整合包介绍章节「{intro_title}」生成 {n} 个 checkmark 类型的任务，用于向玩家介绍整合包的核心玩法、主要模组与游玩建议。

【输出格式】严格输出 JSON 数组，不要 Markdown 代码块：
[
  {{"key": "i1", "type": "checkmark", "title": "欢迎来到整合包", "desc": "了解本整合包的核心玩法", "dependencies": []}},
  {{"key": "i2", "type": "checkmark", "title": "核心玩法", "desc": "了解主要模组", "dependencies": ["i1"]}}
]

规则：
- 恰好 {n} 个任务，全部为 checkmark 类型
- key 用 i1/i2/... 短名，本章内唯一
- 第一个任务 dependencies 为空数组 []
- 后续任务建议串联，形成介绍流程
- title ≤ 12 字，desc ≤ 30 字
- 只输出 JSON 数组
- **输出必须紧凑：不要换行缩进，不要多余空格，每个任务一行**
"""


# ==================== 交互询问 ====================
def _ask_int(prompt, default, min_val=1, max_val=999999):
    while True:
        try:
            raw = input(f"{prompt}（默认 {default}，直接回车使用默认）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if not raw:
            return default
        try:
            v = int(raw)
        except ValueError:
            print(f"  [输入无效] 请输入 {min_val}~{max_val} 的整数")
            continue
        if v < min_val or v > max_val:
            print(f"  [输入无效] 请输入 {min_val}~{max_val} 的整数")
            continue
        return v


def ask_generation_options():
    print("\n===== 生成规模设置 =====")
    print("说明：每章总任务数 ≈ 每章批次数 × 每批任务数")
    batches = _ask_int("每章生成几个批次", int(C("DEFAULT_BATCHES_PER_CHAPTER", 3)))
    batch_size = _ask_int("每批生成几个任务", int(C("BATCH_SIZE", 6)))
    print("说明：max_tokens 是 AI 单次输出上限，太小会截断 JSON。")
    max_tokens = _ask_int("AI 单次输出 max_tokens", int(C("MAX_TOKENS", 8000)))
    print(f"[设置] 每章 {batches} 批 × 每批 {batch_size} 个 ≈ {batches * batch_size} 个任务/章")
    print(f"[设置] max_tokens = {max_tokens}\n")
    return batches, batch_size, max_tokens


# ==================== JSON 截断修复 ====================
def _try_repair_json(text):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass
    last_brace = text.rfind("}")
    if last_brace == -1:
        return None
    candidate = text[:last_brace + 1]
    candidate = candidate.rstrip().rstrip(",")
    if not candidate.rstrip().endswith("]"):
        candidate = candidate + "\n]"
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass
    return None


# ==================== API 调用 ====================
def call_deepseek(prompt, max_tokens=8000, max_retries=3):
    base_url = str(C("BASE_URL", "https://api.deepseek.com") or "").rstrip("/")
    url = f"{base_url}/chat/completions"
    api_key = C("API_KEY", "")
    model = C("MODEL", "deepseek-chat")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You output only a JSON array, no explanation, no Markdown."
                                          if is_en() else
                                          "你只输出 JSON 数组，不输出任何解释，不使用 Markdown 代码块。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": int(max_tokens),
    }
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            parsed = _try_repair_json(text)
            if parsed is not None and parsed:
                if attempt > 0 or not text.rstrip().endswith("]"):
                    log(f"  [修复] 第 {attempt+1} 次返回被截断，已修复为 {len(parsed)} 个任务")
                return parsed
            log(f"  [重试 {attempt+1}] AI 返回空列表或无法修复")
        except requests.exceptions.RequestException as e:
            log(f"  [重试 {attempt+1}] 网络请求失败: {e}")
        except (KeyError, IndexError) as e:
            log(f"  [重试 {attempt+1}] 响应结构异常: {e}")
        except Exception as e:
            log(f"  [重试 {attempt+1}] API 调用失败: {e}")
    return []


# ==================== 结果清洗 ====================
_LEGAL_KEY_RE = re.compile(r"^[a-zA-Z]+\d+(_\d+)?$")


def _align_kill_desc(desc, count):
    if not desc:
        return desc
    desc = re.sub(r"\d+\s*只", f"{count}只", desc)
    desc = re.sub(r"\d+\s*个", f"{count}个", desc)
    desc = re.sub(r"\d+\s*条", f"{count}条", desc)
    desc = re.sub(r"\d+\s*头", f"{count}头", desc)
    return desc


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
        deps = [d for d in deps if _LEGAL_KEY_RE.match(d)]
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
            if _is_boss_entity(raw_id):
                count = 1
            else:
                count = random.randint(3, 10)
        else:
            if raw_type in ("structure", "kill") and raw_id:
                log(f"    [警告] {raw_type} ID 无效或未被允许: {raw_id}，降级为 checkmark")
            qtype, qid, count = "checkmark", "", None
        if count is None:
            count = 1
        desc = str(q.get("desc", ""))
        if qtype == "kill":
            desc = _align_kill_desc(desc, count)
        cleaned.append({
            "key": key,
            "type": qtype,
            "id": qid,
            "count": count,
            "title": str(q.get("title", "未命名任务")),
            "desc": desc,
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


# ==================== 简化的智能连线兜底 ====================
def fix_chain_dependencies(quests):
    """只给没有依赖的任务补上前一个任务，不强行串联所有孤立节点。"""
    if not quests:
        return
    for i in range(1, len(quests)):
        q = quests[i]
        if not q["dependencies"]:
            q["dependencies"].append(quests[i - 1]["key"])
            log(f"    [连线兜底] {q['key']} 无前置，连到前一任务 {quests[i - 1]['key']}")


# ==================== 奖励与难度挂钩（内嵌） ====================
def _is_reward_blacklisted(iid):
    blacklist = C("REWARD_ITEM_BLACKLIST", [])
    for p in blacklist:
        if iid == p or ((":" not in p) and iid.startswith(p + ":")):
            return True
    keywords = C("REWARD_ITEM_BLACKLIST_KEYWORDS", [])
    low = iid.lower()
    for kw in keywords:
        if kw and kw in low:
            return True
    return False


def calc_task_difficulty(quest, all_quests):
    if not C("ENABLE_DIFFICULTY_REWARDS", True):
        return 1
    type_base_map = C("TASK_TYPE_DIFFICULTY", {"checkmark": 1, "item": 2, "kill": 3, "structure": 4})
    type_base = type_base_map.get(quest["type"], 2)
    count_factor = C("COUNT_DIFFICULTY_FACTOR", 0.3)
    count_val = quest.get("count") or 1
    count_score = count_val * count_factor
    depth_weight = C("DEP_DEPTH_WEIGHT", 0.5)
    depth = _calc_dep_depth(quest, all_quests)
    depth_score = depth * depth_weight
    rare_mods = C("RARE_MOD_PREFIXES", [])
    mod_bonus = 0
    qid = quest.get("id", "")
    if ":" in qid:
        modid = qid.split(":", 1)[0]
        if modid in rare_mods:
            mod_bonus = 1
    raw = type_base + count_score + depth_score + mod_bonus
    if raw <= 1.5: return 1
    elif raw <= 2.5: return 2
    elif raw <= 4.0: return 3
    elif raw <= 6.0: return 4
    else: return 5


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
    tiers = C("DIFFICULTY_TIERS", {})
    tier_name = difficulty_to_tier_name(difficulty)
    return tiers.get(tier_name, {"item_count_range": (1, 2)})


def _select_reward_items_for_tier(tier, item_pool, fallback_pool):
    lo, hi = tier.get("item_count_range", (1, 2))
    n = random.randint(int(lo), max(int(lo), int(hi)))
    pool = [i for i in (item_pool or []) if not _is_reward_blacklisted(i)]
    fb = [i for i in (fallback_pool or []) if not _is_reward_blacklisted(i)]
    if not pool:
        pool = fb
    if not pool:
        return "minecraft:experience_bottle", 1
    return random.choice(pool), n


def attach_difficulty_rewards(quests, item_pool):
    fallback_pool = C("REWARD_FALLBACK_POOL", ["minecraft:emerald", "minecraft:diamond"])
    log(f"[内嵌奖励] 开始为 {len(quests)} 个任务计算难度并分配奖励...")
    for q in quests:
        diff = calc_task_difficulty(q, quests)
        tier = _tier_for_difficulty(diff)
        item_id, count = _select_reward_items_for_tier(tier, item_pool, fallback_pool)
        q["reward_item"] = item_id
        q["reward_count"] = count
    log(f"[内嵌奖励] 分配完成。")


# ==================== 数据包输出辅助 ====================
def _calc_layout(quests, cols_per_row, col_spacing, row_spacing, start_x, start_y):
    for i, q in enumerate(quests):
        row = i // cols_per_row
        col = i % cols_per_row
        q["x"] = start_x + col * col_spacing
        q["y"] = start_y - row * row_spacing
    return quests


def _quest_to_snbt(q, key_to_uuid):
    quest_id = q.get("_uuid") or ID_POOL.new()
    q["_uuid"] = quest_id
    snbt = f'{{\n'
    snbt += f'    id: "{quest_id}"\n'
    snbt += f'    x: {float(q.get("x", 0)):.1f}d\n'
    snbt += f'    y: {float(q.get("y", 0)):.1f}d\n'
    snbt += f'    title: "{q["title"].replace(chr(34), chr(39))}"\n'
    snbt += f'    description: ["{q["desc"].replace(chr(34), chr(39))}"]\n'

    task_id = gen_hex_id()
    if q["type"] == "item":
        snbt += '    tasks: [{\n'
        snbt += '        consume_items: true\n'
        snbt += f'        count: {int(q.get("count", 1))}L\n'
        snbt += f'        id: "{task_id}"\n'
        snbt += f'        item: "{q["id"]}"\n'
        snbt += '        type: "item"\n'
        snbt += '    }]\n'
    elif q["type"] == "kill":
        snbt += '    tasks: [{\n'
        snbt += f'        count: {int(q.get("count", 1))}L\n'
        snbt += f'        entity: "{q["id"]}"\n'
        snbt += f'        id: "{task_id}"\n'
        snbt += '        type: "kill"\n'
        snbt += '    }]\n'
    elif q["type"] == "structure":
        snbt += '    tasks: [{\n'
        snbt += f'        id: "{task_id}"\n'
        snbt += f'        structure: "{q["id"]}"\n'
        snbt += '        type: "structure"\n'
        snbt += '    }]\n'
    elif q["type"] == "checkmark":
        snbt += '    tasks: [{\n'
        snbt += f'        id: "{task_id}"\n'
        snbt += '        type: "checkmark"\n'
        snbt += '    }]\n'

    if q.get("dependencies"):
        deps_str = ", ".join(
            f'"{key_to_uuid[d]}"' for d in q["dependencies"] if d in key_to_uuid
        )
        if deps_str:
            snbt += f'    dependencies: [{deps_str}]\n'

    if q.get("reward_item"):
        reward_id = gen_hex_id()
        snbt += '    rewards: [{\n'
        snbt += '        auto: "enabled"\n'
        snbt += f'        id: "{reward_id}"\n'
        snbt += f'        item: "{q["reward_item"]}"\n'
        snbt += f'        count: {int(q.get("reward_count", 1))}\n'
        snbt += '        team_reward: true\n'
        snbt += '        type: "item"\n'
        snbt += '    }]\n'
    snbt += f'}}'
    return snbt


def _chapter_to_snbt(ch_id, ch_title, ch_icon, quests):
    chapter_keys = {q["key"] for q in quests}
    for q in quests:
        q["dependencies"] = [d for d in q.get("dependencies", []) if d in chapter_keys]

    key_to_uuid = {}
    for q in quests:
        if "_uuid" not in q:
            q["_uuid"] = ID_POOL.new()
        key_to_uuid[q["key"]] = q["_uuid"]

    snbt = f'{{\n'
    snbt += f'    id: "{ch_id}"\n'
    snbt += f'    title: "{ch_title}"\n'
    if ch_icon:
        snbt += f'    icon: "{ch_icon}"\n'
    snbt += f'    default_quest_shape: "circle"\n'

    snbt += '    quest_links: [\n'
    links = []
    seen_links = set()
    for q in quests:
        for dep in q["dependencies"]:
            if dep in key_to_uuid:
                pair = (key_to_uuid[dep], q["_uuid"])
                if pair in seen_links:
                    continue
                seen_links.add(pair)
                link_id = gen_hex_id()
                link_snbt = '        {\n'
                link_snbt += f'            id: "{link_id}"\n'
                link_snbt += f'            linked_quest: "{key_to_uuid[dep]}"\n'
                link_snbt += f'            quest: "{q["_uuid"]}"\n'
                link_snbt += '        }'
                links.append(link_snbt)
    if links:
        snbt += ",\n".join(links)
        snbt += "\n"
    snbt += '    ]\n'

    snbt += f'    quests: [\n'
    quest_strs = []
    for q in quests:
        q_str = _quest_to_snbt(q, key_to_uuid)
        q_str = "\n".join("        " + line for line in q_str.splitlines())
        quest_strs.append(q_str)
    snbt += ",\n".join(quest_strs)
    snbt += f'\n    ]\n'
    snbt += f'}}'
    return snbt


# ==================== 主流程 ====================
def main():
    batches_per_chapter, batch_size, max_tokens = ask_generation_options()
    random.seed(C("RANDOM_SEED", None))
    if C("RANDOM_SEED", None) is not None:
        log(f"[随机] 已设置随机种子: {C('RANDOM_SEED')}")
    init_log(C("LOG_FILE", "logs/ftb_bate.log"))
    log(f"===== FTB Quests 任务书生成器启动 =====")
    log(f"[时间] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"[规模] 每章 {batches_per_chapter} 批 × 每批 {batch_size} 个")
    log(f"[tokens] max_tokens = {max_tokens}")

    items_path = C("ITEMS_FILE", "dumpids/items.json")
    structs_path = C("STRUCTURES_FILE", "dumpids/structures.json")
    modlist_path = C("MODLIST_FILE", "dumpids/modlist.json")
    entities_path = C("ENTITIES_FILE", "dumpids/entities.json")

    _load_mcmod_cache()
    global _modlist_map
    _modlist_map = load_modlist(modlist_path)
    item_names = load_items(items_path)
    item_ids = list(item_names.keys())
    structures = load_structures(structs_path)
    entity_ids = list(load_entities(entities_path).keys())
    log(f"[汇总] 物品 {len(item_ids)} | 结构 {len(structures)} | 实体 {len(entity_ids)} | 模组 {len(_modlist_map)}")

    output_dir = C("OUTPUT_DIR", "output")
    chapters_dir = os.path.join(output_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    all_quests = []
    groups_dict = {}

    # ---- 整合包介绍章节 ----
    intro_ch_id = None
    if C("GENERATE_PACK_INTRO", True):
        log("\n===== 生成整合包介绍章节 =====")
        intro_prompt = build_intro_prompt()
        batch = []
        for attempt in range(2):
            batch = call_deepseek(intro_prompt, max_tokens=max_tokens)
            if batch:
                break
            log("  [重试] 整合包介绍章节生成失败，重试...")
        if batch:
            intro_quests = normalize_batch(batch, [], 0, valid_structures=set(structures), valid_entities=set(entity_ids), allowed_types=["checkmark"])
            for i, q in enumerate(intro_quests):
                q["dependencies"] = [] if i == 0 else [intro_quests[i - 1]["key"]]
            _calc_layout(intro_quests, C("COLS_PER_ROW", 5), C("COL_SPACING", 2.0), C("ROW_SPACING", 2.0), C("START_X", 0.0), C("START_Y", 0.0))
            attach_difficulty_rewards(intro_quests, item_ids)
            intro_ch_id = ID_POOL.new()
            intro_icon = resolve_icon(C("PACK_INTRO_CHAPTER_ICON", "minecraft:book"), set(item_ids))
            intro_ch_snbt = _chapter_to_snbt(intro_ch_id, C("PACK_INTRO_CHAPTER_TITLE", "整合包介绍"), intro_icon, intro_quests)
            with open(os.path.join(chapters_dir, "intro.snbt"), "w", encoding="utf-8") as f:
                f.write(intro_ch_snbt)
            all_quests.extend(intro_quests)
            groups_dict.setdefault(0, []).append(intro_ch_id)
            log(f"  [完成] 整合包介绍章节: {len(intro_quests)} 个任务")

    # ---- 逐章生成 ----
    flat = cfg.flatten_chapters()
    log(f"\n===== 共 {len(flat)} 个章节，开始生成 =====")
    for ci, ch in enumerate(flat):
        log(f"\n----- 第 {ci+1}/{len(flat)} 章: {ch['title']} -----")
        ctx = chapter_context(ci)
        chapter_quests = []
        for bi in range(batches_per_chapter):
            log(f"  [批次 {bi+1}/{batches_per_chapter}]")
            prompt = _prompt_zh(
                ctx, ci, bi, chapter_quests,
                item_ids, structures, entity_ids,
                ctx["task_types"],
                batch_size,
                _build_mcmod_section(item_ids, entity_ids),
            )
            batch = call_deepseek(prompt, max_tokens=max_tokens)
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
            fix_chain_dependencies(chapter_quests)
            n_fixed = break_cycles(chapter_quests)
            if n_fixed:
                log(f"    [循环修复] 断开了 {n_fixed} 个循环依赖")
            attach_difficulty_rewards(chapter_quests, item_ids)
            _calc_layout(chapter_quests, C("COLS_PER_ROW", 6), C("COL_SPACING", 2.0), C("ROW_SPACING", 1.5), C("START_X", 0.0), C("START_Y", 0.0))
            ch_id = ID_POOL.new()
            ch_icon = resolve_icon(ctx.get("icon", ""), set(item_ids))
            ch_snbt = _chapter_to_snbt(ch_id, ch['title'], ch_icon, chapter_quests)
            fname = f"chapter_{ci+1:02d}.snbt"
            with open(os.path.join(chapters_dir, fname), "w", encoding="utf-8") as f:
                f.write(ch_snbt)
            groups_dict.setdefault(ctx["group_index"] + 1, []).append(ch_id)
        all_quests.extend(chapter_quests)

    # ---- 全局循环检测 ----
    log(f"\n===== 全局循环检测 =====")
    total_fixed = break_cycles(all_quests)
    if total_fixed:
        log(f"  [全局循环修复] 断开了 {total_fixed} 个循环依赖")
    else:
        log(f"  [全局循环检测] 无循环依赖 ✓")

    # ---- 输出 chapter_groups.snbt ----
    group_snbt = "{\n    chapter_groups: [\n"
    sorted_groups = sorted(groups_dict.keys())
    group_blocks = []
    for g_idx in sorted_groups:
        if g_idx == 0:
            g_title = C("PACK_INTRO_GROUP_TITLE", "整合包介绍")
        else:
            g_title = f"第 {g_idx} 阶段"
        block = "        {\n"
        block += f'            id: "{ID_POOL.new()}"\n'
        block += f'            title: "{g_title}"\n'
        block += '            chapters: [\n'
        for ch_id in groups_dict[g_idx]:
            block += f'                "{ch_id}"\n'
        block += '            ]\n'
        block += '        }'
        group_blocks.append(block)
    group_snbt += ",\n".join(group_blocks)
    group_snbt += "\n    ]\n}\n"
    with open(os.path.join(output_dir, "chapter_groups.snbt"), "w", encoding="utf-8") as f:
        f.write(group_snbt)

    # ---- 输出 data.snbt ----
    data_snbt = '{\n    version: 1\n    title: "整合包任务"\n    icon: "minecraft:book"\n    default_quest_shape: "circle"\n    default_hide_dependency_lines: false\n}\n'
    with open(os.path.join(output_dir, "data.snbt"), "w", encoding="utf-8") as f:
        f.write(data_snbt)

    _save_mcmod_cache()
    log(f"\n===== 完成 =====")
    log(f"[统计] 总任务 {len(all_quests)} 个")
    log(f"[输出] 请去 {output_dir} 查看，所有奖励都在任务文件里，quest_links 会画出连线。")
    close_log()


if __name__ == "__main__":
    main()