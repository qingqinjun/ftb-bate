# -*- coding: utf-8 -*-
"""
========================================================
ftb-bate —— FTB Quests 任务书自动生成器（白板安全版 · SNBT 输出）
========================================================
特性：
  - 所有 cfg 键通过 C() 兜底，缺键不崩
  - 输出 FTB Quests 1.20.1 原生 .snbt 格式
  - 先生成 data.snbt / chapter_groups.snbt，再逐章生成并写入 group 字段
  - 任务要求 tasks: [] 正确包裹
  - 奖励内嵌，无 reward_tables
  - BOSS 击杀固定 1，普通怪 3~10，描述自动对齐
  - ID 使用合法十进制 Long 字符串
  - AI 截断自动修复

【依赖策略 —— 精简版】
  - 【精简1】不再强制全链式，改为按阈值精简依赖
  - 【精简2】依赖数 > DEPENDENCY_KEEP_THRESHOLD 的任务清空依赖
  - 【精简3】DEPENDENCY_FORCE_KEEP_KEYS 中的关键任务保留依赖
  - 【精简4】任何任务最多保留 1 个前置，避免分支合并
  - 【精简5】break_cycles 先于 slim_dependencies 执行

【防 FTB isExcludedByOtherQuestline 递归崩溃 —— 强化版】
  - 【修复1】只保留本章内依赖，跨章节依赖直接丢弃
  - 【修复2】介绍章同样只保留本章内依赖
  - 【修复3】progression_mode 默认 linear
  - 【修复4】group 为空时不写该字段
  - 【修复5】章节组标题硬校验：空/重复直接报错
  - 【修复6】normalize_batch 依赖过滤收紧
  - 【修复7】坐标列数兜底 max(1, cols)
  - 【修复8】generate_chapter 开头显式清空 quests
  - 【修复9】生成后跨章节依赖检查
  - 【修复10】_build_chapter_dict 内 FTB ID 层面 DFS 环检测 + 断环
  - 【修复11】break_cycles 先于依赖精简执行
  - 【修复12】生成后本章内环检测
  - 【修复13】生成后依赖繁简检查
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
            "**后续任务可以使用 dependencies 形成少量关键解锁链，但不要把所有任务串成一条长链。**"
            "例如：允许 t1(击杀娜迦) <- t2(击杀巫妖王) 这样的 Boss 解锁，但不要让每个任务都依赖前一个。"
        )
    else:
        chain_hint = (
            "这是后续批次。**只对少量关键任务使用 dependencies 形成解锁链，不要把所有任务串起来。**"
            "例如：如果已有任务是'击杀娜迦'，可以设计'击杀巫妖王'依赖它；但普通收集/探索任务应保持独立（dependencies 为空）。"
            "请控制依赖数量，让大部分任务可以独立完成。"
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
【依赖策略】{chain_hint}

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
- **大部分任务的 dependencies 应为空数组 []，只对少量关键任务设置前置依赖**
- **每个任务最多只允许有 1 个前置依赖（dependencies 数组长度 ≤ 1），不要设计分支合并结构！**
- **dependencies 只能引用本章内的 key，禁止引用其他章节的 key！**
- **禁止形成循环依赖（A 依赖 B，B 又依赖 A）！**
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
  {{"key": "i2", "type": "checkmark", "title": "核心玩法", "desc": "了解主要模组", "dependencies": []}}
]

规则：
- 恰好 {n} 个任务，全部为 checkmark 类型
- key 用 i1/i2/... 短名，本章内唯一
- **大部分任务 dependencies 为空数组 []，介绍章不需要全部串联**
- **每个任务最多 1 个前置**
- **禁止形成循环依赖**
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
        # 【修复6】依赖过滤收紧：只保留本章已存在或本批前面的 key，最多 1 个，不自环
        valid_for_this = existing_keys | {c["key"] for c in cleaned}
        deps = [d for d in deps if d in valid_for_this and d != key]
        if len(deps) > 1:
            deps = deps[:1]

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
        if len(q["dependencies"]) > 1:
            q["dependencies"] = q["dependencies"][:1]
    if cleaned and not already:
        cleaned[0]["dependencies"] = []
    return cleaned


# ==================== 依赖循环检测 ====================
def break_cycles(quests):
    """在 quests 的 key 层面断开环。

    【修复11】必须在 slim_dependencies 之前调用。
    """
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
                if dep in graph:
                    dfs(dep)
        color[node] = 2
    for k in list(graph):
        if color[k] == 0:
            dfs(k)
    if removed[0]:
        for q in quests:
            q["dependencies"] = graph[q["key"]]
    return removed[0]


# ==================== 依赖精简（替代原 fix_chain_dependencies） ====================
def slim_dependencies(quests, keep_threshold=None, force_keep_keys=None):
    """按规则精简依赖，而不是强制全链式。

    规则：
      1. 依赖数量 > keep_threshold 的任务，清空其依赖（视为独立任务）
      2. 依赖数量 <= keep_threshold 的任务，保留其依赖（视为关键剧情锁）
      3. force_keep_keys 中的任务，无论依赖多少都保留（用于 Boss 解锁链等）
      4. 最终统一做一次环检测断环（调用方已提前 break_cycles）

    keep_threshold 默认取 config 的 DEPENDENCY_KEEP_THRESHOLD，缺省 1。
    """
    if not quests:
        return 0

    if keep_threshold is None:
        keep_threshold = int(C("DEPENDENCY_KEEP_THRESHOLD", 1))
    force_keep_keys = set(force_keep_keys or C("DEPENDENCY_FORCE_KEEP_KEYS", []))

    removed = 0
    for q in quests:
        deps = q.get("dependencies", [])
        if not deps:
            continue
        if q["key"] in force_keep_keys:
            # 关键任务：保留依赖，但最多保留 1 个，避免分支合并
            if len(deps) > 1:
                q["dependencies"] = deps[:1]
                removed += len(deps) - 1
            continue
        if len(deps) > keep_threshold:
            removed += len(deps)
            q["dependencies"] = []
        elif len(deps) > 1:
            # 未超阈值但有多依赖，也只保留第一个，避免分支合并崩溃
            removed += len(deps) - 1
            q["dependencies"] = deps[:1]

    log(f"    [依赖精简] 共移除 {removed} 条冗余依赖，"
        f"阈值={keep_threshold}，强制保留 {len(force_keep_keys)} 个关键任务")
    return removed


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
        item_id, cnt = _select_reward_items_for_tier(tier, item_pool, fallback_pool)
        q["reward_item"] = item_id
        q["reward_count"] = cnt
        q["difficulty"] = diff
    log(f"[内嵌奖励] 完成，已为 {len(quests)} 个任务分配奖励")
    return quests


# ==================== 任务池筛选 ====================
def _filter_pool_by_prefix(pool, prefixes):
    if not prefixes:
        return list(pool)
    out = []
    for iid in pool:
        if ":" not in iid:
            continue
        modid = iid.split(":", 1)[0]
        if modid in prefixes:
            out.append(iid)
    return out


def _build_pools_for_chapter(ctx, items, entities, structures):
    item_pool = _filter_pool_by_prefix(list(items.keys()), ctx["item_prefixes"])
    if not item_pool:
        item_pool = list(items.keys())
    entity_pool = _filter_pool_by_prefix(list(entities.keys()), ctx["entity_prefixes"])
    if not entity_pool:
        entity_pool = list(entities.keys())
    struct_pool = list(structures) if ctx["use_structures"] else []
    return item_pool, entity_pool, struct_pool


# ==================== 章节生成 ====================
def generate_chapter(chapter_index, items, entities, structures,
                     batches_per_chapter, batch_size, max_tokens):
    ctx = chapter_context(chapter_index)
    log(f"\n===== 第 {chapter_index + 1} 章「{ctx['title']}」=====")
    log(f"  焦点: {ctx['focus']}")

    is_intro = (ctx["group_index"] == 0 and
                ctx["title"] == C("PACK_INTRO_CHAPTER_TITLE", "整合包介绍"))
    if is_intro:
        return _generate_intro_chapter(max_tokens)

    item_pool, entity_pool, struct_pool = _build_pools_for_chapter(
        ctx, items, entities, structures
    )
    log(f"  物品池: {len(item_pool)} 个，实体池: {len(entity_pool)} 个，结构池: {len(struct_pool)} 个")

    allowed = list(ctx["task_types"])
    quests = []   # 【修复8】显式清空，防止跨章节残留
    for b in range(batches_per_chapter):
        log(f"  -- 第 {b + 1}/{batches_per_chapter} 批 --")
        mcmod_section = _build_mcmod_section(item_pool, entity_pool)
        prompt = _prompt_zh(
            ctx, chapter_index, b, quests,
            item_pool, struct_pool, entity_pool,
            allowed, batch_size, mcmod_section,
        )
        raw = call_deepseek(prompt, max_tokens=max_tokens)
        if not raw:
            log(f"  [批次 {b + 1}] 未获得有效任务，跳过")
            continue
        cleaned = normalize_batch(
            raw, quests, b,
            valid_structures=struct_pool,
            valid_entities=entity_pool,
            allowed_types=allowed,
        )
        log(f"  [批次 {b + 1}] 获得 {len(cleaned)} 个任务")
        quests.extend(cleaned)

    # 【修复11】先 break_cycles 处理 AI 原始环，再依赖精简
    break_cycles(quests)
    slim_dependencies(quests)
    attach_difficulty_rewards(quests, item_pool)
    return quests


def _generate_intro_chapter(max_tokens):
    log("  [介绍章节] 生成 checkmark 任务...")
    prompt = build_intro_prompt()
    raw = call_deepseek(prompt, max_tokens=max_tokens)
    if not raw:
        log("  [介绍章节] 未获得任务，使用默认三条")
        raw = [
            {"key": "i1", "type": "checkmark", "title": "欢迎来到整合包",
             "desc": "了解本整合包的核心玩法", "dependencies": []},
            {"key": "i2", "type": "checkmark", "title": "核心玩法",
             "desc": "了解修仙与长生主线", "dependencies": []},
            {"key": "i3", "type": "checkmark", "title": "游玩建议",
             "desc": "按推荐顺序体验整合包", "dependencies": []},
        ]
    cleaned = normalize_batch(
        raw, [], 0, valid_structures=[], valid_entities=[],
        allowed_types=["checkmark"],
    )
    # 【修复2】介绍章同样走精简逻辑，避免全部串联
    slim_dependencies(cleaned, keep_threshold=1)
    for q in cleaned:
        q["difficulty"] = 1
        q["reward_item"] = "minecraft:book"
        q["reward_count"] = 1
    return cleaned


# ==================== SNBT 序列化 ====================
class LongInt(int):
    """标记为 Long 的整数，序列化时加 L 后缀。"""
    pass


def _snbt_escape(s):
    s = str(s)
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _snbt_str(s):
    return f'"{_snbt_escape(s)}"'


def _snbt_value(v, indent=1):
    if isinstance(v, bool):
        return "1b" if v else "0b"
    if isinstance(v, LongInt):
        return f"{int(v)}L"
    if isinstance(v, int):
        return f"{v}"
    if isinstance(v, float):
        return f"{v}d"
    if isinstance(v, str):
        return _snbt_str(v)
    if isinstance(v, list):
        if not v:
            return "[]"
        pad = "\t" * indent
        inner = ",\n".join(pad + "\t" + _snbt_value(x, indent + 1) for x in v)
        return "[\n" + inner + "\n" + pad + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        pad = "\t" * indent
        lines = []
        for k, val in v.items():
            lines.append(f"{pad}\t{k}: {_snbt_value(val, indent + 1)}")
        return "{\n" + "\n".join(lines) + "\n" + pad + "}"
    return _snbt_str(v)


# ==================== FTB Quests 章节转换 ====================
def _to_ftb_quest_snbt(q, chapter_icon):
    qid = ID_POOL.new()
    tasks = []
    if q["type"] == "item" and q["id"]:
        tasks.append({
            "consume_items": True,
            "count": LongInt(int(q.get("count", 1))),
            "id": ID_POOL.new(),
            "item": q["id"],
            "type": "item",
        })
    elif q["type"] == "kill" and q["id"]:
        tasks.append({
            "count": LongInt(int(q.get("count", 1))),
            "id": ID_POOL.new(),
            "entity": q["id"],
            "type": "kill",
        })
    elif q["type"] == "structure" and q["id"]:
        tasks.append({
            "id": ID_POOL.new(),
            "structure": q["id"],
            "type": "structure",
        })
    else:
        tasks.append({
            "id": ID_POOL.new(),
            "type": "checkmark",
        })

    rewards = []
    if q.get("reward_item"):
        rewards.append({
            "auto": "enabled",
            "id": ID_POOL.new(),
            "item": q["reward_item"],
            "count": int(q.get("reward_count", 1)),
            "team_reward": True,
            "type": "item",
        })

    d = {
        "id": qid,
        "x": 0.0,
        "y": 0.0,
        "title": q["title"],
    }
    if q.get("desc"):
        d["description"] = [q["desc"]]
    d["icon"] = chapter_icon or C("ICON_FALLBACK", "minecraft:book")
    d["tasks"] = tasks
    if rewards:
        d["rewards"] = rewards
    d["_key"] = q["key"]
    return d


def _build_chapter_dict(chapter_index, quests, chapter_icon, items, group_id):
    icon = resolve_icon(chapter_icon, set(items.keys())) if items else (chapter_icon or "")
    chapter_id = ID_POOL.new()

    ftb_quests = []
    key_to_ftb_id = {}
    for q in quests:
        fq = _to_ftb_quest_snbt(q, icon)
        key_to_ftb_id[q["key"]] = fq["id"]
        ftb_quests.append(fq)

    id_to_quest_key = {fq["id"]: q["key"] for q, fq in zip(quests, ftb_quests)}

    # 【修复1】只保留本章内依赖，彻底删掉跨章节依赖。
    cross_chapter_dropped = 0
    for q, fq in zip(quests, ftb_quests):
        first_dep_key = None
        for d in q.get("dependencies", []):
            if d in key_to_ftb_id and key_to_ftb_id[d] != fq["id"]:
                first_dep_key = d
                break
            elif d not in key_to_ftb_id:
                cross_chapter_dropped += 1
                log(f"    [跨章节依赖] 丢弃: {q['key']} -> {d}（不在本章）")
        if first_dep_key is not None:
            fq["_dep_key"] = first_dep_key
        else:
            fq.pop("_dep_key", None)
            fq.pop("dependencies", None)

    if cross_chapter_dropped:
        log(f"    [跨章节依赖] 本章共丢弃 {cross_chapter_dropped} 条")

    # 【修复10】FTB ID 层面 DFS 环检测 + 断环
    graph = {}
    for fq in ftb_quests:
        dep_key = fq.get("_dep_key")
        if dep_key is not None:
            graph[fq["id"]] = [key_to_ftb_id[dep_key]]
        else:
            graph[fq["id"]] = []

    color = {nid: 0 for nid in graph}
    broken = 0

    def dfs_cycle(node):
        nonlocal broken
        color[node] = 1
        for dep in list(graph[node]):
            c = color.get(dep, 0)
            if c == 1:
                graph[node].remove(dep)
                broken += 1
                dep_q = id_to_quest_key.get(dep, dep)
                node_q = id_to_quest_key.get(node, node)
                log(f"    [环检测] 断开依赖: {node_q}({node}) -> {dep_q}({dep})")
            elif c == 0 and dep in graph:
                dfs_cycle(dep)
        color[node] = 2

    for nid in list(graph):
        if color[nid] == 0:
            dfs_cycle(nid)

    if broken:
        log(f"    [环检测] 本章共断开 {broken} 条循环依赖")

    for fq in ftb_quests:
        fq.pop("_dep_key", None)
        if graph[fq["id"]]:
            fq["dependencies"] = graph[fq["id"]]
        else:
            fq.pop("dependencies", None)

    # 【修复7】坐标列数兜底
    cols = max(1, int(C("COLS_PER_ROW", 6)))
    col_sp = float(C("COL_SPACING", 2.0))
    row_sp = float(C("ROW_SPACING", 1.5))
    sx = float(C("START_X", 0.0))
    sy = float(C("START_Y", 0.0))
    for i, fq in enumerate(ftb_quests):
        r, c = divmod(i, cols)
        fq["x"] = sx + c * col_sp
        fq["y"] = sy + r * row_sp
        fq.pop("_key", None)

    ctx = chapter_context(chapter_index)
    chapter_dict = {
        "id": chapter_id,
        "title": ctx["title"],
        "icon": icon,
        "default_quest_shape": "circle",
        "quests": ftb_quests,
    }
    # 【修复4】group 为空时不写该字段
    if group_id:
        chapter_dict["group"] = group_id
    return chapter_dict


def save_chapter_snbt(chapter_index, quests, chapter_icon, items, group_id, output_dir):
    if not quests:
        log(f"  [跳过] 第 {chapter_index + 1} 章无任务")
        return None
    if not group_id:
        log(f"  [警告] 第 {chapter_index + 1} 章 group_id 为空，"
            f"请检查 CHAPTER_GROUPS[*].title 是否填写且唯一")
    os.makedirs(output_dir, exist_ok=True)
    chapter_dict = _build_chapter_dict(chapter_index, quests, chapter_icon, items, group_id)
    text = _snbt_value(chapter_dict, 0)
    path = os.path.join(output_dir, f"chapter_{chapter_index + 1:02d}.snbt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"  [保存] {path}（{len(quests)} 个任务）")
    return chapter_dict["id"]


def save_chapter_groups_snbt(group_titles, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    groups = []
    title_to_id = {}
    seen_titles = set()
    for title in group_titles:
        # 【修复5】组标题硬校验：空/重复直接报错
        if not title:
            raise ValueError("章节组标题不能为空（检查 CHAPTER_GROUPS[*].title）")
        if title in seen_titles:
            raise ValueError(f"章节组标题重复: '{title}'，每个组必须唯一")
        seen_titles.add(title)
        gid = ID_POOL.new()
        groups.append({"id": gid, "title": title})
        title_to_id[title] = gid
    data = {"chapter_groups": groups}
    path = os.path.join(output_dir, "chapter_groups.snbt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_snbt_value(data, 0))
    log(f"[保存] 章节组 -> {path}（{len(groups)} 个组）")
    return title_to_id


def save_data_snbt(output_dir, pack_title=None):
    """生成 data.snbt 全局配置。"""
    if pack_title is None:
        pack_title = C("PACK_TITLE", "") or "FTB Quests"
    os.makedirs(output_dir, exist_ok=True)
    # 【修复3】progression_mode 默认 linear
    progression_mode = C("PROGRESSION_MODE", "linear")
    if progression_mode == "flexible":
        log("[警告] PROGRESSION_MODE = flexible，会启用 FTB 排除判定逻辑，"
            "存在 isExcludedByOtherQuestline 递归风险，建议改为 linear")
    data = {
        "title": pack_title,
        "default_quest_shape": "circle",
        "progression_mode": progression_mode,
        "default_autoclaim_rewards": "disabled",
        "default_consume_items": False,
        "default_reward_team": True,
        "detection_delay": 10,
        "drop_loot_crates": False,
        "fallback_locale": "",
        "grid_scale": 0.5,
        "pause_game": False,
        "show_lock_icons": True,
        "exclusion_enabled": False,
    }
    path = os.path.join(output_dir, "data.snbt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_snbt_value(data, 0))
    log(f"[保存] 全局配置 -> {path}（progression_mode={progression_mode}）")


# ==================== 【修复9】跨章节依赖检查 ====================
def check_cross_chapter_dependencies(output_dir):
    """生成结束后，扫描所有 chapter_*.snbt，检查依赖 ID 是否跨章节。"""
    chapter_files = sorted(
        f for f in os.listdir(output_dir)
        if f.startswith("chapter_") and f.endswith(".snbt")
    )
    if not chapter_files:
        log("[跨章节检查] 未找到 chapter_*.snbt，跳过")
        return 0

    chapter_quest_ids = {}
    chapter_deps = {}
    for fname in chapter_files:
        path = os.path.join(output_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        ids = set(re.findall(r'^\s*id:\s*"?(\d+)"?', text, re.M))
        quest_blocks = re.findall(
            r'\{\s*id:\s*"?(\d+)"?,.*?tasks:', text, re.S
        )
        chapter_quest_ids[fname] = set(quest_blocks) if quest_blocks else ids
        deps = []
        for m in re.finditer(
            r'\{\s*id:\s*"?(\d+)"?,.*?dependencies:\s*\[(.*?)\]',
            text, re.S
        ):
            qid = m.group(1)
            dep_ids = re.findall(r'"(\d+)"', m.group(2))
            deps.append((qid, dep_ids))
        chapter_deps[fname] = deps

    id_to_chapter = {}
    for fname, ids in chapter_quest_ids.items():
        for iid in ids:
            if iid in id_to_chapter:
                log(f"[跨章节检查] 警告: id {iid} 同时出现在 "
                    f"{id_to_chapter[iid]} 和 {fname}（ID 冲突）")
            id_to_chapter[iid] = fname

    cross_count = 0
    for fname, deps in chapter_deps.items():
        for qid, dep_ids in deps:
            for dep_id in dep_ids:
                owner = id_to_chapter.get(dep_id)
                if owner is None:
                    log(f"[跨章节检查] 警告: {fname} 中 quest {qid} "
                        f"依赖了不存在的 id {dep_id}")
                    cross_count += 1
                elif owner != fname:
                    log(f"[跨章节检查] ✗ 跨章节依赖: "
                        f"{fname} 中 quest {qid} -> {dep_id} "
                        f"（属于 {owner}）")
                    cross_count += 1

    if cross_count:
        log(f"\n[跨章节检查] 发现 {cross_count} 条跨章节/无效依赖！")
        log("[跨章节检查] 这些依赖可能触发 FTB 排除判定递归，请检查生成逻辑。")
    else:
        log(f"\n[跨章节检查] ✓ 全部 {len(chapter_files)} 个章节文件，"
            f"未发现跨章节依赖。")
    return cross_count


# ==================== 【修复12】本章内环检测 ====================
def check_cycles(output_dir):
    """生成结束后，扫描所有 chapter_*.snbt，检查本章内是否存在循环依赖。"""
    chapter_files = sorted(
        f for f in os.listdir(output_dir)
        if f.startswith("chapter_") and f.endswith(".snbt")
    )
    if not chapter_files:
        log("[环检测] 未找到 chapter_*.snbt，跳过")
        return 0

    total_cycles = 0
    for fname in chapter_files:
        path = os.path.join(output_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        quest_ids = set(re.findall(r'\{\s*id:\s*"?(\d+)"?,.*?tasks:', text, re.S))
        graph = {qid: [] for qid in quest_ids}
        for m in re.finditer(
            r'\{\s*id:\s*"?(\d+)"?,.*?dependencies:\s*\[(.*?)\]',
            text, re.S
        ):
            qid = m.group(1)
            dep_ids = re.findall(r'"(\d+)"', m.group(2))
            if qid in graph:
                graph[qid] = [d for d in dep_ids if d in quest_ids]

        color = {nid: 0 for nid in graph}
        cycles_found = []

        def dfs_cycle(node, stack):
            color[node] = 1
            stack.append(node)
            for dep in graph[node]:
                c = color.get(dep, 0)
                if c == 1:
                    try:
                        idx = stack.index(dep)
                        cycle_path = stack[idx:] + [dep]
                    except ValueError:
                        cycle_path = [node, dep]
                    cycles_found.append(cycle_path)
                elif c == 0:
                    dfs_cycle(dep, stack)
            stack.pop()
            color[node] = 2

        for nid in list(graph):
            if color[nid] == 0:
                dfs_cycle(nid, [])

        if cycles_found:
            total_cycles += len(cycles_found)
            log(f"[环检测] ✗ {fname} 发现 {len(cycles_found)} 个环：")
            for cyc in cycles_found[:5]:
                log(f"    → {' -> '.join(cyc)}")
            if len(cycles_found) > 5:
                log(f"    ... 还有 {len(cycles_found) - 5} 个环未列出")

    if total_cycles:
        log(f"\n[环检测] 发现 {total_cycles} 个循环依赖！")
        log("[环检测] 循环依赖会触发 FTB isQuestObjectExcluded 递归爆栈。")
    else:
        log(f"\n[环检测] ✓ 全部 {len(chapter_files)} 个章节文件，未发现循环依赖。")
    return total_cycles


# ==================== 【修复13】依赖繁简检查 ====================
def check_dependency_complexity(output_dir, threshold=3):
    """扫描生成的 SNBT，统计每个章节的依赖数量，报告过繁章节。

    threshold：单个任务依赖数超过此值即视为“过繁”。
    """
    chapter_files = sorted(
        f for f in os.listdir(output_dir)
        if f.startswith("chapter_") and f.endswith(".snbt")
    )
    if not chapter_files:
        log("[繁简检查] 未找到 chapter_*.snbt，跳过")
        return 0

    total_heavy = 0
    for fname in chapter_files:
        path = os.path.join(output_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        dep_counts = []
        for m in re.finditer(r'dependencies:\s*\[(.*?)\]', text, re.S):
            ids = re.findall(r'"(\d+)"', m.group(1))
            dep_counts.append(len(ids))

        heavy = [c for c in dep_counts if c > threshold]
        avg = sum(dep_counts) / len(dep_counts) if dep_counts else 0
        total_heavy += len(heavy)

        if heavy:
            log(f"[繁简检查] {fname}: {len(dep_counts)} 个任务，"
                f"平均依赖 {avg:.2f}，{len(heavy)} 个任务依赖 > {threshold}")
        else:
            log(f"[繁简检查] ✓ {fname}: {len(dep_counts)} 个任务，"
                f"平均依赖 {avg:.2f}，无过繁任务")

    if total_heavy:
        log(f"\n[繁简检查] 共 {total_heavy} 个任务依赖过繁（> {threshold}）")
    else:
        log(f"\n[繁简检查] ✓ 全部章节依赖繁简正常。")
    return total_heavy


# ==================== 主流程 ====================
def main():
    log_path = C("LOG_FILE", "")
    init_log(log_path)
    log("=" * 60)
    log("FTB Quests 任务书自动生成器 启动")
    log("=" * 60)

    _load_mcmod_cache()

    items = load_items(C("ITEMS_FILE", ""))
    entities = load_entities(C("ENTITIES_FILE", ""))
    structures = load_structures(C("STRUCTURES_FILE", ""))
    modlist = load_modlist(C("MODLIST_FILE", ""))

    global _modlist_map
    _modlist_map = modlist

    if not items:
        log("[错误] items.json 为空，无法生成 item 任务，退出")
        close_log()
        return

    batches_per_chapter = int(C("DEFAULT_BATCHES_PER_CHAPTER", 3))
    batch_size = int(C("BATCH_SIZE", 6))
    max_tokens = int(C("MAX_TOKENS", 8000))
    if sys.stdin.isatty():
        try:
            batches_per_chapter, batch_size, max_tokens = ask_generation_options()
        except Exception:
            pass
    else:
        log(f"[非交互] 使用默认规模: {batches_per_chapter} 批 × {batch_size} 个，max_tokens={max_tokens}")

    seed = C("RANDOM_SEED", None)
    if seed is not None:
        random.seed(seed)
        log(f"[随机种子] {seed}")

    chapters_output = C("CHAPTERS_OUTPUT_DIR", os.path.join(C("OUTPUT_DIR", "output"), "chapters"))
    os.makedirs(chapters_output, exist_ok=True)

    # 先生成全局配置与章节组
    save_data_snbt(chapters_output)
    group_titles = [g.get("title", "") for g in C("CHAPTER_GROUPS", [])]
    title_to_group_id = save_chapter_groups_snbt(group_titles, chapters_output)

    flat = cfg.flatten_chapters()
    total = len(flat)
    log(f"[章节] 共 {total} 章待生成")

    success = 0
    for idx, ch in enumerate(flat):
        ctx = chapter_context(idx)
        group_title = group_titles[ctx["group_index"]] if ctx["group_index"] < len(group_titles) else ""
        group_id = title_to_group_id.get(group_title, "")
        try:
            quests = generate_chapter(
                idx, items, entities, structures,
                batches_per_chapter, batch_size, max_tokens,
            )
        except Exception as e:
            log(f"[错误] 第 {idx + 1} 章生成异常: {e}")
            continue
        cid = save_chapter_snbt(
            idx, quests, ctx["icon"], items, group_id, chapters_output
        )
        if cid:
            success += 1
        time.sleep(0.3)

    _save_mcmod_cache()

    # 【修复9】跨章节依赖检查
    log("\n" + "=" * 60)
    log("[跨章节检查] 开始扫描生成的 SNBT 文件...")
    cross = check_cross_chapter_dependencies(chapters_output)
    log("=" * 60)

    # 【修复12】本章内环检测
    log("\n" + "=" * 60)
    log("[环检测] 开始扫描本章内循环依赖...")
    cycles = check_cycles(chapters_output)
    log("=" * 60)

    # 【修复13】依赖繁简检查
    log("\n" + "=" * 60)
    log("[繁简检查] 开始扫描任务依赖繁简...")
    heavy = check_dependency_complexity(chapters_output)
    log("=" * 60)

    log("\n" + "=" * 60)
    log(f"生成结束：成功 {success}/{total} 章")
    log(f"输出目录: {chapters_output}")
    log(f"跨章节依赖: {cross} 条" + ("（安全）" if cross == 0 else "（请检查上方日志）"))
    log(f"循环依赖: {cycles} 个" + ("（安全）" if cycles == 0 else "（请检查上方日志）"))
    log(f"过繁依赖任务: {heavy} 个" + ("（安全）" if heavy == 0 else "（请检查上方日志）"))
    if cross == 0 and cycles == 0 and heavy == 0:
        log("✓ 全部检查通过，可以进游戏测试。")
    else:
        log("✗ 存在依赖问题，建议先修复再进游戏。")
    log("=" * 60)
    close_log()


if __name__ == "__main__":
    main()