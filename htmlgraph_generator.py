import base64
import os
import webbrowser
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import matplotlib.dates as mdates
import config

#--- Helper for directory management ---
#config.ensure_local_directories()

# =====================================================================
# MODULE 1: INDEPENDENT ASSET CROSS VISUALIZER ENGINE
# =====================================================================
def generate_asset_cross_charts(ticker, source_dir, visuals_dir):
    """Loads price arrays, calculates technical indicators (MAs, MACD, Bollinger Bands),
    plots four completely distinct large-format charts, and saves them to disk.
    Returns the latest date string found in the pricing file.
    """
    file_path = os.path.join(source_dir, f"{ticker}.xlsx")
    ticker_clean = ticker.replace(".OL", "").replace(".ol", "").strip()

    if not os.path.exists(file_path):
        print(f"  [MISSING] Price data for {ticker} not found.")
        return "N/A"

    try:
        # Prevent multi-threaded charting memory leaks
        plt.close("all")

        # Handle header metadata skips
        raw_df = pd.read_excel(file_path, sheet_name="Sheet1", nrows=10, header=None)
        header_row_index = 0
        for i, row in raw_df.iterrows():
            row_str = " ".join([str(x) for x in row.values])
            if "Date" in row_str or "Close" in row_str or "Volume" in row_str:
                header_row_index = i
                break

        df = pd.read_excel(file_path, sheet_name="Sheet1", skiprows=header_row_index)
        df.columns = [str(c).strip() for c in df.columns]

        df.rename(columns={df.columns[0]: "Date"}, inplace=True)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", format="mixed")
        df.dropna(subset=["Date"], inplace=True)
        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)

        close_col = next((c for c in df.columns if "Close" in c), None)
        volume_col = next((c for c in df.columns if "Volume" in c), None)
        open_col = next((c for c in df.columns if "Open" in c), None)
        high_col = next((c for c in df.columns if "High" in c), None)
        low_col = next((c for c in df.columns if "Low" in c), None)

        if not close_col or len(df) < 50:
            print(f"  [SKIP] {ticker_clean} (Insufficient data rows for charting)")
            return "N/A"

        df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
        if volume_col:
            df[volume_col] = pd.to_numeric(df[volume_col], errors="coerce").fillna(0)
        if open_col:
            df[open_col] = pd.to_numeric(df[open_col], errors="coerce")
        if high_col:
            df[high_col] = pd.to_numeric(df[high_col], errors="coerce")
        if low_col:
            df[low_col] = pd.to_numeric(df[low_col], errors="coerce")

        # Technical Indicator Calculations
        df["MA20"] = df[close_col].rolling(window=20).mean()
        df["SMA50"] = df[close_col].rolling(window=50).mean()

        # Bollinger Bands (20-day SMA +/- 2 Standard Deviations)
        df["BB_Std"] = df[close_col].rolling(window=20).std()
        df["BB_Upper"] = df["MA20"] + (df["BB_Std"] * 2)
        df["BB_Lower"] = df["MA20"] - (df["BB_Std"] * 2)

        exp1 = df[close_col].ewm(span=12, adjust=False).mean()
        exp2 = df[close_col].ewm(span=26, adjust=False).mean()
        df["MACD"] = exp1 - exp2
        df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_Hist"] = df["MACD"] - df["Signal_Line"]

        # Crossover Signals
        ma_diff = df["MA20"] - df["SMA50"]
        df["MA_Prev_Diff"] = ma_diff.shift(1)
        ma_bear_cross = (ma_diff < 0) & (df["MA_Prev_Diff"] >= 0)
        ma_bull_cross = (ma_diff > 0) & (df["MA_Prev_Diff"] <= 0)

        macd_diff = df["MACD"] - df["Signal_Line"]
        df["MACD_Prev_Diff"] = macd_diff.shift(1)
        macd_bear_cross = (macd_diff < 0) & (df["MACD_Prev_Diff"] >= 0)
        macd_bull_cross = (macd_diff > 0) & (df["MACD_Prev_Diff"] <= 0)

        # Lookback Window Slices
        latest_date_dt = df.index[-1]
        six_months_ago = latest_date_dt - pd.DateOffset(months=6)

        p_df_6m = df[df.index >= six_months_ago]
        p_df_45 = df.tail(45)
        latest_date_str = latest_date_dt.strftime("%Y-%m-%d")

        # SYSTEM PLOTTING THEMING LOGIC
        def apply_dark_theme(fig, ax, is_45d=False):
            fig.patch.set_facecolor("#0b0c10")
            ax.set_facecolor("#151b24")
            ax.grid(True, color="#1f2833", linestyle=":", alpha=0.6)
            ax.tick_params(colors="white", labelsize=9)
            for s in ax.spines.values():
                s.set_color("#1f2833")

            # Control date density based on target timeline
            if is_45d:
                ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
            else:
                ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            fig.autofmt_xdate(rotation=25)

        # -----------------------------------------------------------------
        # CHART 1: OHLC CANDLESTICKS + BOLLINGER BANDS (6 MONTH - LARGE)
        # -----------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(12, 6.5))
        if open_col and high_col and low_col and close_col:
            candles_up = p_df_6m[close_col] >= p_df_6m[open_col]
            candles_down = p_df_6m[close_col] < p_df_6m[open_col]

            ax.vlines(p_df_6m.index[candles_up], p_df_6m[low_col][candles_up], p_df_6m[high_col][candles_up],
                      color="#4caf50", linewidth=1.2, alpha=0.8)
            ax.vlines(p_df_6m.index[candles_down], p_df_6m[low_col][candles_down], p_df_6m[high_col][candles_down],
                      color="#f44336", linewidth=1.2, alpha=0.8)
            ax.bar(p_df_6m.index[candles_up], p_df_6m[close_col][candles_up] - p_df_6m[open_col][candles_up],
                   bottom=p_df_6m[open_col][candles_up], color="#4caf50", width=0.6, alpha=0.8,
                   label="Price Action (Up)")
            ax.bar(p_df_6m.index[candles_down], p_df_6m[close_col][candles_down] - p_df_6m[open_col][candles_down],
                   bottom=p_df_6m[open_col][candles_down], color="#f44336", width=0.6, alpha=0.8,
                   label="Price Action (Down)")
        else:
            ax.plot(p_df_6m.index, p_df_6m[close_col], color="#ffffff", alpha=0.2, label="Price")

        ax.plot(p_df_6m.index, p_df_6m["BB_Upper"], color="#1da1f2", linestyle="--", linewidth=1.2, alpha=0.6,
                label="BB Upper (2σ)")
        ax.plot(p_df_6m.index, p_df_6m["BB_Lower"], color="#1da1f2", linestyle="--", linewidth=1.2, alpha=0.6,
                label="BB Lower (2σ)")
        ax.fill_between(p_df_6m.index, p_df_6m["BB_Lower"], p_df_6m["BB_Upper"], color="#1da1f2", alpha=0.03)

        apply_dark_theme(fig, ax)
        ax.legend(facecolor="#151b24", edgecolor="#1f2833", labelcolor="white", fontsize=9, loc="upper left")
        plt.tight_layout()
        plt.savefig(os.path.join(visuals_dir, f"{ticker_clean}_1_candles_bollinger.png"), facecolor=fig.get_facecolor(),
                    edgecolor="none", dpi=110)
        plt.close()

        # -----------------------------------------------------------------
        # CHART 2: MOVING AVERAGE CROSSOVER MATRIX (6 MONTH - LARGE)
        # -----------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(12, 6.5))
        ax.plot(p_df_6m.index, p_df_6m[close_col], color="#ffffff", alpha=0.7, linewidth=1.0, label="Price Line")
        ax.plot(p_df_6m.index, p_df_6m["MA20"], color="#66fcf1", linewidth=1.8, label="20 SMA Basis")
        ax.plot(p_df_6m.index, p_df_6m["SMA50"], color="#ffb300", linewidth=1.8, label="50 SMA Basis")

        mb_subset = df[ma_bear_cross & (df.index >= six_months_ago)]
        mbl_subset = df[ma_bull_cross & (df.index >= six_months_ago)]

        if not mb_subset.empty:
            ax.scatter(mb_subset.index, mb_subset["MA20"], color="#f44336", s=180, marker="v", zorder=5,
                       label="Bear Cross Vector")
        if not mbl_subset.empty:
            ax.scatter(mbl_subset.index, mbl_subset["MA20"], color="#4caf50", s=180, marker="^", zorder=5,
                       label="Bull Cross Vector")

        apply_dark_theme(fig, ax)
        h, l = ax.get_legend_handles_labels()
        bl = dict(zip(l, h))
        ax.legend(bl.values(), bl.keys(), facecolor="#151b24", edgecolor="#1f2833", labelcolor="white", fontsize=9,
                  loc="upper left")
        plt.tight_layout()
        plt.savefig(os.path.join(visuals_dir, f"{ticker_clean}_2_ma_cross.png"), facecolor=fig.get_facecolor(),
                    edgecolor="none", dpi=110)
        plt.close()

        # -----------------------------------------------------------------
        # CHART 3: MACD MOMENTUM PROFILE (6 MONTH - LARGE)
        # -----------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(12, 6.5))
        ax.plot(p_df_6m.index, p_df_6m["MACD"], color="#66fcf1", linewidth=1.8, label="MACD Line")
        ax.plot(p_df_6m.index, p_df_6m["Signal_Line"], color="#ff4545", linewidth=1.8, label="Signal Line")
        h_cols_6m = ["#4caf50" if x >= 0 else "#f44336" for x in p_df_6m["MACD_Hist"]]
        ax.bar(p_df_6m.index, p_df_6m["MACD_Hist"], color=h_cols_6m, alpha=0.35, width=0.6)

        mac_b_6m = df[macd_bear_cross & (df.index >= six_months_ago)]
        mac_bl_6m = df[macd_bull_cross & (df.index >= six_months_ago)]

        if not mac_b_6m.empty:
            ax.scatter(mac_b_6m.index, mac_b_6m["MACD"], color="#f44336", s=100, marker="o", zorder=6)
        if not mac_bl_6m.empty:
            ax.scatter(mac_bl_6m.index, mac_bl_6m["MACD"], color="#4caf50", s=100, marker="o", zorder=6)

        apply_dark_theme(fig, ax)
        ax.legend(facecolor="#151b24", edgecolor="#1f2833", labelcolor="white", fontsize=9, loc="upper left")
        plt.tight_layout()
        plt.savefig(os.path.join(visuals_dir, f"{ticker_clean}_3_macd_6m.png"), facecolor=fig.get_facecolor(),
                    edgecolor="none", dpi=110)
        plt.close()

        # -----------------------------------------------------------------
        # CHART 4: MACD & VOLUME PANEL MATRIX (45 DAY - SEPARATE STACKED)
        # -----------------------------------------------------------------
        fig, (ax_macd, ax_vol) = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True,
                                              gridspec_kw={'height_ratios': [3.2, 1.8]})

        ax_macd.plot(p_df_45.index, p_df_45["MACD"], color="#66fcf1", linewidth=1.8, label="MACD Line")
        ax_macd.plot(p_df_45.index, p_df_45["Signal_Line"], color="#ff4545", linewidth=1.8, label="Signal Line")
        h_cols_45 = ["#4caf50" if x >= 0 else "#f44336" for x in p_df_45["MACD_Hist"]]
        ax_macd.bar(p_df_45.index, p_df_45["MACD_Hist"], color=h_cols_45, alpha=0.35, width=0.6)

        mac_b_45 = df[macd_bear_cross & (df.index >= p_df_45.index[0])]
        mac_bl_45 = df[macd_bull_cross & (df.index >= p_df_45.index[0])]

        if not mac_b_45.empty:
            ax_macd.scatter(mac_b_45.index, mac_b_45["MACD"], color="#f44336", s=100, marker="o", zorder=6)
        if not mac_bl_45.empty:
            ax_macd.scatter(mac_bl_45.index, mac_bl_45["MACD"], color="#4caf50", s=100, marker="o", zorder=6)

        if volume_col and volume_col in p_df_45.columns:
            if open_col and open_col in p_df_45.columns:
                v_cols = ["#4caf50" if close >= op else "#f44336" for close, op in
                          zip(p_df_45[close_col], p_df_45[open_col])]
            else:
                v_cols = ["#4caf50" if chg >= 0 else "#f44336" for chg in p_df_45[close_col].diff().fillna(0)]
            ax_vol.bar(p_df_45.index, p_df_45[volume_col], color=v_cols, alpha=0.45, width=0.6, zorder=3)

        # Apply dense date tracking to both panels in Chart 4
        apply_dark_theme(fig, ax_macd, is_45d=True)
        apply_dark_theme(fig, ax_vol, is_45d=True)

        ax_macd.legend(facecolor="#151b24", edgecolor="#1f2833", labelcolor="white", fontsize=9, loc="upper left")
        ax_vol.text(0.01, 0.85, "Volume Horizon", transform=ax_vol.transAxes, color="#66fcf1", fontsize=9,
                    weight="bold", alpha=0.8, va="top")

        plt.tight_layout()
        fig.subplots_adjust(hspace=0.08)
        plt.savefig(os.path.join(visuals_dir, f"{ticker_clean}_4_macd_vol_45d.png"), facecolor=fig.get_facecolor(),
                    edgecolor="none", dpi=110)
        plt.close()

        print(f"  [OK] Four discrete chart properties compiled for {ticker_clean}.")
        return latest_date_str

    except Exception as e:
        print(f"  [ERROR] Failed rendering structural viewgraphs for {ticker}: {e}")
        return "N/A"


# =====================================================================
# MODULE 2: DYNAMIC DASHBOARD MATRIX COMPILER (VIEWGRAPH SPLIT)
# =====================================================================
def compile_visual_dashboard():
    print(f"Initializing Visual Dashboard Matrix Compiler...")
    source_dir = config.OSLOBORS_DIR
    visuals_dir = config.GRAPHS_DIR

    if not os.path.exists(config.TECHNICAL_FILE):
        print(f"[ERROR] Technical reference file missing: {config.TECHNICAL_FILE}")
        return

    df = pd.read_excel(config.TECHNICAL_FILE, engine="openpyxl")
    os.makedirs(visuals_dir, exist_ok=True)

    for _, row in df.iterrows():
        ticker = row.get("Ticker", "N/A")
        ticker_display = str(ticker).replace(".OL", "").replace(".ol", "").strip()
        latest_date = generate_asset_cross_charts(ticker, source_dir, visuals_dir)

        if not latest_date:
            latest_date = "N/A"

        img_tags = []
        suffixes = ["1_candles_bollinger", "2_ma_cross", "3_macd_6m", "4_macd_vol_45d"]

        for suffix in suffixes:
            target_path = os.path.join(visuals_dir, f"{ticker_display}_{suffix}.png")
            if os.path.exists(target_path):
                with open(target_path, "rb") as img_f:
                    b64 = base64.b64encode(img_f.read()).decode("utf-8")
                img_tags.append(f'<img src="data:image/png;base64,{b64}" class="viewgraph-large-frame">')
            else:
                img_tags.append('<div class="blank-chart">Chart Asset Unavailable</div>')

        category = str(row.get("Category", "N/A")).strip()
        price = row.get("Price", 0.0)
        sma20 = row.get("20 SMA Status", "N/A")
        sma50 = row.get("50 SMA Status", "N/A")
        sma200 = row.get("200 SMA Status", "N/A")

        sma20_chg = str(row.get("20 SMA Changed", "N/A")).split()[0]
        sma50_chg = str(row.get("50 SMA Changed", "N/A")).split()[0]
        sma200_chg = str(row.get("200 SMA Changed", "N/A")).split()[0]

        sma20_class = "green-badge" if sma20 == "ABOVE" else "red-badge"
        sma50_class = "green-badge" if sma50 == "ABOVE" else "red-badge"
        sma200_class = "green-badge" if sma200 == "ABOVE" else "red-badge"

        dashboard_content = f"""
        <div class="main-layout-container">
            <div class="col-profile-pane">
                <strong class="ticker-text">{ticker_display}</strong>
                <span class="category-text">{category}</span>
                <div class="price-value">{price:,.2f} NOK</div>
                <div class="price-date">Date: {latest_date}</div>

                <div class="sma-group-container">
                    <div class="sma-block">
                        <span class="sma-label">20 SMA Target</span>
                        <span class="badge {sma20_class}">{sma20}</span>
                        <div class="date-subtext">{sma20_chg}</div>
                    </div>
                    <div class="sma-block">
                        <span class="sma-label">50 SMA Target</span>
                        <span class="badge {sma50_class}">{sma50}</span>
                        <div class="date-subtext">{sma50_chg}</div>
                    </div>
                    <div class="sma-block">
                        <span class="sma-label">200 SMA Target</span>
                        <span class="badge {sma200_class}">{sma200}</span>
                        <div class="date-subtext">{sma200_chg}</div>
                    </div>
                </div>
            </div>

            <div class="visuals-matrix-pane">
                <div class="chart-box">
                    <div class="chart-header">1. OHLC Candlesticks & Bollinger Bands Channel (6m Horizon)</div>
                    {img_tags[0]}
                </div>
                <div class="chart-box">
                    <div class="chart-header">2. 20 / 50 SMA Structural Trend Crossover Vectors (6m Horizon)</div>
                    {img_tags[1]}
                </div>
                <div class="chart-box">
                    <div class="chart-header">3. MACD Momentum Crossover Profiles (6m Horizon)</div>
                    {img_tags[2]}
                </div>
                <div class="chart-box">
                    <div class="chart-header">4. MACD Momentum Lines & Standalone Volume Subplots (45d Window)</div>
                    {img_tags[3]}
                </div>
            </div>
        </div>
        """

        html_template = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>{ticker_display} - Technical Viewgraph</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background-color: #0b0c10;
                    color: #c5c6c7;
                    padding: 25px;
                    margin: 0;
                }}
                .wrapper {{ max-width: 1500px; margin: 0 auto; }}
                .header {{ border-bottom: 1px solid #1f2833; padding-bottom: 15px; margin-bottom: 25px; }}
                h2 {{ color: #ffffff; margin: 0 0 5px 0; font-size: 24px; }}
                .subtitle {{ color: #66fcf1; margin: 0; font-size: 13px; font-weight: 500; }}

                .main-layout-container {{
                    display: flex;
                    gap: 25px;
                    background-color: #1f2833;
                    border-radius: 8px;
                    padding: 25px;
                    box-shadow: 0 8px 24px rgba(0,0,0,0.6);
                }}

                .col-profile-pane {{ 
                    width: 220px; 
                    flex-shrink: 0;
                    background-color: #151b24;
                    padding: 20px;
                    border-radius: 6px;
                    height: fit-content;
                    box-sizing: border-box;
                }}

                .visuals-matrix-pane {{
                    display: flex;
                    flex-direction: column;
                    gap: 30px;
                    flex-grow: 1;
                }}

                .chart-box {{
                    background-color: #151b24;
                    border-radius: 6px;
                    padding: 20px;
                }}

                .chart-header {{
                    color: #66fcf1;
                    font-size: 11px;
                    text-transform: capitalize;
                    letter-spacing: 1.2px;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #0b0c10;
                    margin-bottom: 15px;
                    font-weight: bold;
                }}

                .ticker-text {{ color: #ffffff; font-size: 22px; display: block; letter-spacing: -0.5px; }}
                .category-text {{ font-size: 12px; color: #b0b3b8; display: block; margin-top: 4px; }}
                .price-value {{ font-family: monospace; font-weight: bold; color: #ffffff; font-size: 18px; margin-top: 12px; }}
                .price-date {{ font-size: 11px; color: #858585; margin-top: 4px; font-family: monospace; }}

                .viewgraph-large-frame {{ width: 100%; height: auto; display: block; border-radius: 4px; }}
                .blank-chart {{ display: block; padding: 60px 0; font-style: italic; color: #858585; font-size: 12px; text-align: center; }}

                .sma-group-container {{ display: flex; flex-direction: column; gap: 14px; margin-top: 25px; }}
                .sma-block {{ display: flex; flex-direction: column; align-items: flex-start; }}
                .sma-label {{ font-size: 10px; color: #757575; margin-bottom: 4px; font-weight: 500; }}
                .badge {{ display: inline-block; padding: 3px 6px; font-size: 10px; font-weight: bold; text-align: center; min-width: 60px; border-radius: 3px; }}

                .green-badge {{ background-color: rgba(76,175,80,0.13); color: #4caf50; border: 1px solid rgba(76,175,80,0.2); }}
                .red-badge {{ background-color: rgba(244,67,54,0.13); color: #f44336; border: 1px solid rgba(244,67,54,0.2); }}
                .date-subtext {{ font-size: 9px; color: #757575; margin-top: 4px; font-family: monospace; }}
            </style>
        </head>
        <body>
            <div class="wrapper">
                <div class="header">
                    <h2>{ticker_display} - OlaiProject</h2>
                    <p class="subtitle">Simple Graph (Daily)</p>
                </div>
                {dashboard_content}
            </div>
        </body>
        </html>
        """

        individual_filename = f"{ticker_display}_viewgraph.html"
        html_output_path = os.path.join(visuals_dir, individual_filename)

        with open(html_output_path, "w", encoding="utf-8") as f:
            f.write(html_template)

        print(f"  [HTML] Compiled {individual_filename} -> {html_output_path}")

    print(f"\n[SUCCESS] UI files compiled to: {html_output_path}")

# =====================================================================
# ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    compile_visual_dashboard()