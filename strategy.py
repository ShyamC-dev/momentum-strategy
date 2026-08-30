import os
import sys
import io
import time
import requests
import json
import pandas as pd
import yfinance as yf
from datetime import datetime

# 🔐 ACCESS LAYER: Read environment variables from GitHub
TO_WHATSAPP = os.environ.get("TO_WHATSAPP_NUMBER")
FROM_WHATSAPP = "whatsapp:+14155238886"

def get_nifty250():
    # Inline map dictionary to correct yfinance spelling mismatches & rebrands
    ticker_fixes = {
        "CENTURYTEX": "CENTURYTEX-EQ.NS", "GMRINFRA": "GMRINFRA-EQ.NS", "INFIBEAM": "CCAVENUE.NS",
        "JKLACEM": "JKLAKSHMI.NS", "LTIM": "LTM.NS", "MOTORS": "TATAMOTORS.NS", "NIPPON": "NAM-INDIA.NS",
        "BAJAJ-AUTO": "BAJAJ-AUTO.NS", "CHOLAHLD": "CHOLAHLDNG.NS", "M&M": "M&M.NS", "M&MFIN": "M&MFIN.NS",
        "MCDOWELL-N": "MCDOWELL-N.NS", "ESCORTKUB": "ESCORTS.NS"
    }
    # Generate a unique string for the current Month and Year (e.g., "August_2026")
    current_month_year = datetime.now().strftime("%B_%Y")
    cache_filename = f"nifty250_{current_month_year}.csv"
    raw_symbols = []

    # Check if the file for the current month already exists in the local workspace directory
    if os.path.exists(cache_filename):
        print(f"📦 Local Cache Found! Loading '{cache_filename}' instantly from storage...")
        df_cached = pd.read_csv(cache_filename)
        raw_symbols = df_cached['Symbol'].str.strip().tolist()
        print(f"✅ Loaded {len(raw_symbols)} tickers directly from local cache.")
    else:

      print("🌐 Contacting NiftyIndices (NSE)... Downloading official index list...")

      # Official direct link to the Nifty LargeMidcap 250 Index file
      url = "https://niftyindices.com/IndexConstituent/ind_niftylargemidcap250list.csv"

      # Spoof browser headers to bypass the NSE security firewalls instantly
      headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
      }
      try:
        response = requests.get(url, headers=headers, timeout=15).text
        lines = response.split('\n')

        # Locate where the true CSV headers start, bypassing any disclaimer junk lines
        start_idx = next(i for i, line in enumerate(lines) if "Symbol" in line)
        df_nse = pd.read_csv(io.StringIO("\n".join(lines[start_idx:])))
        raw_symbols = df_nse['Symbol'].str.strip().unique().tolist()
        # Save a clean version to the workspace disk to act as the cache for future runs
        df_nse[['Symbol']].to_csv(cache_filename, index=False)
        print(f"💾 Fresh index downloaded and cached locally as '{cache_filename}' for the month.")
        print(f"✅ Successfully compiled {len(raw_symbols)} tickers from official list.")
      except Exception as e:
        print(f"❌ Failed to fetch index online: {e}")
        raise SystemExit

    nifty250 = list(dict.fromkeys([ticker_fixes.get(sym, f"{sym}.NS") for sym in raw_symbols]))
    return nifty250

def check_regime():
    """Bypasses or acts as the macro trend switch via Nifty 50."""
    index_df = yf.download("^NSEI", period="2y", progress=False)
    index_df['SMA_200'] = index_df['Close'].rolling(window=200).mean()
    latest_idx = float(pd.Series(index_df['Close'].iloc[-1]).squeeze())
    sma200_idx = float(pd.Series(index_df['SMA_200'].iloc[-1]).squeeze())
    
    if latest_idx < sma200_idx:
        msg = f"⚠️ Market regime doesn't favour a SIP. Nifty 50 ({latest_idx:.2f}) is below 200 SMA ({sma200_idx:.2f}). Staying away."
        print(msg)
        # Send WhatsApp alert if credentials exist
        # sys.exit(0) # Exit pipeline safely without writing files

def run_analysis():

    check_regime()
    nifty250 = get_nifty250()    
    current_m_y = datetime.now().strftime("%B_%Y")
    chunks = [nifty250[i:i + 50] for i in range(0, len(nifty250), 50)]
    all_frames = []
    
    for i, chunk in enumerate(chunks):
        print(f"   📥 Downloading Batch Data {i+1}/{len(chunks)}...")
        try:
            batch = yf.download(chunk, period="1y", group_by='ticker', progress=False)
            all_frames.append(batch)
            time.sleep(2)
        except:
            continue
        
    data = pd.concat(all_frames, axis=1)
    ranking_data = []
    
    for ticker in nifty250:
        try:
            if ticker not in data.columns.get_level_values(0): continue
            stock_df = data[ticker].copy()
            stock_df.columns = stock_df.columns.str.strip()  # Collapses multi-layer headers to a single flat index string
        
            # Drop rows missing data points to ensure historical calculations line up accurately
            stock_df = stock_df.dropna(subset=['Close', 'Volume'])
            if len(stock_df) < 200:
              print("Dropped {} due to less than 200 days of data".format(ticker))
              continue
        
            close_s = stock_df['Close']
            vol_s = stock_df['Volume']
        
            ema5 = close_s.ewm(span=5, adjust=False).mean()
            ema20 = close_s.ewm(span=20, adjust=False).mean()
            ema50 = close_s.ewm(span=50, adjust=False).mean()
            ema100 = close_s.ewm(span=100, adjust=False).mean()
            ema200 = close_s.ewm(span=200, adjust=False).mean()
            # 🌟 RSI 21 CALCULATION ENGINE
            delta = close_s.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
        
            avg_gain = gain.ewm(com=20, adjust=False).mean() # com = period - 1
            avg_loss = loss.ewm(com=20, adjust=False).mean()
        
            rsi21 = 100 - (100 / (1 + (avg_gain / avg_loss)))
            cur_rsi21 = float(rsi21.iloc[-1])
        
            # 🔒 RSI 50 FILTER GATE
            if cur_rsi21 < 50.0: 
                continue
        
            # [a] Trend Order Check
            if not (ema20.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1] > ema200.iloc[-1]): continue
            # [b] Momentum Check
            if ema20.iloc[-1] <= ema20.iloc[-21]: continue
            # [c] Max 1-Month Drawdown Check
            w1m = close_s.iloc[-21:]
            max_dd = ((w1m.max() - w1m.min()) / w1m.max()) * 100
            if max_dd > 15.0: continue
            # [d] Liquidity Check
            liq = float(close_s.iloc[-20:].mean()) * float(vol_s.iloc[-20:].mean())
            if liq <= 50000000: continue

            # Calculate your 3 trend difference percentages established in your model
            # ✅ FIX: Extract the latest single number ([-1]) before doing arithmetic
            val_5 = float(ema5.iloc[-1])
            val_20 = float(ema20.iloc[-1])
            val_50 = float(ema50.iloc[-1])
            val_100 = float(ema100.iloc[-1])
        
            # Calculate your 3 trend difference percentages cleanly using individual scalars
            diff_5_20 = ((val_5 - val_20) / val_20) * 100

            # [e] 🔒 THE SOFT-BUFFER GUARDRAIL
            # Allows minor tracking pullbacks (up to -1.0%) but axes true distribution/reversion crashes
            if diff_5_20 < -1.0: 
                continue
            diff_20_50 = ((val_20 - val_50) / val_50) * 100
            diff_50_100 = ((val_50 - val_100) / val_100) * 100
            
            score_vel = (diff_5_20 * 0.545) + (diff_20_50 * 0.273) + (diff_50_100 * 0.182)
            score_comp = (diff_5_20 * 0.20) + (diff_20_50 * 0.40) + (diff_50_100 * 0.40)
            
            ranking_data.append({
                'Ticker': ticker.replace('.NS', '').replace('-EQ', ''), 'Price': round(close_s.iloc[-1], 2),
                'Score Vel%': round(score_vel, 2), 'Score Comp%': round(score_comp, 2),
                'EMA5,20 Diff %': round(diff_5_20, 2), 'EMA20, 50 Diff %': round(diff_20_50, 2),
                'EMA50, 100 Diff %': round(diff_50_100, 2), '1M Max DD%': round(max_dd, 2), 'Liquidity(Cr)': round(liq / 10000000, 2)
            })
        except Exception as e:
            print(f"⚠️ Error processing {ticker}: {e}")
            continue
        
    df_final = pd.DataFrame(ranking_data)
    if df_final.empty: return
    
    # === [UPDATED FILE SAVING & LOGGING PHASE] ===
    # 🏎️ 1. SORT AND ARCHIVE PURE VELOCITY LEADERS (CSV + MARKDOWN)
    df_vel_sorted = df_final.sort_values(by='Score Vel%', ascending=False).copy()
    df_vel_sorted['Rank_Velocity'] = range(1, len(df_vel_sorted) + 1)
    
    # Save the standard raw data csv sheet
    df_vel_sorted.head(30).to_csv(f"history/velocity_{current_m_y}.csv", index=False)
    
    # ✅ NEW: Render and save a beautifully readable Top 30 Markdown report instantly
    columns_vel_md = ['Rank_Velocity', 'Ticker', 'Price', 'Score Vel%', 'EMA5,20 Diff %', '1M Max DD%']
    with open(f"history/velocity_{current_m_y}.md", "w") as f_vel:
        f_vel.write(f"# 🏎️ Top 30 Velocity Leaders Snapshot - {current_m_y.replace('_', ' ')}\n\n")
        f_vel.write(df_vel_sorted.head(30)[columns_vel_md].to_markdown(index=False))
    
    
    # 🏋️ 2. SORT AND ARCHIVE PURE COMPOUNDING LEADERS (CSV + MARKDOWN)
    df_comp_sorted = df_final.sort_values(by='Score Comp%', ascending=False).copy()
    df_comp_sorted['Rank_Compounding'] = range(1, len(df_comp_sorted) + 1)
    
    # Save the standard raw data csv sheet
    df_comp_sorted.head(30).to_csv(f"history/compounding_{current_m_y}.csv", index=False)
    
    # ✅ NEW: Render and save a beautifully readable Top 30 Markdown report instantly
    columns_comp_md = ['Rank_Compounding', 'Ticker', 'Price', 'Score Comp%', 'EMA20, 50 Diff %', 'EMA50, 100 Diff %', '1M Max DD%']
    with open(f"history/compounding_{current_m_y}.md", "w") as f_comp:
        f_comp.write(f"# 🏋️ Top 30 Compounding Leaders Snapshot - {current_m_y.replace('_', ' ')}\n\n")
        f_comp.write(df_comp_sorted.head(30)[columns_comp_md].to_markdown(index=False))

    # === [START OF THE REQUESTED ALLOCATION & COMMENTARY SECTION] ===
    # 💰 Dynamic uniquely-deduplicated allocation engine
    strat_budget = TOTAL_BUDGET / 2
    allocations = []
    
    # Bucket A: Pull the Top Velocity selections based on your target count parameters
    vel_picks = df_vel_sorted.head(STOCKS_COUNT).copy()
    for _, r in vel_picks.iterrows():
        qty = int((strat_budget / len(vel_picks)) // r['Price'])
        allocations.append({
            'Ticker': r['Ticker'], 
            'Strategy': 'Velocity', 
            'Price': r['Price'], 
            'Quantity': max(qty, 1)
        })
        
    # Bucket B: Pull the Top Compounding selections, STRICTLY skipping Basket A overlaps
    vel_tickers_list = vel_picks['Ticker'].tolist()
    comp_filtered = df_comp_sorted[~df_comp_sorted['Ticker'].isin(vel_tickers_list)].head(STOCKS_COUNT).copy()
    for _, r in comp_filtered.iterrows():
        qty = int((strat_budget / len(comp_filtered)) // r['Price'])
        allocations.append({
            'Ticker': r['Ticker'], 
            'Strategy': 'Compounding', 
            'Price': r['Price'], 
            'Quantity': max(qty, 1)
        })
        
    # Compile allocation profiles into a structured framework matrix
    df_alloc = pd.DataFrame(allocations)
    df_alloc.to_csv("zerodha_sip_basket.csv", index=False)
    
    # --- STEP 5: AUTOMATED LOOKBACK COMMENTARY MATRIX ---
    generate_markdown_report(current_m_y, df_alloc, df_final)

def generate_markdown_report(current_m_y, df_alloc, df_final):
    """
    Audits your live master portfolio inventory file. Batches all dropped stocks
    to pull a single combined yfinance download for high-speed, error-free diagnostics.
    """
    report = f"# 📝 Portfolio Re-Ranking Commentary Report ({current_m_y.replace('_', ' ')})\n\n"
    report += f"**Target Allocation Parameters:** Budget ₹{TOTAL_BUDGET:,.2f} | Strategy Split: {STOCKS_COUNT}+{STOCKS_COUNT} Unique Split\n\n"
    report += "## 🎯 Current Active Allocations For Your Fresh Zerodha Basket\n\n"
    report += df_alloc.to_markdown(index=False) + "\n\n"
    
    report += "## 🔍 Trend Audit & Dynamic Commentary Matrix\n"
    
    master_portfolio_file = "portfolio.csv"
    
    if os.path.exists(master_portfolio_file):
        try:
            df_master = pd.read_csv(master_portfolio_file, encoding='utf-8-sig')
            
            # Clean and flatten headers safely
            df_master.columns = [str(c).strip().lower() for c in df_master.columns]
            
            t_col = 'ticker' if 'ticker' in df_master.columns else df_master.columns[0]
            s_col = 'strategy' if 'strategy' in df_master.columns else df_master.columns[1]
            
            live_holdings = []
            for _, r in df_master.dropna(subset=[t_col]).iterrows():
                live_holdings.append({
                    'Ticker': str(r[t_col]).strip().upper(),
                    'Strategy': str(r[s_col]).strip()
                })
            
            report += f"Analyzing active stock positions directly from your master ledger (`{master_portfolio_file}`)...\n\n"
            
            df_final_clean = df_final.copy()
            df_final_clean.columns = [str(c).strip() for c in df_final_clean.columns]
            
            # STEP 1: PRE-IDENTIFY ALL DROPPED TICKERS FOR BATCH DOWNLOADING
            dropped_tickers_ns = []
            for asset in live_holdings:
                ticker = asset['Ticker']
                if ticker not in df_final_clean['Ticker'].values:
                    dropped_tickers_ns.append(f"{ticker}.NS")
            
            # BATCH BULK DOWNLOAD LAYER
            batch_diag_data = pd.DataFrame()
            if dropped_tickers_ns:
                print(f"📥 Batch-downloading metrics for {len(dropped_tickers_ns)} dropped portfolio assets...")
                batch_diag_data = yf.download(dropped_tickers_ns, period="1y", group_by='ticker', progress=False)
            
            # STEP 2: LOOP AND EVALUATE CRITERIA
            for asset in live_holdings:
                ticker = asset['Ticker']
                origin = asset['Strategy']
                ticker_ns = f"{ticker}.NS"
                
                # ✅ SCENARIO A: Stock passed all guardrails and is actively ranked
                if ticker in df_final_clean['Ticker'].values:
                    curr_row = df_final_clean[df_final_clean['Ticker'] == ticker].iloc[0]
                    
                    if origin.lower() == 'compounding':
                        df_sorted = df_final_clean.sort_values(by='Score Comp%', ascending=False)
                        curr_rank = df_sorted['Ticker'].tolist().index(ticker) + 1
                        curr_score = curr_row['Score Comp%']
                    else:
                        df_sorted = df_final_clean.sort_values(by='Score Vel%', ascending=False)
                        curr_rank = df_sorted['Ticker'].tolist().index(ticker) + 1
                        curr_score = curr_row['Score Vel%']
                    
                    prev_rank = "N/A"
                    delta_str = ""
                    
                    if os.path.exists('history'):
                        history_files = sorted([f for f in os.listdir('history') if f.startswith(f"{origin.lower()}_")])
                        if len(history_files) > 0:
                            df_hist_log = pd.read_csv(f"history/{history_files[-1]}", encoding='utf-8-sig')
                            df_hist_log.columns = [str(c).strip().lower() for c in df_hist_log.columns]
                            
                            # ✅ THE REPAIR: Force hist_t_col to resolve to a unique string name element instead of returning the entire index grid layout
                            hist_t_col = next((c for c in df_hist_log.columns if 'ticker' in c), df_hist_log.columns[0])
                            
                            # Safely convert column strings to uppercase for evaluation passes
                            df_hist_log[hist_t_col] = df_hist_log[hist_t_col].astype(str).str.strip().str.upper()
                            
                            if ticker in df_hist_log[hist_t_col].values:
                                target_rank_col = 'rank_compounding' if origin.lower() == 'compounding' else 'rank_velocity'
                                actual_rank_col = next((c for c in df_hist_log.columns if target_rank_col in c or 'rank' in c), None)
                                if actual_rank_col:
                                    match_row = df_hist_log[df_hist_log[hist_t_col] == ticker]
                                    prev_rank = int(match_row[actual_rank_col].values[0])
                                    delta = prev_rank - curr_rank
                                    delta_str = f" ({delta:+} positions)"
                    
                    is_outside_top30 = curr_rank > 30
                    report += f"### 🔹 {ticker} ({origin} Strategy)\n"
                    report += f"* **Current Status:** Price: ₹{curr_row['Price']:.2f} | Today's Strategy Score: {curr_score}% | Active Rank: #{curr_rank}{delta_str}\n"
                    
                    if is_outside_top30:
                        report += f"* ⚠️ **MOMENTUM SLIPPAGE ALERT:** This asset has slid down to **Rank #{curr_rank}**, dropping out of the Top 30 window. Velocity has decayed.\n"
                    elif delta_str and delta > 3:
                        report += "* 🚀 **Momentum Expansion:** Institutional velocity is accelerating month-over-month.\n"
                    elif delta_str and delta < -4:
                        report += "* 📉 **Momentum Cooling:** Trend velocity is compressing compared to last month.\n"
                    else:
                        report += "* 🟢 **Stable Tracking:** Maintaining clean, steady compounding geometric tracking.\n"
                        
                # 🚨 ✅ SCENARIO B: STOCK DROPPED. PROCESS DIAGNOSTICS FROM BATCH DATA
                else:
                    report += f"### ❌ {ticker} ({origin} Strategy) | **DANGER FLAG** 🛑\n"
                    report += f"* 🛑 **EMERGENCY SYSTEM DROP:** This asset was completely removed from the fresh investment ranking tables this month.\n"
                    
                    try:
                        has_ticker_data = False
                        diag_df = pd.DataFrame()
                        
                        if not batch_diag_data.empty:
                            if isinstance(batch_diag_data.columns, pd.MultiIndex):
                                if ticker_ns in batch_diag_data.columns.get_level_values(0):
                                    diag_df = batch_diag_data.xs(ticker_ns, axis=1, level=0).dropna()
                                    has_ticker_data = not diag_df.empty
                            else:
                                diag_df = batch_diag_data.dropna()
                                has_ticker_data = not diag_df.empty
                        
                        if has_ticker_data and 'Close' in diag_df.columns:
                            close_s = diag_df['Close'].squeeze()
                            vol_s = diag_df['Volume'].squeeze()

                            # 🌟 ADDED: RSI 21 Diagnostic Calculation Engine
                            delta = close_s.diff()
                            gain = delta.where(delta > 0, 0)
                            loss = -delta.where(delta < 0, 0)
                            avg_gain = gain.ewm(com=20, adjust=False).mean() # com = period - 1
                            avg_loss = loss.ewm(com=20, adjust=False).mean()
                            rsi21 = 100 - (100 / (1 + (avg_gain / avg_loss)))
                            cur_rsi21 = float(rsi21.iloc[-1].item() if hasattr(rsi21.iloc[-1], 'item') else rsi21.iloc[-1])
                            
                            ema5 = close_s.ewm(span=5, adjust=False).mean()
                            ema20 = close_s.ewm(span=20, adjust=False).mean()
                            ema50 = close_s.ewm(span=50, adjust=False).mean()
                            ema100 = close_s.ewm(span=100, adjust=False).mean()
                            ema200 = close_s.ewm(span=200, adjust=False).mean()
                            
                            val_5 = float(ema5.iloc[-1].item() if hasattr(ema5.iloc[-1], 'item') else ema5.iloc[-1])
                            val_20 = float(ema20.iloc[-1].item() if hasattr(ema20.iloc[-1], 'item') else ema20.iloc[-1])
                            val_50 = float(ema50.iloc[-1].item() if hasattr(ema50.iloc[-1], 'item') else ema50.iloc[-1])
                            val_100 = float(ema100.iloc[-1].item() if hasattr(ema100.iloc[-1], 'item') else ema100.iloc[-1])
                            val_200 = float(ema200.iloc[-1].item() if hasattr(ema200.iloc[-1], 'item') else ema200.iloc[-1])
                            
                            diff_5_20 = ((val_5 - val_20) / val_20) * 100
                            w1m = close_s.iloc[-21:]
                            max_dd = ((w1m.max() - w1m.min()) / w1m.max()) * 100
                            liq = float(close_s.iloc[-20:].mean()) * float(vol_s.iloc[-20:].mean())
                            
                            report += f"  * **Diagnostic Data Snapshot:** Current Price: ₹{close_s.iloc[-1]:.2f} | Short-Term Trend Gap: {diff_5_20:.2f}% | 1-Month Max Drawdown: {max_dd:.2f}%\n"
                            
                            if len(diag_df) < 200:
                                report += f"  * ❌ **Diagnostic Reason:** Stock has less than 200 days of active trading history on the NSE. Cannot compute macro-indicators safely.\n"
                            elif diff_5_20 < -1.0:
                                report += f"  * ❌ **Diagnostic Reason:** **SHORT-TERM TREND BREAKDOWN.** The 5 EMA has cracked below the 20 EMA past your strict **-1.0% Soft Buffer Threshold**. The stock is entering active short-term distribution/reversion.\n"
                            elif max_dd > 15.0:
                                report += f"  * ❌ **Diagnostic Reason:** **RISK WINDOW EXCEEDED.** The asset has crashed by **{max_dd:.2f}%** from its peak over the last 21 sessions, breaching your strict **15% Max Drawdown Ceiling**.\n"
                            elif liq <= 50000000:
                                report += f"  * ❌ **Diagnostic Reason:** **LIQUIDITY FAILURE.** Average daily turnover value over the last 20 days dropped below ₹5 Crore, breaching your execution liquidity floor.\n"
                            elif not (val_20 > val_50 > val_100 > val_200):
                                report += f"  * ❌ **Diagnostic Reason:** **MACRO TREND ROLLOVER.** The moving averages have lost their bullish structural stack configuration (`EMA 20 > 50 > 100 > 200`). Trend lines have flipped bearish or flattened.\n"
                            elif cur_rsi21 < 50.0:
                                report += f"  * ❌ **Diagnostic Reason:** **RSI 21 WEAKNESS.** The short-term momentum oscillator has dropped below the neutral 50.0 threshold, indicating a loss of buying pressure.\n"
                            else:
                                report += f"  * ❌ **Diagnostic Reason:** Stock was excluded due to an unclassified baseline rule filter.\n"
                        else:
                            report += f"  * ❌ **Diagnostic Reason:** Ticker shortcode mismatch. Asset code `{ticker_ns}` not found on yfinance NSE servers. Check for recent symbol renames or spelling typos.\n"
                    except Exception as diag_err:
                        report += f"  * ⚠️ Diagnostic parser execution error encountered: {diag_err}\n"
                
                report += "\n" + "-" * 80 + "\n"
        except Exception as e:
            report += f"\n⚠️ Error parsing master portfolio ledger configuration: {e}\n"
    else:
        report += "_Master portfolio ledger file (`portfolio.csv`) not found in root. Skipping commentary._\n"
        
    with open("commentary_report.md", "w") as f:
        f.write(report)

    print("\n📝 ======================================= GENERATED DIAGNOSTIC MARKDOWN REPORT PREVIEW =======================================")
    print(report)
    print("====================================================================================================================\n")


if __name__ == "__main__":
    # Create the required history subdirectory if missing from folder tree
    if not os.path.exists('history'): 
        os.makedirs('history')
# Usage format: python engine.py [BUDGET] [STOCKS_COUNT]
# Example: python engine.py 45000 6

    if len(sys.argv) >= 3:
        try:
            TOTAL_BUDGET = float(sys.argv[1])
            STOCKS_COUNT = int(sys.argv[2])
            print(f"✅ Parameters loaded from Terminal Arguments -> Budget: ₹{TOTAL_BUDGET:,.2f} | Unique Stocks/Strategy: {STOCKS_COUNT}")
        except ValueError:
            print("⚠️ Parameter parsing failed! Falling back to base defaults.")
            TOTAL_MONTHLY_SIP_BUDGET = 30000
            STOCKS_PER_STRATEGY = 5
    else:
        print("ℹ️ No command line arguments passed. Running with optimal strategy defaults.")
        TOTAL_BUDGET = 30000
        STOCKS_COUNT = 5

    run_analysis()
# === [END OF THE REQUESTED ALLOCATION & COMMENTARY SECTION] ===
