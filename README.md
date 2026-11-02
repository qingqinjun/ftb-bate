---

总体流程图

```
┌─────────────────────────────────────────────┐
│ A. 准备文件（游戏内导出）                    │
│   1. 装 4 个模组                             │
│   2. 进游戏执行导出指令                      │
│   3. 把 4 份文件 + ftb-bate.py 放同一文件夹  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│ B. 准备环境（Termux）                        │
│   1. 装 Python + 存储权限                    │
│   2. pip install requests                    │
│   3. export DEEPSEEK_API_KEY                 │
│   4. curl 测网络 + 测 API                    │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│ C. 合流运行                                  │
│   1. cd 到文件夹                             │
│   2. 先跑 TOTAL_CHAPTERS=1 测试              │
│   3. 成功后再改回 9/10 完整跑                │
└─────────────────────────────────────────────┘
```

---

A. 准备文件（游戏内导出）

A1. 装 4 个模组

模组 作用 导出的文件
Modlist 导出模组列表 modlist.txt
Entity Dump 导出实体列表 entities_list.json
Tell Me My Items（TMMI） 导出物品列表 items.json
Structure Dump 导出结构列表 structure_dump.txt

放进 mods/ 文件夹，启动游戏。

A2. 进游戏执行导出指令

```mcfunction
/tmmiexport        # 导出物品 → items.json
/dumpstructures    # 导出结构 → structure_dump.txt
```

另外两个模组（Modlist、Entity Dump）通常是进游戏自动导出，或在模组配置里有按钮。导出后去 .minecraft/ 或 config/ 下找，文件名类似：

· modlist.txt
· entities_list.json

如果找不到，看模组的配置文件或日志，里面会写导出路径。

A3. 把 5 个文件放同一文件夹

```
/storage/emulated/0/Download/py/
├── ftb-bate.py          ← 你的脚本
├── modlist.txt
├── items.json
├── structure_dump.txt
└── entities_list.json
```

⚠️ 脚本里的 BASE_DIR 必须指向这个文件夹：

```python
BASE_DIR = "/storage/emulated/0/Download/py"
```

---

B. 准备环境（Termux）

按你贴的 9 步，我压缩成 4 个关键节点：

B1. 装 Python + 存储权限

```bash
pkg install -y python
termux-setup-storage   # 弹窗点允许
```

B2. 装依赖

```bash
pip install requests
```

B3. 设置 Key 并验证

```bash
export DEEPSEEK_API_KEY="你的新key"
echo $DEEPSEEK_API_KEY   # 必须能打印出来
```

B4. 测网络 + 测 API（关键，别跳过）

```bash
# 测网络
curl -I --max-time 10 https://api.deepseek.com

# 测 API（返回带 content 的 JSON 才算通）
curl https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' \
  --max-time 30
```

返回 含义 处理
带 content 的 JSON ✅ 全通 进 C
401 Key 无效 回 B3 重设
400/404 提到 model 模型名不对 改脚本里 MODEL
超时 网络问题 换网络/开代理

B5. 防休眠

```bash
termux-wake-lock
```

---

C. 合流运行

C1. 进目录

```bash
cd /storage/emulated/0/Download/py
ls   # 必须看到 5 个文件
```

C2. 先跑 1 章测试

临时改脚本：

```python
TOTAL_CHAPTERS = 1
```

运行：

```bash
python ftb-bate.py
```

等 1~2 分钟，看到 chapter_01.snbt 和 data.snbt 生成 = 成功。

C3. 改回完整章数

```python
TOTAL_CHAPTERS = 10   # 你的暮色版是 10
```

再跑一遍：

```bash
python ftb-bate.py
```

---

你贴的 9 步 vs 上面的梳理，对应关系

你贴的步骤 对应上面
第 1 步 确认 Termux 环境 B1
第 2 步 安装依赖 B2
第 3 步 检查脚本 API_KEY 行 A3（脚本检查）
第 4 步 确认文件在位 A3 + C1
第 5 步 设置 Key 并验证 B3
第 6 步 测网络 B4（第一段 curl）
第 7 步 手动测 API B4（第二段 curl）
第 8 步 防休眠 B5
第 9 步 先跑一章测试 C2 → C3

---

最容易卡住的 3 个点

1. 文件找不到：4 个模组导出路径不统一，去 .minecraft/config/、.minecraft/、模组自己的配置文件夹翻一遍，或者看游戏日志里模组打印的路径。
2. echo $DEEPSEEK_API_KEY 为空：export 只在当前 Termux 窗口有效，关掉窗口就没了。每次新开窗口都要重新 export。
3. API 返回 404 model 错误：deepseek-flash 这个模型名如果报错，看报错里提示的可用模型名，改脚本里 MODEL = "..."。

---