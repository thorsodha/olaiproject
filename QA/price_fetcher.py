import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from openpyxl import load_workbook
import config

START_CUTOFF = datetime(2024, 1, 1).date()


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
    # Get ticket
    file_path = os.path.join(config.OSLOBORS_DIR, f"{ticker}.xlsx")

    # check if file exists
    is_valid, message = check_file_integrity(file_path, ticker)
    yield f"[{ticker}] {message}<br>"
    if not is_valid:
        return

    # Find Start Date & Existing Date Set
    existing_dates = set()
    df_existing = None
    #TODO avoid hard coding here
    sheet_name_to_use = "Sheet1"

    if os.path.exists(file_path):
        try:
            excellink = pd.ExcelFile(file_path, engine='openpyxl')
            #TODO avoid hard coding
            sheet_name_to_use = excellink.sheet_names[0]
            df_existing = excellink.parse(sheet_name_to_use, header=None)

            #TODO fix hardcoding
            if len(df_existing) >= 3:

                existing_dates = set(pd.to_datetime(df_existing.iloc[3:, 0], errors='coerce').dt.date)
                last_date_val = df_existing.iloc[-1, 0]
                last_date_dt = pd.to_datetime(last_date_val).date()
                fetch_start = max(last_date_dt, START_CUTOFF)
            else:
                fetch_start = START_CUTOFF

        except Exception as e:
            yield f"[{ticker}] Error reading existing file: {e}<br>"
            fetch_start = START_CUTOFF
    else:
        fetch_start = START_CUTOFF

    # Gather up the existing data
    start_str = fetch_start.strftime('%Y-%m-%d')
    end_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    yield f"[{ticker}] Fetching from Yahoo Finance {start_str}...<br>"
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

    if len(new_data) < 1:
        yield f"[{ticker}] Zero rows returned. Skipping.<br>"
        return

    if 'Volume' in new_data.columns and new_data['Volume'].sum() == 0:
        yield f"[{ticker}] Warning: Volume is 0. Skipping to avoid bad entry.<br>"
        return

    # 4. Process and Filter Data
    new_rows = []
    for index, row in new_data.iterrows():
        current_date = index.date()

        if current_date < START_CUTOFF or current_date in existing_dates:
            continue

        data_row = [None] * 8
        data_row[0] = index.replace(tzinfo=None)
        data_row[1] = row['Close']
        data_row[2] = row['Dividends']
        data_row[3] = row['High']
        data_row[4] = row['Low']
        data_row[5] = row['Open']
        data_row[6] = row['Stock Splits']
        data_row[7] = int(row['Volume'])

        new_rows.append(data_row)

    # 5. Build Final DataFrame
    if not new_rows:
        yield f"[{ticker}] All data is up to date.<br>"
        return

    df_new = pd.DataFrame(new_rows)

    if df_existing is None or len(df_existing) < 3:
        header_rows = [
            ["Price", "Close", "Dividends", "High", "Low", "Open", "Stock Splits", "Volume"],
            ["Ticker", ticker, ticker, ticker, ticker, ticker, ticker, ticker],
            ["Date", "", "", "", "", "", "", ""]
        ]
        df_final = pd.concat([pd.DataFrame(header_rows), df_new], ignore_index=True)
    else:
        df_final = pd.concat([df_existing, df_new], ignore_index=True)

    # 6. Save directly to the mapped folder WITHOUT deleting other tabs
    try:
        if os.path.exists(file_path):
            with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_final.to_excel(writer, index=False, header=False, sheet_name=sheet_name_to_use)
        else:
            df_final.to_excel(file_path, index=False, header=False, engine='openpyxl', sheet_name=sheet_name_to_use)

        yield f"[{ticker}] <span style='color:#22c55e;'>Success: Prices updated. Fundamental tabs preserved.</span><br>"
    except Exception as e:
        yield f"[{ticker}] <span style='color:#ef4444;'>Error saving: {e}</span><br>"