import os
import time
import numpy as np
import pandas as pd
from openpyxl.styles import Alignment
import config  # Centralized configuration module

def get_last_cross_date(df, current_status, status_series, warm_up_period=200):
    """
    Looks backward in the dataframe to find the most recent date where
    the status switched into its current state.
    Ignores initial warm-up rows to avoid false NaN-boundary triggers.
    """
    if not isinstance(df.index, pd.DatetimeIndex) or len(df) <= warm_up_period:
        return "N/A"

    valid_status_series = status_series.iloc[warm_up_period:]
    current_status_rows = valid_status_series[valid_status_series == current_status]
    if current_status_rows.empty:
        return "N/A"

    different_status_rows = valid_status_series[valid_status_series != current_status]

    if not different_status_rows.empty:
        last_diff_date = different_status_rows.index[-1]
        post_switch_rows = current_status_rows[current_status_rows.index > last_diff_date]
        if not post_switch_rows.empty:
            return post_switch_rows.index[0].date()

    return "No Change"


def main():
    # Constants
    RSI_PERIOD = 14
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    COL_WIDTH = 20

    yield f"[TA] Starting Technical Analysis Engine...<br>"
    yield f"[TA] Pulling target criteria from: {config.WATCHLIST_PATH}<br>"

    # --- STEP 0: DYNAMICALLY EXTRACT TICKERS FROM WATCHLIST ---
    if not os.path.exists(config.WATCHLIST_PATH):
        yield f"[TA] <span style='color: #ef4444;'>ERROR: Watchlist file not found at {config.WATCHLIST_PATH}</span><br>"
        return

    target_tickers = []
    try:
        df_watchlist = pd.read_excel(config.WATCHLIST_PATH)
        if 'Ticker' in df_watchlist.columns:
            target_tickers = df_watchlist['Ticker'].dropna().astype(str).str.strip().tolist()
        else:
            yield f"[TA] <span style='color: #ef4444;'>ERROR: No 'Ticker' column found in Watchlist.</span><br>"
            return

        yield f"[TA] Successfully isolated {len(target_tickers)} targets from your watchlist.<br>"

    except Exception as e:
        yield f"[TA] <span style='color: #ef4444;'>ERROR reading watchlist criteria: {str(e)}</span><br>"
        return

    # --- STEP 1: INITIALIZE SCANNING ---
    technical_results = []

    # FIXED: Replaced legacy SOURCE_DIR references with config.OSLOBORS_DIR
    if not os.path.exists(config.OSLOBORS_DIR):
        yield f"[TA] <span style='color: #ef4444;'>ERROR: Price data directory not found: {config.OSLOBORS_DIR}</span><br>"
        return

    for ticker in target_tickers:
        file_name = f"{ticker}.xlsx"
        # FIXED: Replaced legacy SOURCE_DIR reference with config.OSLOBORS_DIR
        file_path = os.path.join(config.OSLOBORS_DIR, file_name)

        if not os.path.exists(file_path):
            yield f"[TA] [MISSING] Ticker sheet {file_name} absent. Bypassing.<br>"
            continue

        try:
            # --- STEP 2: LOAD DATA ---
            raw_df = pd.read_excel(file_path, sheet_name=0, nrows=10, header=None)
            header_row_index = 0
            for i, row in raw_df.iterrows():
                row_str = " ".join([str(x) for x in row.values])
                if 'Date' in row_str or 'Close' in row_str:
                    header_row_index = i
                    break

            df = pd.read_excel(file_path, sheet_name=0, skiprows=header_row_index)
            df.columns = [str(c).strip() for c in df.columns]

            # --- STEP 3: DATA CLEANING ---
            df.rename(columns={df.columns[0]: 'Date'}, inplace=True)
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce', format='mixed')
            df.dropna(subset=['Date'], inplace=True)
            df.set_index('Date', inplace=True)
            df.sort_index(inplace=True)
            df.index = pd.to_datetime(df.index)

            close_col = next((c for c in df.columns if 'Close' in c), None)
            vol_col = next((c for c in df.columns if 'Volume' in c), None)

            if not close_col or not vol_col or len(df) < 200:
                yield f"[TA] [SKIP] {ticker} (Insufficient depth for 200 SMA model).<br>"
                continue

            df[close_col] = pd.to_numeric(df[close_col], errors='coerce')
            df[vol_col] = pd.to_numeric(df[vol_col], errors='coerce')

            # --- STEP 4: CALCULATIONS ---
            df['MA20'] = df[close_col].rolling(window=20).mean()
            df['SMA50'] = df[close_col].rolling(window=50).mean()
            df['SMA200'] = df[close_col].rolling(window=200).mean()

            df['STD'] = df[close_col].rolling(window=20).std()
            df['Upper_Band'] = df['MA20'] + (df['STD'] * 2)
            df['Lower_Band'] = df['MA20'] - (df['STD'] * 2)

            delta = df[close_col].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=RSI_PERIOD).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()

            rs = gain / loss.replace(0, np.nan)
            df['RSI'] = 100 - (100 / (1 + rs.fillna(0)))

            # --- STEP 5: MACD CALCULATION ---
            exp1 = df[close_col].ewm(span=MACD_FAST, adjust=False).mean()
            exp2 = df[close_col].ewm(span=MACD_SLOW, adjust=False).mean()
            df['MACD'] = exp1 - exp2
            df['Signal_Line'] = df['MACD'].ewm(span=MACD_SIGNAL, adjust=False).mean()
            df['MACD_Hist'] = df['MACD'] - df['Signal_Line']

            # --- STEP 6: OBV CALCULATION ---
            df['OBV'] = (np.sign(df[close_col].diff()).fillna(0) * df[vol_col]).cumsum()

            # --- STEP 7: VOL RATIO ---
            df['Avg_Vol_20'] = df[vol_col].rolling(20).mean()
            df['Vol_Ratio'] = (df[vol_col] / df['Avg_Vol_20']).round(2).fillna(0.0)

            # --- HISTORICAL STATE GENERATION FOR TIMESTAMPS ---
            df_sma20_series = pd.Series(np.where(df[close_col] > df['MA20'], "ABOVE", "BELOW"), index=df.index)
            df_sma50_series = pd.Series(np.where(df[close_col] > df['SMA50'], "ABOVE", "BELOW"), index=df.index)
            df_sma200_series = pd.Series(np.where(df[close_col] > df['SMA200'], "ABOVE", "BELOW"), index=df.index)
            df_rsi_series = pd.Series(
                np.where(df['RSI'] >= 70, "OVERBOUGHT", np.where(df['RSI'] <= 30, "OVERSOLD", "NEUTRAL")),
                index=df.index)
            df_macd_above_2 = pd.Series(np.where(df['MACD'] > 2, "ABOVE 2", "BELOW 2"), index=df.index)
            df_macd_signal_series = pd.Series(
                np.where(df['MACD'] > df['Signal_Line'], "BULLISH CROSS", "BEARISH CROSS"), index=df.index)
            df_obv_trend = pd.Series(np.where(df['OBV'] > df['OBV'].shift(4), "UP", "DOWN"), index=df.index)
            df_bb_series = pd.Series(np.where(df[close_col] > df['Upper_Band'], "BULLISH", "NEUTRAL"), index=df.index)
            df_vol_alert = pd.Series(np.where(df['Vol_Ratio'] > 3.0, "ABOVE 3", "BELOW 3"), index=df.index)

            # --- STEP 8: EXTRACT LATEST VALUES & TRACK LAST SWITCH DATES ---
            latest = df.iloc[-1]
            current_price = latest[close_col]

            sma20_status = df_sma20_series.iloc[-1]
            sma50_status = df_sma50_series.iloc[-1]
            sma200_status = df_sma200_series.iloc[-1]
            rsi_status = df_rsi_series.iloc[-1]
            macd2_status = df_macd_above_2.iloc[-1]
            macd_signal = df_macd_signal_series.iloc[-1]
            obv_trend = df_obv_trend.iloc[-1]
            bb_signal = df_bb_series.iloc[-1]
            vol_alert_status = df_vol_alert.iloc[-1]

            date_sma20_switch = get_last_cross_date(df, sma20_status, df_sma20_series)
            date_sma50_switch = get_last_cross_date(df, sma50_status, df_sma50_series)
            date_sma200_switch = get_last_cross_date(df, sma200_status, df_sma200_series)
            date_rsi_switch = get_last_cross_date(df, rsi_status, df_rsi_series)
            date_macd2_switch = get_last_cross_date(df, macd2_status, df_macd_above_2)
            date_macd_sig_switch = get_last_cross_date(df, macd_signal, df_macd_signal_series)
            date_obv_switch = get_last_cross_date(df, obv_trend, df_obv_trend)
            date_bb_switch = get_last_cross_date(df, bb_signal, df_bb_series)
            date_vol_switch = get_last_cross_date(df, vol_alert_status, df_vol_alert)

            if isinstance(date_rsi_switch, (str, type(None))) or date_rsi_switch in ["N/A", "No Change"]:
                val_rsi_switch = "N/A"
            else:
                ts_key = pd.Timestamp(date_rsi_switch)
                idx_pos = df.index.get_loc(ts_key)
                val_rsi_switch = round(df['RSI'].iloc[idx_pos - 1], 2) if idx_pos > 0 else "N/A"

            # --- STEP 9: GATHER ALL METRICS ---
            technical_results.append({
                'Ticker': ticker,
                'Price': round(current_price, 2),
                '20 SMA Status': sma20_status,
                '20 SMA Changed': date_sma20_switch,
                '50 SMA Status': sma50_status,
                '50 SMA Changed': date_sma50_switch,
                '200 SMA Status': sma200_status,
                '200 SMA Changed': date_sma200_switch,
                'RSI': round(latest['RSI'], 2),
                'RSI Status': rsi_status,
                'RSI Changed': date_rsi_switch,
                'RSI Value Day Before Change': val_rsi_switch,
                'MACD Hist': round(latest['MACD_Hist'], 4),
                'MACD Signal': macd_signal,
                'MACD Sig Changed': date_macd_sig_switch,
                'MACD > 2 Changed': date_macd2_switch,
                'OBV Trend': obv_trend,
                'OBV Trend Changed': date_obv_switch,
                'Upper BB': round(latest['Upper_Band'], 2),
                'Lower BB': round(latest['Lower_Band'], 2),
                'BB Signal': bb_signal,
                'BB Signal Changed': date_bb_switch,
                'Vol Ratio': latest['Vol_Ratio'],
                'Vol > 3 Changed': date_vol_switch
            })
            yield f"[TA] -> Processed {ticker:<10} successfully.<br>"

        except Exception as e:
            yield f"[TA] <span style='color: #ef4444;'>-> Error parsing {ticker}: {str(e)}</span><br>"

    # --- STEP 10: SAVE WITH NATIVE EXCEL FORMATTING ---
    if technical_results:
        final_df = pd.DataFrame(technical_results)
        final_df.sort_values(by=['Vol Ratio'], ascending=[False], inplace=True)

        try:
            # FIXED: Replaced legacy TARGET_FILE reference with config.TECHNICAL_FILE
            with pd.ExcelWriter(config.TECHNICAL_FILE, engine='openpyxl', datetime_format='yyyy-mm-dd',
                                date_format='yyyy-mm-dd') as writer:
                final_df.to_excel(writer, sheet_name='Technical_Screen', index=False)

                workbook = writer.book
                worksheet = writer.sheets['Technical_Screen']
                center_alignment = Alignment(horizontal='center', vertical='center')

                for col in worksheet.columns:
                    col_letter = col[0].column_letter
                    worksheet.column_dimensions[col_letter].width = COL_WIDTH
                    for cell in col:
                        cell.alignment = center_alignment

            yield f"[TA] <span style='color: #22c55e;'><b>Success: Technical framework written to cloud storage volume.</b></span><br>"
        except Exception as e:
            yield f"[TA] <span style='color: #ef4444;'>Save Error: Could not write metrics payload: {e}</span><br>"
    else:
        yield f"[TA] Warnings issued: Empty results payload compiled.<br>"


if __name__ == "__main__":
    for line in main():
        print(line.replace("<br>", ""))