第 1 步：确认 Termux 环境

打开 Termux，执行：

```bash python --version
```

没有输出就装：

```bash pkg install -y python
```

然后给存储权限：

```bash termux-setup-storage
```

弹窗点允许。

---

第 2 步：安装依赖

```bash pip install requests
```

看到 Successfully installed requests... 即可。

---

第 3 步：检查脚本那一行

打开 ftb.py，确认这行是：

```python API_KEY = os.environ.get("DEEPSEEK_API_KEY")
```

括号里必须是 DEEPSEEK_API_KEY，不能是 sk- 开头的字符串。 如果现在是 os.environ.get("sk-...")，改回来。文件里不能出现任何真实 Key。

---

第 4 步：确认文件在位

```bash cd /storage/emulated/0/Download/py
ls
```

必须看到 ftb.py、items.json、structure_dump.txt等。缺了先补上。

---

第 5 步：设置 Key 并验证

在同一个 Termux 窗口执行（把引号里换成你的新 Key）：

```bash export DEEPSEEK_API_KEY="你的新key"
```

然后必须验证：

```bash echo $DEEPSEEK_API_KEY
```

能打印出 Key 才能继续。 打印为空就重新 export，别往下走。

---

第 6 步：先测网络通不通

```bash curl -I --max-time 10 https://api.deepseek.com
```

· 返回 HTTP/... 状态码 → 网络通，继续第 8 步。
· 卡住或报错 → 手机网络连不上 DeepSeek，先解决网络（换网络、开代理等）。

---

第 7 步：手动测一次 API（关键）

```bash curl https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' \
  --max-time 30
```

· 返回带 "content" 的 JSON → Key 和模型都正常，进第 9 步。
· 返回 401 → Key 无效，回第 6 步。
· 返回 400 或 404 提到 model → 模型名不对，把脚本里 MODEL 换成报错里提示的可用的模型名。
· 超时 → 网络问题，回第 7 步。

---

第 8 步：防止 Termux 休眠

```bash termux-wake-lock
```

这步别省，能避免请求挂起。

---

第 9 步：先只跑一章测试

为了快速验证流程，先临时把脚本里 TOTAL_CHAPTERS = 9 改成 TOTAL_CHAPTERS = 1，然后：

```bash python ftb.py
```

耐心等 1~2 分钟。如果终端停在 [1/1] 生成... 不动，是正常的，API 在生成内容，别急着 Ctrl+C。

跑通后你会看到 chapter_01.snbt 和 data.snbt 生成。确认没问题后，把 TOTAL_CHAPTERS 改回 9，再完整跑一遍。

---

现在从第 1 步开始。卡在哪一步，就把那一步的命令和终端输出发我。