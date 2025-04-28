import os
import json
import requests
import asyncio
from vercel_blob import put  # ✅ Import the SDK

API_MOVIES_URL = "https://mkvking-scraper.vercel.app/api/movies"  # <-- update if needed

def fetch_movies():
    """ Fetch movies from the deployed /api/movies endpoint """
    response = requests.get(API_MOVIES_URL)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch movies: {response.status_code}")
        return None

async def upload_to_vercel_blob(file_path):
    """ Upload a local file to Vercel Blob using Vercel Blob SDK """
    with open(file_path, "rb") as f:
        data = f.read()

    blob = await put("movies.json", data)  # <-- Just this! No manual Authorization header needed
    print("Successfully uploaded to Vercel Blob")
    print(blob)

async def main():
    movies_data = fetch_movies()
    if not movies_data:
        return

    # Save the movies data into a local file
    with open("movies.json", "w", encoding="utf-8") as f:
        json.dump(movies_data, f, ensure_ascii=False, indent=4)

    # Upload to Vercel Blob
    await upload_to_vercel_blob("movies.json")

if __name__ == "__main__":
    asyncio.run(main())
