import requests
import os

def download_gsm8k():
    print("Downloading GSM8K Test set directly...")
    # URL for the raw parquet file of the test split
    url = "https://huggingface.co/datasets/openai/gsm8k/resolve/main/main/test-00000-of-00001.parquet"
    
    target = "gsm8k_test.parquet"
    
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(target, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Success! Saved to {target}")
        
        # Try to convert to json for easier use if pandas is available
        try:
            import pandas as pd
            df = pd.read_parquet(target)
            df.to_json("gsm8k_test.json", orient="records", indent=2)
            print(f"Converted to gsm8k_test.json ({len(df)} tasks)")
        except ImportError:
            print("Pandas not found. Keeping parquet file.")
            
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    download_gsm8k()
