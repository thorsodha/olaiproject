import os
import base64
import pandas as pd
import config

# --- REQUIRED FOR DOCKER ---
import matplotlib
matplotlib.use('Agg')  # Forces headless background rendering
import matplotlib.pyplot as plt
# ---------------------------

# =====================================================================
# MODULE 1: INDEPENDENT ASSET CROSS VISUALIZER ENGINE
# =====================================================================
def generate_asset_cross_charts(ticker):
    """
    Loads price arrays, calculates structural inflection thresholds, plots
    moving average intersections + MACD divergence histograms, and saves high-res
    matrix assets natively into your target system folder.
    Returns the latest date string found in the pricing file.
    """
    file_path = os.path.join(config.OSLOBORS_DIR, f"{ticker}.xlsx")
    ticker_clean = ticker.replace(".OL", "").replace(".ol", "").strip()

    if not os.path.exists(file_path):
        print(f"  [MISSING] Price data for {ticker} not found. Skipping charts.")
        return "N/A"

    try:
        # Avoid multi-threaded charting overflows
        plt.close("all")

        # Handle header metadata skips
        raw_df = pd.read_excel(file_path, sheet_name="Sheet1", nrows=10, header=None)
        header_row_index = 0
        for i, row in raw_df.iterrows():
            row_str = " ".join([str(x) for x in row.values])
            if "Date" in row_str or "Close" in row_str:
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
        if not close_col or len(df) < 50:
            print(f"  [SKIP] {ticker_clean} (Insufficient data rows for charting)")
            return "N/A"

        df[close_col] = pd.to_numeric(df[close_col], errors="coerce")

        # Math Indicator Layers
        df["MA20"] = df[close_col].rolling(window=20).mean()
        df["SMA50"] = df[close_col].rolling(window=50).mean()

        exp1 = df[close_col].ewm(span=12, adjust=False).mean()
        exp2 = df[close_col].ewm(span=26, adjust=False).mean()
        df["MACD"] = exp1 - exp2
        df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_Hist"] = df["MACD"] - df["Signal_Line"]

        # Track cross variations using directional vector shift changes
        ma_diff = df["MA20"] - df["SMA50"]
        df["MA_Prev_Diff"] = ma_diff.shift(1)
        ma_bear_cross = (ma_diff < 0) & (df["MA_Prev_Diff"] >= 0)
        ma_bull_cross = (ma_diff > 0) & (df["MA_Prev_Diff"] <= 0)

        macd_diff = df["MACD"] - df["Signal_Line"]
        df["MACD_Prev_Diff"] = macd_diff.shift(1)
        macd_bear_cross = (macd_diff < 0) & (df["MACD_Prev_Diff"] >= 0)
        macd_bull_cross = (macd_diff > 0) & (df["MACD_Prev_Diff"] <= 0)

        # Timeframe slices (Window 1 is 6-month lookback | Window 2 is 45 days)
        latest_date_dt = df.index[-1]
        six_months_ago = latest_date_dt - pd.DateOffset(months=6)

        p_df_6m = df[df.index >= six_months_ago]
        p_df_45 = df.tail(45)

        latest_date_str = latest_date_dt.strftime("%Y-%m-%d")

        # -----------------------------------------------------------------
        # PLOT A: MOVING AVERAGE TREND CONVERGENCE (6 MONTH)
        # -----------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(p_df_6m.index, p_df_6m[close_col], color="#ffffff", alpha=0.2, label="Price")
        ax.plot(p_df_6m.index, p_df_6m["MA20"], color="#66fcf1", linewidth=1.6, label="20 SMA")
        ax.plot(p_df_6m.index, p_df_6m["SMA50"], color="#ffb300", linewidth=1.6, label="50 SMA")

        ma_bears_all = df[ma_bear_cross]
        ma_bulls_all = df[ma_bull_cross]
        mb_subset = ma_bears_all[ma_bears_all.index.isin(p_df_6m.index)]
        mbl_subset = ma_bulls_all[ma_bulls_all.index.isin(p_df_6m.index)]

        if not mb_subset.empty:
            ax.scatter(mb_subset.index, mb_subset["MA20"], color="#f44336", s=140, marker="v", zorder=5, label="Bear Cross")
        if not mbl_subset.empty:
            ax.scatter(mbl_subset.index, mbl_subset["MA20"], color="#4caf50", s=140, marker="^", zorder=5, label="Bull Cross")

        fig.patch.set_facecolor("#0b0c10")
        ax.set_facecolor("#151b24")
        ax.grid(True, color="#1f2833", linestyle=":", alpha=0.6)
        ax.tick_params(colors="white", labelsize=9)
        for s in ax.spines.values():
            s.set_color("#1f2833")
        h, l = ax.get_legend_handles_labels()
        bl = dict(zip(l, h))
        ax.legend(bl.values(), bl.keys(), facecolor="#151b24", edgecolor="#1f2833", labelcolor="white", fontsize=8)

        plt.tight_layout()
        ma_path = os.path.join(config.GRAPHS_DIR, f"{ticker_clean}_ma_cross.png")
        plt.savefig(ma_path, facecolor=fig.get_facecolor(), edgecolor="none", dpi=110)
        plt.close()

        # -----------------------------------------------------------------
        # PLOT B: MACD INTERSECTIONS (6 MONTH)
        # -----------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(p_df_6m.index, p_df_6m["MACD"], color="#66fcf1", linewidth=1.5, label="MACD")
        ax.plot(p_df_6m.index, p_df_6m["Signal_Line"], color="#ff4545", linewidth=1.5, label="Signal")

        h_cols_6m = ["#4caf50" if x >= 0 else "#f44336" for x in p_df_6m["MACD_Hist"]]
        ax.bar(p_df_6m.index, p_df_6m["MACD_Hist"], color=h_cols_6m, alpha=0.3, width=0.6)

        macd_bears_all = df[macd_bear_cross]
        macd_bulls_all = df[macd_bull_cross]
        mac_b_6m = macd_bears_all[macd_bears_all.index.isin(p_df_6m.index)]
        mac_bl_6m = macd_bulls_all[macd_bulls_all.index.isin(p_df_6m.index)]

        if not mac_b_6m.empty:
            ax.scatter(mac_b_6m.index, mac_b_6m["MACD"], color="#f44336", s=80, marker="o", zorder=6)
        if not mac_bl_6m.empty:
            ax.scatter(mac_bl_6m.index, mac_bl_6m["MACD"], color="#4caf50", s=80, marker="o", zorder=6)

        fig.patch.set_facecolor("#0b0c10")
        ax.set_facecolor("#151b24")
        ax.grid(True, color="#1f2833", linestyle=":", alpha=0.6)
        ax.tick_params(colors="white", labelsize=9)
        for s in ax.spines.values():
            s.set_color("#1f2833")
        h, l = ax.get_legend_handles_labels()
        bl = dict(zip(l, h))
        ax.legend(bl.values(), bl.keys(), facecolor="#151b24", edgecolor="#1f2833", labelcolor="white", fontsize=8)

        plt.tight_layout()
        macd_path = os.path.join(config.GRAPHS_DIR, f"{ticker_clean}_macd_cross.png")
        plt.savefig(macd_path, facecolor=fig.get_facecolor(), edgecolor="none", dpi=110)
        plt.close()

        # -----------------------------------------------------------------
        # PLOT C: MACD INTERSECTIONS (45 DAY WIDE)
        # -----------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(13, 4.5))
        ax.plot(p_df_45.index, p_df_45["MACD"], color="#66fcf1", linewidth=1.5, label="MACD")
        ax.plot(p_df_45.index, p_df_45["Signal_Line"], color="#ff4545", linewidth=1.5, label="Signal")

        h_cols_45 = ["#4caf50" if x >= 0 else "#f44336" for x in p_df_45["MACD_Hist"]]
        ax.bar(p_df_45.index, p_df_45["MACD_Hist"], color=h_cols_45, alpha=0.3, width=0.6)

        mac_b_45 = macd_bears_all[macd_bears_all.index.isin(p_df_45.index)]
        mac_bl_45 = macd_bulls_all[macd_bulls_all.index.isin(p_df_45.index)]

        if not mac_b_45.empty:
            ax.scatter(mac_b_45.index, mac_b_45["MACD"], color="#f44336", s=80, marker="o", zorder=6)
        if not mac_bl_45.empty:
            ax.scatter(mac_bl_45.index, mac_bl_45["MACD"], color="#4caf50", s=80, marker="o", zorder=6)

        fig.patch.set_facecolor("#0b0c10")
        ax.set_facecolor("#151b24")
        ax.grid(True, color="#1f2833", linestyle=":", alpha=0.6)
        ax.tick_params(colors="white", labelsize=9)
        for s in ax.spines.values():
            s.set_color("#1f2833")
        h, l = ax.get_legend_handles_labels()
        bl = dict(zip(l, h))
        ax.legend(bl.values(), bl.keys(), facecolor="#151b24", edgecolor="#1f2833", labelcolor="white", fontsize=8)

        plt.tight_layout()
        macd_45_path = os.path.join(config.GRAPHS_DIR, f"{ticker_clean}_macd_cross_45.png")
        plt.savefig(macd_45_path, facecolor=fig.get_facecolor(), edgecolor="none", dpi=110)
        plt.close()

        print(f"  [OK] Charts compiled for {ticker_clean}.")
        return latest_date_str

    except Exception as e:
        print(f"  [ERROR] Failed rendering crossover charts for {ticker}: {e}")
        return "N/A"


# =====================================================================
# MODULE 2: DYNAMIC DASHBOARD MATRIX COMPILER
# =====================================================================
def generate_dashboard(excel_path=None, output_path=None):
    """
    Main hook for the pipeline. Uses config paths if not explicitly passed.
    """
    if excel_path is None:
        excel_path = config.TECHNICAL_FILE
    if output_path is None:
        output_path = config.DASHBOARD_FILE

    print(f"Initializing Visual Dashboard Matrix Compiler...")

    if not os.path.exists(excel_path):
        print(f"[ERROR] Technical reference spreadsheet missing at: {excel_path}")
        return False

    os.makedirs(config.GRAPHS_DIR, exist_ok=True)

    try:
        df = pd.read_excel(excel_path, engine="openpyxl")
    except Exception as e:
        print(f"[ERROR] Failed reading {excel_path}: {e}")
        return False

    rows_html = ""

    for _, row in df.iterrows():
        ticker = row.get("Ticker", "N/A")
        ticker_display = str(ticker).replace(".OL", "").replace(".ol", "").strip()

        # 1. Trigger visualizer and extract the true price endpoint timestamp
        latest_date = generate_asset_cross_charts(ticker)
        if not latest_date:
            latest_date = "N/A"

        # 2. Extract and convert generated plots into Base64 strings
        ma_img_html = '<span class="blank-chart">No MA Plot Available</span>'
        macd_img_html = '<span class="blank-chart">No MACD 6m Plot Available</span>'
        macd_45_img_html = '<span class="blank-chart">No MACD 45 Plot Available</span>'

        ma_plot_file = os.path.join(config.GRAPHS_DIR, f"{ticker_display}_ma_cross.png")
        macd_plot_file = os.path.join(config.GRAPHS_DIR, f"{ticker_display}_macd_cross.png")
        macd_45_plot_file = os.path.join(config.GRAPHS_DIR, f"{ticker_display}_macd_cross_45.png")

        if os.path.exists(ma_plot_file):
            with open(ma_plot_file, "rb") as img:
                ma_base64 = base64.b64encode(img.read()).decode("utf-8")
                ma_img_html = f'<img src="data:image/png;base64,{ma_base64}" class="cross-panel-img-narrow" alt="MA Chart">'

        if os.path.exists(macd_plot_file):
            with open(macd_plot_file, "rb") as img:
                macd_base64 = base64.b64encode(img.read()).decode("utf-8")
                macd_img_html = f'<img src="data:image/png;base64,{macd_base64}" class="cross-panel-img-narrow" alt="MACD 6m Chart">'

        if os.path.exists(macd_45_plot_file):
            with open(macd_45_plot_file, "rb") as img:
                macd_45_base64 = base64.b64encode(img.read()).decode("utf-8")
                macd_45_img_html = f'<img src="data:image/png;base64,{macd_45_base64}" class="cross-panel-img-wide" alt="MACD 45 Chart">'

        # 3. Pull metrics data for left side information block
        category = str(row.get("Category", "N/A")).strip()
        price = row.get("Price", 0.0)
        sma20 = row.get("20 SMA Status", "N/A")
        sma50 = row.get("50 SMA Status", "N/A")
        sma200 = row.get("200 SMA Status", "N/A")

        sma20_chg = str(row.get("20 SMA Changed", "N/A")).split()[0]
        sma50_chg = str(row.get("50 SMA Changed", "N/A")).split()[0]
        sma200_chg = str(row.get("200 SMA Changed", "N/A")).split()[0]

        sma20_class = "green-badge-left" if sma20 == "ABOVE" else "red-badge-left"
        sma50_class = "green-badge-middle" if sma50 == "ABOVE" else "red-badge-middle"
        sma200_class = "green-badge-right" if sma200 == "ABOVE" else "red-badge-right"

        # Build structural row matrix
        rows_html += f"""
        <tr>
            <td class="col-profile-pane">
                <strong class="ticker-text">{ticker_display}</strong>
                <span class="category-text">{category}</span>
                <div class="price-value">{price:,.2f} NOK</div>
                <div class="price-date">Date: {latest_date}</div>

                <div class="sma-group-container">
                    <div class="sma-block">
                        <span class="sma-label">20 SMA</span>
                        <span class="badge {sma20_class}">{sma20}</span>
                        <div class="date-subtext">{sma20_chg}</div>
                    </div>
                    <div class="sma-block">
                        <span class="sma-label" style="padding-left:2px;">50 SMA</span>
                        <span class="badge {sma50_class}">{sma50}</span>
                        <div class="date-subtext" style="padding-left:2px;">{sma50_chg}</div>
                    </div>
                    <div class="sma-block">
                        <span class="sma-label" style="padding-left:2px;">200 SMA</span>
                        <span class="badge {sma200_class}">{sma200}</span>
                        <div class="date-subtext" style="padding-left:2px;">{sma200_chg}</div>
                    </div>
                </div>
            </td>
            <td>{ma_img_html}</td>
            <td>{macd_img_html}</td>
            <td>{macd_45_img_html}</td>
        </tr>
        """

    # HTML Layout Template Configuration
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Technical Cross Matrix Portal</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: #0b0c10;
                color: #c5c6c7;
                padding: 25px;
                margin: 0;
            }}
            .wrapper {{ max-width: 1920px; margin: 0 auto; }}
            .header {{
                border-bottom: 1px solid #1f2833;
                padding-bottom: 15px;
                margin-bottom: 25px;
            }}
            h2 {{ color: #ffffff; margin: 0 0 5px 0; font-size: 24px; }}
            .subtitle {{ color: #66fcf1; margin: 0; font-size: 13px; font-weight: 500; }}

            table {{
                border-collapse: collapse;
                width: 100%;
                background-color: #1f2833;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 8px 24px rgba(0,0,0,0.6);
                table-layout: fixed;
            }}
            th, td {{ padding: 10px 8px; text-align: left; vertical-align: top; }}
            th {{
                background-color: #151b24;
                color: #66fcf1;
                font-size: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
                border-bottom: 2px solid #0b0c10;
            }}

            /* Sizing Layout for asymmetric grid alignment */
            th:nth-child(1), td:nth-child(1) {{ width: 190px; }}                    /* Profile Side-Panel */
            th:nth-child(2), td:nth-child(2) {{ width: 450px; text-align: center; }} /* Narrow SMA 6m */
            th:nth-child(3), td:nth-child(3) {{ width: 450px; text-align: center; }} /* Narrow MACD 6m */
            th:nth-child(4), td:nth-child(4) {{ width: 790px; text-align: center; }} /* Extra-Wide MACD 45d */

            /* Compact first column styles */
            .col-profile-pane {{
                vertical-align: middle;
            }}
            .ticker-text {{
                color: #ffffff; 
                font-size: 14px; 
                display: block;
                letter-spacing: -0.2px;
            }}
            .category-text {{
                font-size: 10px; 
                color: #b0b3b8;
                display: block;
                margin-top: 1px;
            }}
            .price-value {{
                font-family: monospace; 
                font-weight: bold; 
                color: #ffffff;
                font-size: 13px;
                margin-top: 6px;
            }}
            .price-date {{
                font-size: 9px;
                color: #858585;
                margin-top: 1px;
                font-family: monospace;
            }}

            /* Asymmetric HTML Chart rendering properties */
            .cross-panel-img-narrow {{
                width: 440px;
                height: auto;
                display: block;
                margin: 0 auto;
                border-radius: 4px;
                filter: brightness(1.08) contrast(1.02);
            }}
            .cross-panel-img-wide {{
                width: 775px;
                height: auto;
                display: block;
                margin: 0 auto;
                border-radius: 4px;
                filter: brightness(1.08) contrast(1.02);
            }}

            .blank-chart {{
                display: block;
                padding: 40px 0;
                font-style: italic;
                color: #858585;
                font-size: 11px;
            }}

            tr {{ border-bottom: 1px solid #0b0c10; transition: background 0.1s; }}
            tr:hover {{ background-color: #243342; }}

            /* Compact SMA structure styles */
            .sma-group-container {{ display: flex; gap: 0px; margin-top: 10px; }}
            .sma-block {{ display: flex; flex-direction: column; align-items: flex-start; }}
            .sma-label {{ font-size: 9px; color: #757575; margin-bottom: 2px; font-weight: 500; }}
            .badge {{ display: inline-block; padding: 2px 4px; font-size: 9px; font-weight: bold; text-align: center; min-width: 42px; }}

            .green-badge-left {{ background-color: rgba(76,175,80,0.13); color: #4caf50; border: 1px solid rgba(76,175,80,0.2); border-right: none; border-radius: 3px 0 0 3px; }}
            .red-badge-left {{ background-color: rgba(244,67,54,0.13); color: #f44336; border: 1px solid rgba(244,67,54,0.2); border-right: none; border-radius: 3px 0 0 3px; }}
            .green-badge-middle {{ background-color: rgba(76,175,80,0.13); color: #4caf50; border: 1px solid rgba(76,175,80,0.2); border-right: none; }}
            .red-badge-middle {{ background-color: rgba(244,67,54,0.13); color: #f44336; border: 1px solid rgba(244,67,54,0.2); border-right: none; }}
            .green-badge-right {{ background-color: rgba(76,175,80,0.13); color: #4caf50; border: 1px solid rgba(76,175,80,0.2); border-radius: 0 3px 3px 0; }}
            .red-badge-right {{ background-color: rgba(244,67,54,0.13); color: #f44336; border: 1px solid rgba(244,67,54,0.2); border-radius: 0 3px 3px 0; }}

            .date-subtext {{ font-size: 8px; color: #757575; margin-top: 2px; font-family: monospace; }}
        </style>
    </head>
    <body>
        <div class="wrapper">
            <div class="header">
                <h2> Oslo Børs - Crossover Signal Matrix</h2>
                <p class="subtitle">OlaiProject Automated Visualizer</p>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Asset & Moving Averages</th>
                        <th>20 / 50 SMA Cross Vector (6m)</th>
                        <th>MACD Signal Cross Profile (6m)</th>
                        <th>MACD Signal Cross Profile (45d)</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)

    print(f"\n[SUCCESS] Matrix UI compiled and updated at: {output_path}")
    return True

if __name__ == "__main__":
    generate_dashboard()