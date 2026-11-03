详细操作步骤（从零到跑通）

下面按顺序一步步做，每步都有「做什么 / 怎么做 / 怎么确认成功」。

---

阶段 A：准备文件（游戏内导出）

A1. 安装 4 个模组

序号 模组 作用 导出文件
1 Modlist 导出模组列表 modlist.txt
2 Entity Dump 导出实体列表 entities_list.json
3 Tell Me My Items (TMMI) 导出物品列表 items.json
4 Structure Dump 导出结构列表 structure_dump.txt

怎么做：

1. 下载这 4 个模组的 .jar 文件（注意版本要匹配你的 Minecraft / 整合包版本）。
2. 把 .jar 全部放进 .minecraft/mods/ 文件夹。
3. 启动游戏，进入任意存档。

确认成功： 游戏能正常启动，模组列表里能看到这 4 个模组。

---

A2. 执行导出指令

进游戏后，在聊天框输入：

```mcfunction
/tmmiexport        # 导出物品 → items.json
/dumpstructures    # 导出结构 → structure_dump.txt
```

另外两个模组（Modlist、Entity Dump）通常是进游戏自动导出，或在模组配置界面里有导出按钮。

导出后去哪里找文件？ 按以下顺序翻：

1. .minecraft/config/ —— 最常见
2. .minecraft/ 根目录
3. 模组自己的配置文件夹（如 .minecraft/config/模组名/）
4. 如果还找不到，看游戏日志（.minecraft/logs/latest.log），搜模组名，日志里通常会打印导出路径

确认成功： 4 个文件都能找到：

· modlist.txt
· entities_list.json
· items.json
· structure_dump.txt

---

A3. 把 5 个文件放同一文件夹

在手机存储里建一个文件夹，比如：

```
/storage/emulated/0/Download/py/
├── ftb-bate.py          ← 你的脚本
├── modlist.txt
├── items.json
├── structure_dump.txt
└── entities_list.json
```

怎么做：

1. 用文件管理器（或 Termux 的 cp 命令）把上面 4 个导出文件复制到这个文件夹。
2. 把你的 ftb-bate.py 也放进去。

⚠️ 关键检查： 打开 ftb-bate.py，确认开头附近这一行：

```python
BASE_DIR = "/storage/emulated/0/Download/py"
```

必须和你实际放文件的路径完全一致。不一致就改成实际路径。

确认成功： 在 Termux 里执行 ls /storage/emulated/0/Download/py，能看到 5 个文件。

---

阶段 B：准备环境（Termux）

B1. 安装 Python + 存储权限

```bash
pkg update -y
pkg install -y python
termux-setup-storage
```

注意： termux-setup-storage 执行后会弹窗问是否允许访问存储，必须点「允许」。

确认成功：

```bash
python --version          # 显示 Python 3.x.x
ls /storage/emulated/0/   # 能看到 Download 等文件夹
```

---

B2. 安装依赖

```bash
pip install requests
```

确认成功：

```bash
python -c "import requests; print(requests.__version__)"
```

能打印出版本号即成功。

---

B3. 设置 API Key 并验证

```bash
export DEEPSEEK_API_KEY="你的新key"
echo $DEEPSEEK_API_KEY
```

确认成功： echo 能打印出你的 key（不是空行）。

⚠️ 重要提醒： export 只在当前 Termux 窗口有效。关掉窗口/新开窗口后要重新 export。建议每次开新窗口先跑一次 echo $DEEPSEEK_API_KEY 检查。

---

B4. 测网络 + 测 API（关键，别跳过）

第一步：测网络

```bash
curl -I --max-time 10 https://api.deepseek.com
```

第二步：测 API

```bash
curl https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' \
  --max-time 30
```

结果对照表：

返回 含义 处理
带 content 的 JSON ✅ 全通 进入阶段 C
401 Key 无效 回 B3 重设 key
400/404 提到 model 模型名不对 按报错里提示的可用模型名改脚本 MODEL = "..."
超时 网络问题 换网络 / 开代理

---

B5. 防休眠

```bash
termux-wake-lock
```

防止跑长任务时手机休眠导致中断。

---

阶段 C：合流运行

C1. 进入目录

```bash
cd /storage/emulated/0/Download/py
ls
```

确认成功： ls 能看到 5 个文件（脚本 + 4 个导出文件）。

---

C2. 先跑 1 章测试

临时改脚本： 打开 ftb-bate.py，把

```python
TOTAL_CHAPTERS = 10
```

改成

```python
TOTAL_CHAPTERS = 1
```

运行：

```bash
python ftb-bate.py
```

等待 1~2 分钟。

确认成功： 目录里出现：

· chapter_01.snbt
· data.snbt

如果报错，看报错信息对照 B4 的结果表排查。

---

C3. 改回完整章数，正式跑

把脚本改回：

```python
TOTAL_CHAPTERS = 10   # 你的暮色版是 10
```

再跑一遍：

```bash
python ftb-bate.py
```

建议： 先跑 termux-wake-lock，手机插电，别切后台，等它跑完。

---

附：最容易卡住的 3 个点

问题 原因 解决
文件找不到 4 个模组导出路径不统一 翻 .minecraft/config/、.minecraft/ 根目录、模组自己的配置文件夹；或看 logs/latest.log 里模组打印的路径
echo $DEEPSEEK_API_KEY 为空 export 只在当前窗口有效，关窗就没了 每次新开 Termux 窗口都要重新 export
API 返回 404 model 错误 deepseek-flash 模型名不对 看报错里提示的可用模型名，改脚本里的 MODEL = "..."

---

你贴的 9 步 ↔ 上面的对应关系

原 9 步 对应上面
第 1 步 确认 Termux 环境 B1
第 2 步 安装依赖 B2
第 3 步 检查脚本 API_KEY 行 A3
第 4 步 确认文件在位 A3 + C1
第 5 步 设置 Key 并验证 B3
第 6 步 测网络 B4（第一段 curl）
第 7 步 手动测 API B4（第二段 curl）
第 8 步 防休眠 B5
第 9 步 先跑一章测试 C2 → C3

---

按顺序做：A（准备文件）→ B（环境）→ C（跑），每个「确认成功」都过了再进下一步，基本不会卡。

实在不会的话可以把这些喂给AI，让其生成专属教程，支持中英文切换，改之前还得配置config.py文件，直接喂AI即可，目前那四个模组适配于1.20.1forge版本，其它版本可能有，没有的话就得安装其它模组进行导出ID。