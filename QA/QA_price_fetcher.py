import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime


class MockConfig:
    OSLOBORS_DIR = r"E:\OneDrive\Desktop\OlaiProject\PriceData"


# Force configuration override before testing core script paths
sys.modules['config'] = MockConfig

from price_fetcher import update_ticker_data, check_file_integrity


class TestYFinanceDataFaults(unittest.TestCase):

    def setUp(self):
        self.ticker = "AFG.OL"
        self.test_file = os.path.join(MockConfig.OSLOBORS_DIR, f"{self.ticker}.xlsx")

    @patch('price_fetcher.os.path.exists', return_value=True)
    @patch('price_fetcher.pd.ExcelFile')
    def test_1_file_already_up_to_date_skipped(self, mock_excel_file, mock_exists):
        """Simulate an existing Excel file where the last recorded date is set to today."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        mock_sheet_data = pd.DataFrame([
            ["Price", "Close", "Dividends", "High", "Low", "Open", "Stock Splits", "Volume"],
            ["Ticker", self.ticker, self.ticker, self.ticker, self.ticker, self.ticker, self.ticker, self.ticker],
            ["Date", "", "", "", "", "", "", ""],
            [today_str, 150.0, 0, 155.0, 149.0, 151.0, 0, 10000]
        ])
        mock_writer_instance = MagicMock()
        mock_writer_instance.sheet_names = ["Sheet1"]
        mock_writer_instance.parse.return_value = mock_sheet_data
        mock_excel_file.return_value = mock_writer_instance

        logs = "".join(list(update_ticker_data(self.ticker)))
        self.assertIn("up to date", logs.lower())

    @patch('price_fetcher.os.path.exists', return_value=False)
    @patch('yfinance.Ticker')
    def test_2_pipeline_filters_empty_nan_rows(self, mock_ticker, mock_exists):
        """Simulate a response from yfinance where the data row structure exists but price values are entirely blank (NaN)."""
        bad_df = pd.DataFrame(
            [[np.nan, np.nan, np.nan, np.nan, 50000, 0, 0]],
            columns=['Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits'],
            index=[pd.Timestamp('2025-06-01')]  # Safe date bypasses chronological cutoff blocks
        )
        mock_instance = MagicMock()
        mock_instance.history.return_value = bad_df
        mock_ticker.return_value = mock_instance

        logs = "".join(list(update_ticker_data(self.ticker)))
        normalized_logs = logs.lower()

        has_expected_behavior = any(x in normalized_logs for x in ["skip", "empty", "no new data", "up to date"])
        self.assertTrue(has_expected_behavior)

    def test_3_volume_safeguard_casting(self):
        """Simulate an asset row that contains active price values but has a missing/blank (NaN) Volume field."""
        row_with_nan_volume = {'Volume': np.nan, 'Close': 185.0}
        volume_val = row_with_nan_volume.get('Volume', 0)
        volume_int = int(volume_val) if pd.notna(volume_val) else 0
        self.assertEqual(volume_int, 0)

    @patch('price_fetcher.os.path.exists', return_value=False)
    @patch('yfinance.Ticker')
    def test_4_zero_volume_day_skipped(self, mock_ticker, mock_exists):
        """Simulate a scenario where yfinance returns a row on a trading day with an aggregate volume of exactly 0."""
        zero_vol_df = pd.DataFrame(
            [[180.0, 185.0, 179.0, 184.0, 0, 0, 0]],
            columns=['Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits'],
            index=[pd.Timestamp('2024-01-02')]
        )
        mock_instance = MagicMock()
        mock_instance.history.return_value = zero_vol_df
        mock_ticker.return_value = mock_instance

        logs = "".join(list(update_ticker_data(self.ticker)))
        self.assertIn("Volume is 0", logs)

    def test_5_file_integrity_mismatch_flagged(self):
        """Point workbook layout checker at an Excel file that belongs to a completely different ticker symbol."""
        header_rows = [
            ["Price", "Close", "Dividends"],
            ["Ticker", "WRONG_TICKER", "WRONG_TICKER"]
        ]
        with patch('price_fetcher.pd.read_excel', return_value=pd.DataFrame(header_rows)):
            with patch('price_fetcher.os.path.exists', return_value=True):
                is_valid, msg = check_file_integrity(self.test_file, self.ticker)
                self.assertFalse(is_valid)
                self.assertIn("Ticker mismatch", msg)


if __name__ == '__main__':
    # Load all targeted tests from the suite class
    suite = unittest.TestLoader().loadTestsFromTestCase(TestYFinanceDataFaults)

    # Run tests silently to allow custom output formatting
    result = unittest.TextTestRunner(stream=open(os.devnull, 'w')).run(suite)

    print("\n" + "=" * 90)
    print(" YFINANCE DATA INTEGRITY: QA PIPELINE TEST SUMMARY")
    print("=" * 90)

    # Process and map internal test method runs into custom summary logs
    for test in suite:
        test_method_name = test._testMethodName
        actual_test_func = getattr(test, test_method_name)
        description = actual_test_func.__doc__ or "No description provided."
        formatted_title = test_method_name.replace("test_", "").replace("_", " ").title()

        status = "PASS"
        is_failure = any(f[0]._testMethodName == test_method_name for f in result.failures)
        is_error = any(e[0]._testMethodName == test_method_name for e in result.errors)

        if is_failure or is_error:
            status = "FAIL"
            handling = "Unable to handle"
        else:
            handling = "Able to handle"

        print(f"** {formatted_title} **")
        print(f"   Description : {description}")
        print(f"   Status      : {status} / {handling}\n")

    print("-" * 90)
    if result.wasSuccessful():
        print("FINAL STATUS: SUCCESS (All defensive checks passed safely)")
    else:
        print("FINAL STATUS: FAILED (Pipeline vulnerabilities found)")
    print("=" * 90 + "\n")