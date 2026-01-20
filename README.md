# 📈 Wyckoff-M1-Sentinel (威科夫 M1 哨兵)

![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated-green.svg)
![Strategy](https://img.shields.io/badge/Strategy-Wyckoff-orange.svg)
![AI Engine](https://img.shields.io/badge/AI-Gemini%20%7C%20GPT--4o-purple.svg)

> **拒绝情绪化交易，用代码还原市场真相。**
> 
> 一个基于 **GitHub Actions** 的全自动量化分析系统。它利用 **A股 1分钟微观数据**，结合 **AI 大模型 (Gemini/GPT-4o)** 进行 **威科夫 (Wyckoff)** 结构分析，并通过 **Telegram** 实现交互式监控与研报推送。

## ✨ 核心更新 (2026-01-20)

本次更新重构了数据源管理与底层分析逻辑，提升了系统的稳定性与智能化程度。

### 1. ☁️ Google Sheets 云端管理 (替换本地 TXT)
- **动态管理**：不再依赖静态的 `stock_list.txt`，直接通过 Google Sheets 管理持仓与关注列表。
- **持仓感知**：支持读取 `买入日期`、`持仓成本` 和 `持仓数量`。
- **纯文本注入**：持仓信息将以纯文本形式注入 AI Prompt，让 AI 根据你的成本优势/劣势提供针对性建议（Hold/Sell/Stop-Loss）。
- **双重连接模式**：支持通过 `Spreadsheet ID` (推荐) 或 `文件名` 连接表格，自动适配。

### 2. 📊 智能 K 线获取策略 (Smart Fetch)
重写了 `fetch_stock_data_dynamic` 逻辑，解决了数据源兼容性问题：
- **代码归一化**：强制执行 `.zfill(6)` 补全逻辑（如 `2641` -> `002641`），完美修复 Excel/Sheets 丢零导致的接口报错。
- **时间窗口回溯**：自动计算 `买入日期` 前 15 天作为分析窗口。
- **自适应周期切换**：
    1. 优先拉取 **5分钟** 级别 K 线。
    2. 若数据量超过 960 根（导致上下文过长），自动切换至 **15分钟** 级别。
    3. 确保 LLM 接收到的数据密度适中且具有代表性。

### 3. 🧠 AI 模型升级与容错
- **模型升级**：默认集成 Google 最新 **Gemini-3-Pro-Preview** (或 2.0/1.5 Flash)。
- **安全豁免**：配置 `BLOCK_NONE` 安全策略，防止 AI 因“金融建议敏感”而拒绝回答。
- **超时优化**：HTTP 请求超时延长至 **120秒**，适应深度思考模型。
- **Fail-Fast 机制**：若 Gemini 解析失败或返回空内容，立即触发异常并自动降级切换至 **OpenAI (GPT-4o)**。


---

## ✨ 核心功能 (Key Features)

* **🕵️‍♂️ 1分钟微观哨兵**：自动抓取 A 股 **1分钟 K 线**数据，捕捉肉眼难以察觉的主力吸筹/派发痕迹。
* **🧠 双引擎 AI 分析**：
    * **主引擎**：Google Gemini Pro (高速、免费)
    * **副引擎**：OpenAI GPT-4o (精准、兜底)
    * 深度分析供求关系，自动识别 Spring (弹簧效应)、UT (上冲回落)、LPS (最后支撑点) 等威科夫关键行为。
* **🤖 交互式 Telegram 机器人**：
    * **指令管理**：直接在电报群发送代码即可添加/删除监控，无需接触代码。
    * **研报推送**：自动生成包含红绿高对比 K 线图的 **PDF 研报**，推送到手机。
* **☁️ Serverless 架构**：完全运行在 GitHub Actions 上，**无需服务器，零成本维护**。
* **⏰ 智能调度**：
    * **午盘 (12:00)** & **收盘 (15:15)**：自动运行分析并推送报告。
    * **每 30 分钟**：自动同步 Telegram 指令，更新监控列表。


<img width="731" height="825" alt="image" src="https://github.com/user-attachments/assets/5af1f8fc-cc67-4c02-b34d-e1749180ce2c" />

---
## 🏗️ 系统架构

```mermaid
graph TD
    User(("👨‍💻 用户")) <-->|"指令交互 / 接收 PDF"| TG["Telegram Bot"]
    TG <-->|"每30分钟同步"| GH["GitHub Actions (Monitor)"]
    GH <-->|"读写"| LIST["stock_list.txt"]
    
    LIST -->|"读取列表"| JOB["GitHub Actions (Daily Report)"]
    JOB -->|"1. 获取数据"| API["AkShare 财经接口"]
    JOB -->|"2. 绘制图表"| PLOT["Mplfinance"]
    JOB -->|"3. AI推理"| AI["Gemini / GPT-4o"]
    JOB -->|"4. 生成PDF"| PDF["Report.pdf"]
    PDF -->|"推送"| TG
