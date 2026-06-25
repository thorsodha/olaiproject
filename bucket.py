import os
from google.cloud import storage


def process_excel_file(bucket_name='olaiproject_price_data', file_path='pricing_folder/data.xlsx'):
    # Initialise client (automatically routes to the emulator via env variable)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_path)

    # Flatten the path for local container storage (extracts 'data.xlsx')
    local_filename = file_path.split('/')[-1]
    local_path = f'/tmp/{local_filename}'

    # 1. Download file if it exists
    if blob.exists():
        blob.download_to_filename(local_path)
        print(f"Successfully downloaded {file_path} from {bucket_name}")
    else:
        print(f"File {file_path} not found in {bucket_name}. Simulating a new file creation.")
        # Create a mock file for testing since it's missing
        with open(local_path, 'w') as f:
            f.write("Mock Excel Data")

    # --- Your processing logic happens here ---

    # 2. Upload file back to the simulated folder
    blob.upload_from_filename(local_path)
    print(f"Successfully uploaded {file_path} back to {bucket_name}")


if __name__ == '__main__':
    process_excel_file()