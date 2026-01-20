import os
import time
import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import akshare as ak
import mplfinance as mpf
from openai import OpenAI
import numpy as np
import markdown
from xhtml2pdf import pisa
from sheet_manager import SheetManager 
import concurrent.futures 

# ==========================================
# 1. 数据获取模块
# ==========================================

def fetch_stock_data_dynamic(symbol: str, buy_date_str: str) -> dict:
    clean_digits = ''.join(filter(str.isdigit, str(symbol)))
    symbol_code = clean_digits.zfill(6)
    
    # print(f"   -> [{symbol_code}] 正在获取数据...")

    try:
        if buy_date_str and str(buy_date_str) != 'nan' and len(str(buy_date_str)) >= 10:
            buy_dt = datetime.strptime(str(buy_date_str)[:10], "%Y-%m-%d")
            start_dt = buy_dt - timedelta(days=15) 
            start_date_em = start_dt.strftime("%Y%m%d")
        else:
            start_date_em = (datetime.now() - timedelta(days=15)).strftime("%Y%m%d")
    except:
        start_date_em = (datetime.now() - timedelta(days=15)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist_min_em(symbol=symbol_code, period="5", start_date=start_date_em, adjust="qfq")
    except Exception as e:
        print(f"   [Error] {symbol_code} 5min接口报错: {e}")
        return {"df": pd.DataFrame(), "period": "5m"}

    if df.empty:
        return {"df": pd.DataFrame(), "period": "5m"}

    current_period = "5m"
    if len(df) > 960:
        try:
            df_15 = ak.stock_zh_a_hist_min_em(symbol=symbol_code, period="15", adjust="qfq")
            rename_map = {"时间": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"}
            df_15 = df_15.rename(columns={k: v for k, v in rename_map.items() if k in df_15.columns})
            df = df_15.tail(960).reset_index(drop=True) 
            current_period = "15m"
        except:
            df = df.tail(960)

    rename_map = {"时间": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"}
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    
    if "date" in df.columns: df["date"] = pd.to_datetime(df["date"])
    cols = ["open", "high", "low", "close", "volume"]
    valid_cols = [c for c in cols if c in df.columns]
    df[valid_cols] = df[valid_cols].astype(float)

    if "open" in df.columns and (df["open"] == 0).any():
        df["open"] = df["open"].replace(0, np.nan)
        if "close" in df.columns:
            df["open"] = df["open"].fillna(df["close"].shift(1)).fillna(df["close"])

    return {"df": df, "period": current_period}

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "close" in df.columns:
        df["ma50"] = df["close"].rolling(50).mean()
        df["ma200"] = df["close"].rolling(200).mean()
    return df

# ==========================================
# 2. 绘图模块
# ==========================================

def generate_local_chart(symbol: str, df: pd.DataFrame, save_path: str, period: str):
    if df.empty: return
    plot_df = df.copy()
    if "date" in plot_df.columns: plot_df.set_index("date", inplace=True)

    mc = mpf.make_marketcolors(up='#ff3333', down='#00b060', edge='inherit', wick='inherit', volume={'up': '#ff3333', 'down': '#00b060'}, inherit=True)
    s = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=mc, gridstyle=':', y_on_right=True)
    apds = []
    if 'ma50' in plot_df.columns: apds.append(mpf.make_addplot(plot_df['ma50'], color='#ff9900', width=1.5))
    if 'ma200' in plot_df.columns: apds.append(mpf.make_addplot(plot_df['ma200'], color='#2196f3', width=2.0))

    try:
        mpf.plot(plot_df, type='candle', style=s, addplot=apds, volume=True, title=f"Wyckoff: {symbol} ({period})", savefig=dict(fname=save_path, dpi=150, bbox_inches='tight'), warn_too_much_data=2000)
    except Exception as e:
        print(f"   [Error] {symbol} 绘图失败: {e}")

# ==========================================
# 3. AI 分析模块 (无修正版)
# ==========================================

def get_prompt_content(symbol, df, position_info):
    prompt_template = os.getenv("WYCKOFF_PROMPT_TEMPLATE")
    if not prompt_template and os.path.exists("prompt_secret.txt"):
        try:
            with open("prompt_secret.txt", "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except: pass
    if not prompt_template: return None

    csv_data = df.to_csv(index=False)
    latest = df.iloc[-1]

    base_prompt = prompt_template.replace("{symbol}", symbol) \
                          .replace("{latest_time}", str(latest["date"])) \
                          .replace("{latest_price}", str(latest["close"])) \
                          .replace("{csv_data}", csv_data)
    
    buy_date = position_info.get('date', 'N/A')
    buy_price = position_info.get('price', 'N/A')
    qty = position_info.get('qty', 'N/A')

    position_text = (
        f"\n\n[USER POSITION DATA]\n"
        f"Symbol: {symbol}\n"
        f"Buy Date: {buy_date}\n"
        f"Cost Price: {buy_price}\n"
        f"Quantity: {qty}\n"
        f"(Note: Please analyze the current trend based on this position data.)"
    )
    
    return base_prompt + position_text

def call_gemini_http(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: raise ValueError("GEMINI_API_KEY missing")
    
    # ⚠️【遵照指示】直接使用环境变量，不做任何修正
    # 默认值留空，强迫它读取 GEMINI_MODEL
    model_name = os.getenv("GEMINI_MODEL") 
    
    # 打印出来确认一下
    # print(f"   >>> Gemini 正在请求: {model_name} ...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "system_instruction": {"parts": [{"text": "You are Richard D. Wyckoff."}]},
        "generationConfig": {"temperature": 0.2},
        "safetySettings": safety_settings 
    }
    
    resp = requests.post(url, headers=headers, json=data, timeout=60)
    
    if resp.status_code != 200: 
        raise Exception(f"Gemini API Error {resp.status_code}: {resp.text}")
    
    try:
        result = resp.json()
        
        if "error" in result:
            raise Exception(f"API Error Logic: {result['error']}")

        candidates = result.get('candidates', [])
        if not candidates:
            feedback = result.get('promptFeedback', 'No Feedback')
            raise ValueError(f"No candidates returned. Feedback: {feedback}")
        
        content = candidates[0].get('content', {})
        parts = content.get('parts', [])
        
        if not parts:
            finish_reason = candidates[0].get('finishReason', 'UNKNOWN')
            raise ValueError(f"Content parts empty. FinishReason: {finish_reason}")
            
        text = parts[0].get('text', '')
        if not text: raise ValueError("Empty text")
        
        return text

    except Exception as e:
        # 如果出错，打印原始内容帮助调试
        print(f"   [Debug] {model_name} 解析崩溃. 响应片段:\n{resp.text[:500]}") 
        raise e 

def call_openai_official(prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("OpenAI Key missing")
    
    model_name = os.getenv("AI_MODEL", "gpt-4o")
    
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model_name, 
        messages=[{"role": "system", "content": "You are Richard D. Wyckoff."}, {"role": "user", "content": prompt}],
        temperature=0.2 
    )
    return resp.choices[0].message.content

def ai_analyze(symbol, df, position_info):
    prompt = get_prompt_content(symbol, df, position_info)
    if not prompt: return "Error: No Prompt"
    
    try: 
        return call_gemini_http(prompt)
    except Exception as e: 
        print(f"   ⚠️ [{symbol}] Gemini ({os.getenv('GEMINI_MODEL')}) 失败: {e} -> 切 OpenAI")
        try: 
            return call_openai_official(prompt)
        except Exception as e2: 
            return f"Analysis Failed. Gemini Error: {e}. OpenAI Error: {e2}"

# ==========================================
# 5. 主程序 (5线程并发)
# ==========================================

def process_one_stock(symbol: str, position_info: dict):
    clean_digits = ''.join(filter(str.isdigit, str(symbol)))
    clean_symbol = clean_digits.zfill(6)

    print(f"🚀 [{clean_symbol}] 开始分析...")

    data_res = fetch_stock_data_dynamic(clean_symbol, position_info.get('date'))
    df = data_res["df"]
    period = data_res["period"]
    
    if df.empty:
        print(f"   ⚠️ [{clean_symbol}] 数据为空，跳过")
        return None
    
    df = add_indicators(df)

    beijing_tz = timezone(timedelta(hours=8))
    ts = datetime.now(beijing_tz).strftime("%Y%m%d_%H%M%S")
    
    # 保存 CSV
    csv_path = f"data/{clean_symbol}_{period}_{ts}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    chart_path = f"reports/{clean_symbol}_chart_{ts}.png"
    pdf_path = f"reports/{clean_symbol}_report_{period}_{ts}.pdf"
    
    generate_local_chart(clean_symbol, df, chart_path, period)
    report_text = ai_analyze(clean_symbol, df, position_info)
    
    if generate_pdf_report(clean_symbol, chart_path, report_text, pdf_path):
        print(f"✅ [{clean_symbol}] 报告生成完毕")
        return pdf_path
    
    return None

def main():
    os.makedirs("data", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    print("☁️ 正在连接 Google Sheets...")
    try:
        sm = SheetManager()
        stocks_dict = sm.get_all_stocks()
        print(f"📋 获取 {len(stocks_dict)} 个任务")
    except Exception as e:
        print(f"❌ Sheet 连接失败: {e}")
        return

    generated_pdfs = []
    
    # 5 线程并发
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {
            executor.submit(process_one_stock, symbol, info): symbol 
            for symbol, info in stocks_dict.items()
        }
        
        for future in concurrent.futures.as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                result = future.result()
                if result:
                    generated_pdfs.append(result)
            except Exception as exc:
                print(f"❌ [{symbol}] 处理发生异常: {exc}")

    if generated_pdfs:
        print(f"\n📝 生成推送清单 ({len(generated_pdfs)}):")
        with open("push_list.txt", "w", encoding="utf-8") as f:
            for pdf in generated_pdfs:
                print(f"   -> {pdf}")
                f.write(f"{pdf}\n")
    else:
        print("\n⚠️ 无报告生成")

if __name__ == "__main__":
    main()
