import os
import json
import requests

VERCEL_BLOB_URL = "https://blob.vercel-storage.com/upload"
API_MOVIES_URL = "https://mkvking-scraper.vercel.app/api/movies"  # <-- update this
BLOB_READ_WRITE_TOKEN = os.getenv("BLOB_READ_WRITE_TOKEN")  # from .env.local

def fetch_movies():
    """ Fetch movies from the deployed /api/movies endpoint """
    response = requests.get(API_MOVIES_URL)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch movies: {response.status_code}")
        return None

def upload_to_vercel_blob(file_path):
    """ Upload a local file to Vercel Blob """
    headers = {
        "Authorization": f"Bearer {BLOB_READ_WRITE_TOKEN}"
    }
    files = {
        "file": open(file_path, "rb")
    }
    response = requests.post(VERCEL_BLOB_URL, headers=headers, files=files)

    if response.status_code == 200:
        print("Successfully uploaded to Vercel Blob")
        print(response.json())
    else:
        print(f"Failed to upload to Vercel Blob: {response.status_code}")
        print(response.text)

def main():
    movies_data = fetch_movies()
    if not movies_data:
        return

    # Save the movies data into a local file
    with open("movies.json", "w", encoding="utf-8") as f:
        json.dump(movies_data, f, ensure_ascii=False, indent=4)

    # Upload to Vercel Blob
    upload_to_vercel_blob("movies.json")

if __name__ == "__main__":
    main()
