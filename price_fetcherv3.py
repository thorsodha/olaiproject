import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from openpyxl import load_workbook
import config  # Relies on config.OSLOBORS_DIR as requested

# --- CONFIGURATION ---
TICKERS = ["NAS.OL", "2020.OL"]
START_CUTOFF = datetime(2025, 1, 1).date()


# ---------------------

def get_ticker_paths(ticker):
    """Returns the path to save the file using config.OSLOBORS_DIR."""
    return os.path.join(config.OSLOBORS_DIR, f"{ticker}.xlsx")


def check_file_integrity(file_path, ticker):
    """Checks if file exists and has the correct ticker in the header."""
    if not os.path.exists(file_path):
        return True, "File does not exist. Will create with headers."
    try:
        df_check = pd.read_excel(file_path, header=None, nrows=2)
        if len(df_check) < 2:
            return True, "File exists but is empty/corrupt. Will overwrite with headers."

        existing_ticker = str(df_check.iloc[1, 1]).strip()
        if existing_ticker != ticker:
            return False, f"Ticker mismatch: Found {existing_ticker}, expected {ticker}."

        return True, "Integrity OK."
    except Exception as e:
        return True, f"Error reading file ({e}). Will treat as fresh start."


def update_ticker_data(ticker):
    file_path = get_ticker_paths(ticker)

    # 1. Integrity Check
    is_valid, message = check_file_integrity(file_path, ticker)
    yield f"[{ticker}] {message}<br>"
    if not is_valid:
        return

    # 2. Determine Start Date & Existing Date Set
    existing_dates = set()
    df_existing = None
    sheet_name_to_use = "Sheet1"

    if os.path.exists(file_path):
        try:
            xls = pd.ExcelFile(file_path, engine='openpyxl')
            sheet_name_to_use = xls.sheet_names[0]
            df_existing = xls.parse(sheet_name_to_use, header=None)

            if len(df_existing) >= 3:
                existing_dates = set(pd.to_datetime(df_existing.iloc[3:, 0], errors='coerce').dt.date)
                last_date_val = df_existing.iloc[-1, 0]
                last_date_dt = pd.to_datetime(last_date_val, errors='coerce')

                if pd.isna(last_date_dt):
                    fetch_start = START_CUTOFF
                else:
                    fetch_start = max(last_date_dt.date(), START_CUTOFF)
            else:
                fetch_start = START_CUTOFF
        except Exception as e:
            yield f"[{ticker}] Error reading existing file: {e}<br>"
            fetch_start = START_CUTOFF
    else:
        fetch_start = START_CUTOFF

    # 3. Fetch Data
    start_str = fetch_start.strftime('%Y-%m-%d')


    #### Because yfinance does not have necessary data
    end_str = (datetime.now() + timedelta(days=-1)).strftime('%Y-%m-%d')



    yield f"[{ticker}] Fetching from Yahoo Finance {start_str} to {end_str}...<br>"
    ticker_obj = yf.Ticker(ticker)

    try:
        new_data = ticker_obj.history(start=start_str, end=end_str)
    except Exception as e:
        yield f"[{ticker}] <span style='color:#ef4444;'>yfinance crashed! Skipping and logging error...</span><br>"
        log_path = os.path.join(config.OSLOBORS_DIR, "error_log.txt")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] TICKER: {ticker} | ERROR: {str(e)}\n")
        return

    if new_data is None or new_data.empty:
        yield f"[{ticker}] <span style='color:#f59e0b; font-weight:bold;'>No new data found. Skipping safely.</span><br>"
        return

    if 'Volume' in new_data.columns and new_data['Volume'].sum() == 0:
        yield f"[{ticker}] Warning: Volume is 0. Skipping to avoid bad entry.<br>"
        return

    # 4. Process and Filter Data
    new_rows = []
    skipped_rows = 0
    for index, row in new_data.iterrows():
        try:
            current_date = index.date()

            if current_date < START_CUTOFF or current_date in existing_dates:
                continue

            close_val = row.get('Close')
            open_val = row.get('Open')
            high_val = row.get('High')
            low_val = row.get('Low')

            # Validation: Filter out records where any key metric is missing or <= 0
            is_corrupt = (
                    pd.isna(close_val) or close_val <= 0 or
                    pd.isna(open_val) or open_val <= 0 or
                    pd.isna(high_val) or high_val <= 0 or
                    pd.isna(low_val) or low_val <= 0
            )

            if is_corrupt:
                skipped_rows += 1
                continue

            volume_val = row.get('Volume')
            volume_val = int(volume_val) if pd.notna(volume_val) else 0

            data_row = [None] * 8
            data_row[0] = index.replace(tzinfo=None)
            data_row[1] = close_val
            data_row[2] = row.get('Dividends', 0) if pd.notna(row.get('Dividends', 0)) else 0
            data_row[3] = high_val
            data_row[4] = low_val
            data_row[5] = open_val
            data_row[6] = row.get('Stock Splits', 0) if pd.notna(row.get('Stock Splits', 0)) else 0
            data_row[7] = volume_val

            new_rows.append(data_row)
        except Exception as e:
            skipped_rows += 1
            yield f"[{ticker}] <span style='color:#f59e0b;'>Skipped a row for {index}: {e}</span><br>"

    if skipped_rows:
        yield f"[{ticker}] <span style='color:#f59e0b;'>Skipped {skipped_rows} row(s) with missing/invalid data.</span><br>"

    # 5. Build Final DataFrame
    if not new_rows:
        yield f"[{ticker}] All data is up to date.<br>"
        return

    df_new = pd.DataFrame(new_rows)

    # Clean missing or zero close prices
    if 1 in df_new.columns and not df_new.empty:
        df_new[1] = pd.to_numeric(df_new[1], errors='coerce')
        invalid_rows_mask = df_new[1].isna() | (df_new[1] <= 0)

        if invalid_rows_mask.any():
            invalid_count = invalid_rows_mask.sum()
            df_new = df_new[~invalid_rows_mask]
            yield f"[{ticker}] <span style='color:#f59e0b;'>Cleaned {invalid_count} row(s) with missing/zero close prices from new data.</span><br>"

    # Litmus Test
    is_numeric_and_valid = False
    if 1 in df_new.columns and not df_new.empty:
        valid_numbers = pd.to_numeric(df_new[1], errors='coerce').dropna()
        valid_numbers = valid_numbers[valid_numbers > 0]
        if not valid_numbers.empty:
            is_numeric_and_valid = True

    if not is_numeric_and_valid:
        yield f"[{ticker}] <span style='color:#ef4444;'>Error: Litmus test failed. No valid prices found to update.</span><br>"
        return

    if df_existing is None or len(df_existing) < 3:
        header_rows = [
            ["Price", "Close", "Dividends", "High", "Low", "Open", "Stock Splits", "Volume"],
            ["Ticker", ticker, ticker, ticker, ticker, ticker, ticker, ticker],
            ["Date", "", "", "", "", "", "", ""]
        ]
        df_final = pd.concat([pd.DataFrame(header_rows), df_new], ignore_index=True)
    else:
        df_final = pd.concat([df_existing, df_new], ignore_index=True)

    # 6. Save directly WITHOUT deleting other tabs
    try:
        if os.path.exists(file_path):
            with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_final.to_excel(writer, index=False, header=False, sheet_name=sheet_name_to_use)
        else:
            df_final.to_excel(file_path, index=False, header=False, engine='openpyxl', sheet_name=sheet_name_to_use)

        try:
            os.sync()
        except AttributeError:
            pass

        yield f"[{ticker}] <span style='color:#22c55e;'>Success: Prices updated. Fundamental tabs preserved.</span><br>"
    except Exception as e:
        yield f"[{ticker}] <span style='color:#ef4444;'>Error saving: {e}</span><br>"


def main():
    if not os.path.exists(config.OSLOBORS_DIR):
        os.makedirs(config.OSLOBORS_DIR, exist_ok=True)

    for ticker in TICKERS:
        try:
            # Consuming the generator when running directly via CLI
            for log in update_ticker_data(ticker):
                # Clean the HTML tags for a neat terminal presentation
                clean_log = log.replace("<br>", "").replace("<span style='color:#ef4444;'>", "").replace(
                    "<span style='color:#f59e0b; font-weight:bold;'>", "").replace("<span style='color:#f59e0b;'>",
                                                                                   "").replace(
                    "<span style='color:#22c55e;'>", "").replace("</span>", "")
                print(clean_log)
        except Exception as e:
            print(f"[{ticker}] Failed unexpectedly: {e}")


if __name__ == "__main__":
    main()