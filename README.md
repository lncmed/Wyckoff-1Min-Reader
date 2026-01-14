项目名称：A-Share Wyckoff AI Analyst (A股威科夫AI分析师)


本人第一个项目，感谢chatgpt/gemini的大力支持，纯ai手搓。欢迎留言交流

           
[简介]
这是一个基于 Python 的自动化工具，结合 Akshare 数据接口与 AI 大模型（GPT-4o / DeepSeek），自动拉取 A 股分钟级 K 线，绘制威科夫风格图表，并生成专业操盘分析报告。

[核心功能]
1. 数据：自动获取 A 股实时/历史分钟数据。
2. 绘图：本地生成含 MA50/MA200 及成交量的 K 线图。
3. 分析：AI 模拟威科夫本人，基于供求定律进行趋势推演。
4. 推送：支持 GitHub Actions 定时运行并推送 Telegram。

[安装依赖]
请确保安装 Python 3.8+，并在终端运行：
pip install pandas akshare mplfinance openai requests

[环境变量配置]
程序通过环境变量控制，支持本地或 CI/CD 环境：

- OPENAI_API_KEY  (必填): 你的 API 密钥
- SYMBOL          (选填): 股票代码 (默认 600970)
- BARS_COUNT      (选填): 分析 K 线数量 (默认 600)
- OPENAI_BASE_URL (选填): 自定义接口地址 (如 DeepSeek 需填 https://api.deepseek.com)
- AI_MODEL        (选填): 模型名称 (默认 gpt-4o-mini)

[运行方法]
1. Linux/Mac:
   export OPENAI_API_KEY="sk-xxxx"
   python main.py

2. Windows CMD/PowerShell:
   set OPENAI_API_KEY=sk-xxxx
   python main.py

[输出结果]
运行成功后，文件将保存在 reports/ 目录下：
- .png 文件：威科夫 K 线图表
- .md  文件：AI 分析报告
