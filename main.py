import os
import time
from datetime import datetime
import pandas as pd
import akshare as ak
import mplfinance as mpf
from openai import OpenAI
import google.generativeai as genai  # 新增 Gemini 库

# ==========================================
# 1. 数据获取模块
# ==========================================

def fetch_a_share_minute(symbol: str) -> pd.DataFrame:
    """获取A股1分钟K线 (使用东方财富接口)"""
    symbol_code = ''.join(filter(str.isdigit, symbol))
    print(f"正在获取 {symbol_code} 的1分钟数据 (Source: Eastmoney)...")

    try:
        df = ak.stock_zh_a_hist_min_em(
            symbol=symbol_code, 
            period="1", 
            adjust="qfq"
        )
    except Exception as e:
        print(f"获取失败: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    rename_map = {
        "时间": "date", "开盘": "open", "最高": "high",
        "最低": "low", "收盘": "close", "成交量": "volume"
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    
    df["date"] = pd.to_datetime(df["date"])
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    
    bars_count = int(os.getenv("BARS_COUNT", 600))
    df = df.sort_values("date").tail(bars_count).reset_index(drop=True)
    return df

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ma50"] = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()
    return df

# ==========================================
# 2. 本地绘图模块
# ==========================================

def generate_local_chart(symbol: str, df: pd.DataFrame, save_path: str):
    if df.empty: return

    plot_df = df.copy()
    plot_df.set_index("date", inplace=True)

    mc = mpf.make_marketcolors(up='red', down='green', edge='i', wick='i', volume='in', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

    apds = []
    if 'ma50' in plot_df.columns:
        apds.append(mpf.make_addplot(plot_df['ma50'], color='orange', width=1.0))
    if 'ma200' in plot_df.columns:
        apds.append(mpf.make_addplot(plot_df['ma200'], color='blue', width=1.2))

    try:
        mpf.plot(
            plot_df, type='candle', style=s, addplot=apds, volume=True,
            title=f"Wyckoff Chart: {symbol}",
            savefig=dict(fname=save_path, dpi=150, bbox_inches='tight'),
            warn_too_much_data=2000
        )
        print(f"[OK] Chart saved to: {save_path}")
    except Exception as e:
        print(f"[Error] 绘图失败: {e}")

# ==========================================
# 3. AI 分析模块 (双引擎：Gemini -> OpenAI)
# ==========================================

def get_prompt_content(symbol, df):
    """读取并填充 Prompt 模板"""
    prompt_template = os.getenv("WYCKOFF_PROMPT_TEMPLATE")
    
    # 本地回退
    if not prompt_template and os.path.exists("prompt_secret.txt"):
        try:
            with open("prompt_secret.txt", "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except: pass

    if not prompt_template:
        return None

    csv_data = df.to_csv(index=False)
    latest = df.iloc[-1]
    
    return prompt_template.replace("{symbol}", symbol) \
                          .replace("{latest_time}", str(latest["date"])) \
                          .replace("{latest_price}", str(latest["close"])) \
                          .replace("{csv_data}", csv_data)

def call_gemini(prompt: str) -> str:
    """调用 Google Gemini"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found")

    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    print(f"   >>> 尝试调用 Google Gemini ({model_name})...")
    
    genai.configure(api_key=api_key)
    # Gemini 1.5 支持 system instruction，更适合角色扮演
    model = genai.GenerativeModel(
        model_name,
        system_instruction="You are Richard D. Wyckoff. You follow strict Wyckoff logic."
    )
    
    response = model.generate_content(prompt)
    return response.text

def call_openai(prompt: str) -> str:
    """调用 OpenAI / DeepSeek (备用)"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found")
        
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.getenv("AI_MODEL", "gpt-4o")
    
    print(f"   >>> 尝试调用 OpenAI/Compatible ({model_name})...")
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model_name, 
        messages=[
            {"role": "system", "content": "You are Richard D. Wyckoff."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2 
    )
    return resp.choices[0].message.content

def ai_analyze_wyckoff(symbol: str, df: pd.DataFrame) -> str:
    print("正在准备 AI 分析...")
    prompt = get_prompt_content(symbol, df)
    
    if not prompt:
        return "错误：未找到 WYCKOFF_PROMPT_TEMPLATE，无法分析。"

    # === 策略：首选 Gemini，失败后降级 ===
    
    # 1. 尝试 Gemini
    try:
        return call_gemini(prompt)
    except Exception as e:
        print(f"[Warning] Gemini 调用失败: {e}")
        print("正在切换到备用通道 (OpenAI/DeepSeek)...")

    # 2. 尝试 OpenAI (Fallback)
    try:
        return call_openai(prompt)
    except Exception as e:
        error_msg = f"# 分析失败\n\nGemini 和 OpenAI 均无法响应。\n最后错误: `{e}`"
        print(f"[Error] 所有 AI 通道均失败: {e}")
        return error_msg

# ==========================================
# 4. 主程序
# ==========================================

def main():
    symbol = os.getenv("SYMBOL", "600970") 
    
    # 1. 获取数据
    df = fetch_a_share_minute(symbol)
    if df.empty:
        print("!!!" * 10)
        print(f"[错误] {symbol} 数据获取失败 (Empty DataFrame)")
        print("!!!" * 10)
        exit(1) # 强制报错让 Actions 变红
        
    df = add_indicators(df)

    # 目录准备
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("data", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    # 2. 保存CSV
    csv_path = f"data/{symbol}_1min_{ts}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[OK] CSV Saved: {csv_path}")

    # 3. 本地绘图
    chart_path = f"reports/{symbol}_chart_{ts}.png"
    generate_local_chart(symbol, df, chart_path)

    # 4. AI 分析 (双通道)
    report_text = ai_analyze_wyckoff(symbol, df)

    # 5. 保存报告
    report_path = f"reports/{symbol}_report_{ts}.md"
    final_report = f"![Chart](./{os.path.basename(chart_path)})\n\n{report_text}"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)

    print(f"[OK] Report Saved: {report_path}")

if __name__ == "__main__":
    main()
