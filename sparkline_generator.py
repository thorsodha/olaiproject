import os
import pandas as pd
import config

# --- REQUIRED FOR DOCKER ---
# Must be set before importing pyplot to force headless background rendering
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# ---------------------------

def generate_na_sparkline(output_path):
    """
    Generates a dark-mode placeholder 'N/A' image matching the narrow dimensions
    (1.8x0.8) and white text configuration.
    """
    try:
        plt.figure(figsize=(1.8, 0.8))
        plt.text(0.5, 0.5, 'N/A', fontsize=12, fontweight='bold', color='#ffffff',
                 ha='center', va='center')

        plt.axis('off')
        plt.tight_layout(pad=0)
        plt.savefig(output_path, dpi=200, bbox_inches='tight', transparent=True)
        plt.close()
        return True
    except Exception as e:
        print(f"Failed to create N/A placeholder graphic: {e}")
        plt.close()
        return False


def generate_row_sparkline(file_path, row_number, ticker_name, sheet_name='Monthly Analysis'):
    """
    Generates an ultra-compact, narrow dark-mode sparkline.
    Uses a light blue line with horizontal white numbers that alternate heights to prevent overlap.
    """
    output_dir = config.SPARKLINES_DIR

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    filename = f"sparkline_row_{row_number}_{ticker_name}.png"
    full_output_path = os.path.join(output_dir, filename)

    # Fallback: Data file does not exist on disk
    if not os.path.exists(file_path):
        print(f"Row {row_number:02d} ({ticker_name}): Data file missing. Creating N/A template...")
        generate_na_sparkline(full_output_path)
        return full_output_path

    try:
        # Read Excel data
        df = pd.read_excel(file_path, sheet_name=sheet_name)

        # Fallback: File exists but sheet is empty
        if df.empty or 'YearMonth' not in df.columns or 'Sentiment_Score' not in df.columns:
            print(f"Row {row_number:02d} ({ticker_name}): Data format invalid. Creating N/A template...")
            generate_na_sparkline(full_output_path)
            return full_output_path

        df_last_6 = df.sort_values('YearMonth').tail(6).copy()

        # Smooth empty tracking points
        df_last_6['Sentiment_Score'] = df_last_6['Sentiment_Score'].ffill()
        month_labels = pd.to_datetime(df_last_6['YearMonth']).dt.strftime('%b')

        # Narrow Layout (1.8 inches wide)
        plt.figure(figsize=(1.8, 0.8))

        # Plot profile using Light Blue (#00bfff)
        plt.plot(month_labels, df_last_6['Sentiment_Score'],
                 marker='o', markersize=3.5, linewidth=1.2, color='#00bfff')

        # Numbers on ALL dots using White (#ffffff)
        for i, score in enumerate(df_last_6['Sentiment_Score']):
            if pd.notna(score):
                # ALTERNATING OFFSET: Odd indexes go higher, even indexes go lower
                y_offset = 7 if (i % 2 == 0) else 3

                plt.annotate(str(int(score)),
                             (month_labels.iloc[i], df_last_6['Sentiment_Score'].iloc[i]),
                             textcoords="offset points", xytext=(0, y_offset),
                             ha='center', fontsize=6.5, fontweight='bold', color='#ffffff')

                # If this is the latest dot, add the month label below it
                if i == len(df_last_6) - 1:
                    plt.annotate(str(month_labels.iloc[i]),
                                 (month_labels.iloc[i], df_last_6['Sentiment_Score'].iloc[i]),
                                 textcoords="offset points", xytext=(0, -11),
                                 ha='center', fontsize=7, fontweight='bold', color='#ffffff')

        # Safe tracking layout limits
        plt.ylim(-4, 14)
        plt.axis('off')
        plt.tight_layout(pad=0)

        # Saved transparently to inherit your dashboard's black background
        plt.savefig(full_output_path, dpi=200, bbox_inches='tight', transparent=True)
        plt.close()
        return full_output_path

    except Exception as e:
        # Fallback: General parsing errors
        print(f"Row {row_number:02d} ({ticker_name}): Error processing file. Creating N/A template... Details: {e}")
        generate_na_sparkline(full_output_path)
        plt.close()
        return full_output_path


def process_technical_watchlist():
    """
    Master function that reads the tickers from TECHNICAL.xlsx, adjusts names
    to the '_data' suffix format, and loops through to generate dark-mode sparklines.
    """
    technical_file_path = config.TECHNICAL_FILE
    newsbank_dir = config.NEWSWEB_DIR

    if not os.path.exists(technical_file_path):
        print(f"Error: The technical master file could not be found at: {technical_file_path}")
        return

    tech_df = pd.read_excel(technical_file_path)

    if 'Ticker' not in tech_df.columns:
        print("Error: Could not find a column named 'Ticker' in TECHNICAL.xlsx.")
        return

    tickers = tech_df['Ticker'].dropna().tolist()
    print(f"Loaded {len(tickers)} tickers from TECHNICAL.xlsx. Running row processor...")

    for index, raw_ticker in enumerate(tickers, start=1):
        clean_name = str(raw_ticker).split('.')[0].strip()
        target_filename = f"{clean_name}_data.xlsx"
        full_excel_path = os.path.join(newsbank_dir, target_filename)

        saved_img_path = generate_row_sparkline(full_excel_path, row_number=index, ticker_name=clean_name)

        if saved_img_path:
            print(f"Processed row {index:02d} ({raw_ticker}) -> Result: {os.path.basename(saved_img_path)}")


if __name__ == "__main__":
    process_technical_watchlist()