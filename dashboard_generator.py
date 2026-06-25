import base64
import os
import pandas as pd
import config
from datetime import datetime


def get_latest_monthly_news(ticker_display, news_files, newsweb_dir):
    matched_file = next(
        (f for f in news_files if ticker_display.lower() in f.lower()),
        None
    )
    if not matched_file:
        return None
    try:
        file_path = os.path.join(newsweb_dir, matched_file)
        monthly_df = pd.read_excel(file_path, sheet_name="Monthly Analysis", engine="openpyxl")
        if monthly_df.empty or "YearMonth" not in monthly_df.columns:
            return None
        monthly_df = monthly_df.dropna(subset=["YearMonth"]).sort_values("YearMonth")
        if monthly_df.empty:
            return None
        latest = monthly_df.iloc[-1]
        raw_year_month = str(latest.get("YearMonth", "N/A"))
        try:
            month_label = pd.to_datetime(raw_year_month + "-01").strftime("%B")
        except Exception:
            month_label = raw_year_month

        return {
            "year_month": month_label,
            "summary": str(latest.get("Monthly_Summary", "")).strip(),
            "sentiment": latest.get("Sentiment_Score", None),
        }

    except Exception as news_err:
        print(f"[WARNING] NewsBank lookup failed for {ticker_display}: {news_err}")
        return None


def generate_dashboard(excel_path, output_path="matrix_dashboard.html"):
    """
    Reads technical analysis data, pairs it with local asset metrics,
    and builds a self-contained HTML matrix screen.
    """
    last_updated = datetime.now().strftime("%d %b %Y %H:%M")

    print(f"Initializing Dashboard Engine using Excel data from: {excel_path}...")

    if not os.path.exists(excel_path):
        print(f"[ERROR] System could not find Excel file at: '{excel_path}'")
        return False

    try:
        df = pd.read_excel(excel_path, engine="openpyxl")
    except Exception as e:
        print(f"[ERROR] Failed to read Excel file. Details: {e}")
        return False

    if "MACD Hist Prev" not in df.columns and "MACD Hist" in df.columns:
        df["MACD Hist Prev"] = df["MACD Hist"].shift(1)

    # --- ADJUSTED CONFIGURATION PATHS ---
    # Replaced the legacy if/else block to leverage our unified system variables
    visuals_dir = config.SPARKLINES_DIR
    deepdives_route = "/visuals/graphs"
    newsweb_dir = config.NEWSWEB_DIR  # NEW

    news_files = []  # NEW block
    if os.path.exists(newsweb_dir):
        try:
            news_files = [f for f in os.listdir(newsweb_dir) if f.lower().endswith(".xlsx")]
        except Exception as e:
            print(f"[WARNING] Could not list NewsBank directory '{newsweb_dir}': {e}")


    rows_html = ""
    for idx, row in df.iterrows():
        ticker = row.get("Ticker", "N/A")
        ticker_display = str(ticker).replace(".OL", "").replace(".ol", "").strip()

        # --- Sparkline Embedding ---
        sparkline_html = '<span style="color: #e2e8f0; font-size: 12px; font-style: italic;">No Chart</span>'
        if os.path.exists(visuals_dir):
            try:
                matched_file = next(
                    (f for f in os.listdir(visuals_dir) if ticker_display.lower() in f.lower() and f.endswith(".png")),
                    None)
                if matched_file:
                    with open(os.path.join(visuals_dir, matched_file), "rb") as img_file:
                        encoded_string = base64.b64encode(img_file.read()).decode("utf-8")
                        sparkline_html = f'<img src="data:image/png;base64,{encoded_string}" class="sparkline-img" alt="{ticker_display} Sparkline">'
            except Exception as img_err:
                print(f"[WARNING] Sparkline asset match missed for {ticker_display}: {img_err}")


        # NEW — replace with:
        latest_news = get_latest_monthly_news(ticker_display, news_files, newsweb_dir)
        if latest_news and latest_news["summary"]:
            news_text = latest_news["summary"]
            sentiment_html = ""
            try:
                sentiment_val = float(latest_news["sentiment"])
                sentiment_class = "green-text" if sentiment_val >= 8 else (
                    "red-text" if sentiment_val <= 3 else "white-text")
                sentiment_html = f' &middot; <span class="{sentiment_class}" style="font-weight:700;">Sentiment {sentiment_val:.0f}/10</span>'
            except (TypeError, ValueError):
                pass
            news_header_html = f'<div class="date-subtext" style="margin-bottom:4px;">{latest_news["year_month"]}{sentiment_html}</div>'
        else:
            news_header_html = ""
            news_text = str(row.get("News", "No recent news updates found for this asset.")).strip()





        # --- Metric Extraction & Formatting ---
        category = "" if pd.isna(row.get("Category")) or row.get("Category") in ["N/A", "None"] else str(row.get("Category")).strip()
        price = row.get("Price", 0.0)
        sma20 = row.get("20 SMA Status", "N/A")
        sma50 = row.get("50 SMA Status", "N/A")
        sma200 = row.get("200 SMA Status", "N/A")

        def format_date(raw_date):
            try:
                return pd.to_datetime(raw_date).strftime("%d %b") if pd.notna(raw_date) else "N/A"
            except:
                return str(raw_date)

        sma20_chg = format_date(row.get("20 SMA Changed"))
        sma50_chg = format_date(row.get("50 SMA Changed"))
        sma200_chg = format_date(row.get("200 SMA Changed"))
        bb_chg = format_date(row.get("BB Signal Changed"))

        try:
            macd_chg = format_date(row.iloc[16]) if len(row) > 16 else "N/A"
        except:
            macd_chg = "N/A"

        cat_html = '<div class="light-gray-text"></div>'

        # --- RSI Logic ---
        rsi_val = row.get("RSI", 0.0)
        rsi_stat = str(row.get("RSI Status", "N/A")).strip()
        try:
            rsi_prev_val = float(row.get("RSI Value Day Before Change", 0.0))
        except:
            rsi_prev_val = 0.0

        rsi_delta = rsi_val - rsi_prev_val
        chg_prefix = "+" if rsi_delta >= 0 else ""
        rsi_alert_symbol = ' <span style="color: #4caf50; margin-left: 5px; font-size: 14px;">★</span>' if rsi_prev_val > 70 and rsi_val < 70 else ""

        rsi_stat_upper = rsi_stat.upper()
        rsi_stat_class = "white-text" if "NEUTRAL" in rsi_stat_upper else (
            "green-text" if "OVERSOLD" in rsi_stat_upper and rsi_val < 30 else "red-text")

        macd_hist = row.get("MACD Hist", 0.0)
        macd_sig = str(row.get("MACD Signal", "N/A")).strip()
        upper_bb = row.get("Upper BB", 0.0)
        lower_bb = row.get("Lower BB", 0.0)
        vol_ratio = row.get("Vol Ratio", 0.0)

        # --- Bollinger %B Calculations ---
        bb_date_html = ""
        if pd.notna(lower_bb) and pd.notna(upper_bb) and lower_bb > 0 and (upper_bb - lower_bb) > 0:
            pct_from_lower = ((price - lower_bb) / lower_bb) * 100
            pct_b = (price - lower_bb) / (upper_bb - lower_bb)
            bb_pct_class = "green-text" if pct_b <= 0.15 or price < lower_bb else (
                "red-text" if pct_b >= 0.85 else "white-text")
            bb_position_text = "Below Bands" if price < lower_bb else (
                "Near Bottom" if pct_b <= 0.15 else ("Near Top" if pct_b >= 0.85 else "Mid-Band"))
            bb_pct_subtext = f"{pct_from_lower:+.2f}% from floor"
            if bb_chg != "N/A": bb_date_html = f'<div class="date-subtext">Chg: {bb_chg}</div>'
        else:
            bb_pct_class, bb_position_text, bb_pct_subtext = "light-gray-text", "N/A", ""

        # --- Pattern Recognitions ---
        detected_badges = []
        price_above_50 = str(sma50).upper() == "ABOVE"
        price_below_50 = str(sma50).upper() == "BELOW"
        macd_hist_prev = row.get("MACD Hist Prev", None)

        if pd.notna(upper_bb) and pd.notna(lower_bb) and price > 0:
            if ((upper_bb - lower_bb) / lower_bb) < 0.12:
                detected_badges.append('<span class="orange-text" style="font-weight:700;">Squeeze</span>')

        if price_above_50 and pd.notna(
                macd_hist) and macd_hist_prev is not None and macd_hist > 0 and macd_hist <= macd_hist_prev:
            detected_badges.append('<span class="green-text" style="font-weight:700;">Bull Flag</span>')
        elif price_below_50 and pd.notna(
                macd_hist) and macd_hist_prev is not None and macd_hist < 0 and macd_hist >= macd_hist_prev:
            detected_badges.append('<span class="red-text" style="font-weight:700;">Bear Flag</span>')

        pattern_html = f'<div style="display:flex; flex-direction:column; gap:4px;">{"".join(detected_badges)}</div>' if detected_badges else '<span class="light-gray-text">—</span>'

        # --- FIXED VIEWGRAPH ROUTE PASSING ---
        # Forces both environments to route asset views through Flask serving
        file_url = f"{deepdives_route}/{ticker_display}_viewgraph.html"

        # --- Column Mappings ---
        sma20_class = "green-badge-left" if sma20 == "ABOVE" else "red-badge-left"
        sma50_class = "green-badge-middle" if sma50 == "ABOVE" else "red-badge-middle"
        sma200_class = "green-badge-right" if sma200 == "ABOVE" else "red-badge-right"
        macd_class = "green-text" if "BULLISH" in macd_sig.upper() else (
            "red-text" if "BEARISH" in macd_sig.upper() else "")
        vol_class = "green-text" if vol_ratio > 1.5 else ("red-text" if vol_ratio < 0.5 else "white-text")
        obv_trend = str(row.get("OBV Trend", "N/A")).strip()
        obv_class = "green-text" if obv_trend == "UP" else ("red-text" if obv_trend == "DOWN" else "")

        rows_html += f"""
        <tr>
            <td><strong style="color: #ffffff; font-size: 15px;">{ticker_display}</strong>{cat_html}<a href="{file_url}" class="graph-link" target="_blank">Show graph</a></td>
            <td class="price-text">{price:,.2f} NOK</td>
            <td><div class="sma-group-container"><div class="sma-block"><span class="sma-label">20 SMA</span><span class="badge {sma20_class}">{sma20}</span><div class="date-subtext">Chg: {sma20_chg}</div></div><div class="sma-block"><span class="sma-label" style="padding-left:6px;">50 SMA</span><span class="badge {sma50_class}">{sma50}</span><div class="date-subtext" style="padding-left:6px;">Chg: {sma50_chg}</div></div><div class="sma-block"><span class="sma-label" style="padding-left:6px;">200 SMA</span><span class="badge {sma200_class}">{sma200}</span><div class="date-subtext" style="padding-left:6px;">Chg: {sma200_chg}</div></div></div></td>
            <td><span class="{macd_class}" style="font-weight:600;">{macd_sig}</span><div class="date-subtext">Hist: {macd_hist:.4f}</div><div class="date-subtext">Chg: {macd_chg}</div></td>
            <td class="col-bb-pct"><span class="{bb_pct_class}" style="font-size:15px; font-weight:700;">{bb_position_text}</span><div class="date-subtext">{bb_pct_subtext}</div><div class="date-subtext">Floor: {lower_bb:,.2f}</div>{bb_date_html}</td>
            <td class="col-pattern">{pattern_html}</td>
            <td><span class="price-text">{rsi_val:.2f}</span><div style="display: flex; align-items: center; margin-top: 2px;"><span class="{rsi_stat_class}" style="font-weight: 600;">{rsi_stat}</span>{rsi_alert_symbol}</div><div class="date-subtext" style="margin-top: 1px;">Prev: {rsi_prev_val:.2f} ({chg_prefix}{rsi_delta:.2f})</div></td>
            <td class="col-volume"><span class="price-text {vol_class}">{vol_ratio:.2f}x</span><div class="{obv_class}" style="font-weight:600; margin-top:2px; font-size:14px;">{obv_trend}</div></td>
            <td class="col-sparkline">{sparkline_html}</td>
            <td class="col-news"><div class="news-scroll-container">{news_header_html}{news_text}</div></td>
        </tr>
        """

    html_template = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Technical Screener</title><style>body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b0c10; color: #c5c6c7; padding: 30px; margin: 0; }} .wrapper {{ max-width: 1920px; margin: 0 auto; }} .header-panel {{ display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid #1f2833; padding-bottom: 20px; margin-bottom: 25px; }} h2 {{ color: #ffffff; margin: 0 0 5px 0; font-size: 26px; font-weight: 600; letter-spacing: -0.5px; }} .subtitle {{ color: #e2e8f0; margin: 0 0 12px 0; font-size: 14px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }} table {{ border-collapse: collapse; width: 100%; background-color: #1f2833; border-radius: 10px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); table-layout: fixed; }} th, td {{ padding: 30px 14px; text-align: left; vertical-align: top; word-wrap: break-word; }} th {{ background-color: #151b24; color: #e2e8f0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 3px solid #0b0c10; }} .th-desc {{ text-transform: none; font-size: 10px; color: #94a3b8; margin: 4px 0 0 0; line-height: 1.3; font-weight: 400; }} th:nth-child(1), td:nth-child(1) {{ width: 120px; }} th:nth-child(2), td:nth-child(2) {{ width: 100px; }} th:nth-child(3), td:nth-child(3) {{ width: 230px; }} th:nth-child(4), td:nth-child(4) {{ width: 140px; }} th.col-bb-pct, td.col-bb-pct {{ width: 140px; }} th.col-pattern, td.col-pattern {{ width: 100px; }} th:nth-child(7), td:nth-child(7) {{ width: 145px; }} th.col-volume, td.col-volume {{ width: 105px; }} th.col-sparkline, td.col-sparkline {{ width: 235px; }} th.col-news, td.col-news {{ width: 340px; }} td.col-sparkline {{ text-align: center; vertical-align: middle; padding: 8px 5px; }} .sparkline-img {{ width: 220px; height: auto; display: block; margin: 0 auto; filter: brightness(1.15) contrast(1.05); }} .news-scroll-container {{ font-size: 12px; line-height: 1.45; color: #d1d2d3; max-height: 72px; overflow-y: auto; padding-right: 4px; }} tr {{ border-bottom: 1px solid #0b0c10; transition: background 0.15s ease; }} tr:hover {{ background-color: #2b3a4a; }} .price-text {{ font-family: monospace; font-size: 15px; font-weight: bold; color: #ffffff; white-space: nowrap; }} .light-gray-text {{ font-size: 11px; color: #b0b3b8; margin-top: 4px; }} .graph-link {{ display: inline-block; font-size: 11px; color: #94a3b8; text-decoration: none; margin-top: 6px; border-bottom: 1px dashed rgba(148, 163, 184, 0.4); }} .graph-link:hover {{ color: #e2e8f0; border-bottom-style: solid; }} .sma-group-container {{ display: flex; }} .sma-block {{ display: flex; flex-direction: column; }} .sma-label {{ font-size: 11px; color: #858585; margin-bottom: 4px; }} .badge {{ display: inline-block; padding: 4px 8px; font-size: 11px; font-weight: bold; min-width: 52px; text-align: center; }} .green-badge-left {{ background-color: rgba(76,175,80,0.15); color: #4caf50; border: 1px solid rgba(76,175,80,0.25); border-right: none; border-radius: 4px 0 0 4px; }} .red-badge-left {{ background-color: rgba(244,67,54,0.15); color: #f44336; border: 1px solid rgba(244,67,54,0.25); border-right: none; border-radius: 4px 0 0 4px; }} .green-badge-middle {{ background-color: rgba(76,175,80,0.15); color: #4caf50; border: 1px solid rgba(76,175,80,0.25); border-right: none; }} .red-badge-middle {{ background-color: rgba(244,67,54,0.15); color: #f44336; border: 1px solid rgba(244,67,54,0.25); border-right: none; }} .green-badge-right {{ background-color: rgba(76,175,80,0.15); color: #4caf50; border: 1px solid rgba(76,175,80,0.25); border-radius: 0 4px 4px 0; }} .red-badge-right {{ background-color: rgba(244,67,54,0.15); color: #f44336; border: 1px solid rgba(244,67,54,0.25); border-radius: 0 4px 4px 0; }} .date-subtext {{ font-size: 11px; color: #858585; margin-top: 4px; }} .green-text {{ color: #4caf50 !important; }} .red-text {{ color: #f44336 !important; }} .white-text {{ color: #ffffff !important; }} .orange-text {{ color: #ff9800 !important; }}</style></head><body><div class="wrapper"><div class="header-panel"><div><h2>OlaiProject</h2><p class="subtitle">Oslo Børs</p></div>
    <div class="timestamp">Total Rows Parsed: {len(df)}</div><div style="margin-top: 4px; font-style: italic;">Last Updated: {last_updated}</div></div></div><table><thead><tr><th>Company</th><th>Price</th><th>20 / 50 / 200 SMA</th><th>MACD</th><th class="col-bb-pct">Bollinger Position</th><th class="col-pattern">Flag Pattern</th><th>RSI</th><th class="col-volume">Volume</th><th class="col-sparkline">News Sparkline</th><th class="col-news">News Highlight</th></tr></thead><tbody>{rows_html}</tbody></table></div></body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Success! Dashboard file updated at: {output_path}")
    return True