基于你自己做的 IdDumper 模组，我已经把这份教程重写并优化了。现在完全不需要再去下载和安装那 4 个第三方模组了，直接用你写的 iddumper 导出的 JSON 文件即可。

因为你的脚本现在已经支持直接读取 JSON，所以教程变得非常简洁。以下是专为你现在这套流程定制的全新操作指南：

---

FTB Quests 任务书自动生成器（IdDumper 专属版）从零跑通教程

这套教程分为三个阶段：准备数据（你的模组） → 配置环境（Termux） → 修改代码并运行。

阶段 A：使用 IdDumper 导出数据

A1. 准备游戏环境

1. 确保你的 Minecraft 是 1.20.1 版本。
2. 如果你玩的是 Fabric 端，请安装 Fabric API 以及你做的 iddumper-1.0.0.jar。
3. 如果你玩的是 Forge 端，直接把 iddumper-1.0.0.jar 放进 mods 文件夹。

A2. 游戏内执行指令
进入任意一个存档（确保开启了作弊/你是OP），在聊天框输入：

```mcfunction
/dumpids
```

执行后，聊天框会提示：§aID 导出完成: <路径>。

A3. 转移文件到工作目录
去你的存档目录下（通常是 saves/你的存档名/dumpids/），找到这 6 个文件：

· items.json（物品）
· entities.json（实体）
· structures.json（结构）
· modlist.json（模组列表）
· advancements.json（进度/成就，可选）
· fluids.json（流体，可选）

在手机存储里新建一个文件夹 py，把这 6 个文件全部移动过去：

```text
/storage/emulated/0/Download/py/
├── ftb-bate.py          ← 你的 Python 主程序
├── config.py            ← 你的配置文件
├── items.json
├── entities.json
├── structures.json
├── modlist.json
└── (以及可选的两个 json)
```

---

阶段 B：准备环境（Termux）

B1. 安装 Python 与依赖

```bash
pkg update -y
pkg install -y python
termux-setup-storage # 弹窗记得点允许
pip install requests
```

B2. 设置 API Key

```bash
export DEEPSEEK_API_KEY="你的API_KEY"
echo $DEEPSEEK_API_KEY  # 确认能打印出你的 key
```

(注意：每次新开 Termux 窗口都需要重新 export)

B3. 测试网络连通性

```bash
curl -I --max-time 10 https://api.deepseek.com
```

如果返回 200 或 400，说明网络没问题。

B4. 防休眠

```bash
termux-wake-lock
```

---

阶段 C：修改代码与运行

C1. 修改 config.py（非常关键）
用文本编辑器打开 config.py，找到路径部分。保证路径与你存放 json 文件的路径完全一致：

```python
BASE_DIR = "/storage/emulated/0/Download/py/dumpids"
# 如果你的文件直接放在了 py 根目录，就改成 "/storage/emulated/0/Download/py"
```

确保下面的几行能正确指向文件名（如果文件直接在 py 目录，去掉 dumpids/）：

```python
MODLIST_FILE      = os.path.join(BASE_DIR, "modlist.json")
ITEMS_FILE        = os.path.join(BASE_DIR, "items.json")
STRUCTURES_FILE   = os.path.join(BASE_DIR, "structures.json")
ENTITIES_FILE     = os.path.join(BASE_DIR, "entities.json")
ADVANCEMENTS_FILE = os.path.join(BASE_DIR, "advancements.json")
FLUIDS_FILE       = os.path.join(BASE_DIR, "fluids.json")
```

C2. 填写章节信息
还是在 config.py 里，找到 CHAPTER_GROUPS。按你的整合包实际内容，填写章节的标题、要求等。如果不需要特定模组限制，item_prefixes 留空列表 [] 即可。

C3. 运行脚本

```bash
cd /storage/emulated/0/Download/py
python ftb-bate.py
```

C4. 交互询问
程序启动后，会问你两个问题：

1. 是否允许生成【成就/进度】类型任务？ [y/N]: 
   (如果你导出了 advancements.json，且你的 FTB Quests 支持成就任务，输入 y)
2. 是否允许生成【流体】类型任务？ [y/N]: 
   (输入 y 或 n)

等待 AI 跑完，你会在 py 目录下看到生成的 output 文件夹，里面有 quests.json 和 reward_tables.snbt。

---

⚠️ 最容易卡住的 3 个点

1. 找不到 JSON 文件
   · 原因：config.py 里的 BASE_DIR 路径写错了，或者文件没放进去。
   · 解决：在 Termux 里运行 ls /storage/emulated/0/Download/py，亲眼确认那几个 .json 文件就在那里。
2. API 调用报 401 错误
   · 原因：Key 没有设置，或者 export 的窗口失效了。
   · 解决：重新 export DEEPSEEK_API_KEY="..."。
3. 导入游戏提示“未知任务类型”
   · 原因：FTB Quests 原版可能不支持 advancement 或 fluid 类型的任务。
   · 解决：在 config.py 的 CHAPTER_GROUPS 里，把 task_types 里面的 "advancement" 或 "fluid" 删掉，只保留 ["item", "checkmark", "structure", "kill"]。运行脚本时对应问题也选 n。

(如果你不想手动改，可以把主体和配置文件、以及这个教程全喂给 AI，让 AI 根据你的实际游戏路径和想法全自动改好。)