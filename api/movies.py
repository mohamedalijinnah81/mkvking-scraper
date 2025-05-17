from flask import Flask, request, jsonify
import requests
import sys
import re
from bs4 import BeautifulSoup
import cloudinary
import cloudinary.uploader
from urllib.parse import urlparse
import os
import concurrent.futures
import time
from functools import lru_cache
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TMDB_BEARER_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI2YjljMGQ1ZTJhYTk0OTVjZTQzZmY4MzQyNTNjYmRjOCIsIm5iZiI6MS43NDYzNDIyMDIyNTQwMDAyZSs5LCJzdWIiOiI2ODE3MTEzYWVlOGFlODcwZWQ4NGNmZDEiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6rfRRKkn7eqsUv1VwIifWCehwT3f-YwK-6KV7x1kfx8'

# Configure Cloudinary
cloudinary.config(
    cloud_name='dshmvyjgf',
    api_key='832587935596469',
    api_secret='5DPNHukMTr1agmI0nowrDTJuHRQ'
)

# Request headers - define once and reuse
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Session for connection pooling
session = requests.Session()
session.headers.update(HEADERS)

# Base URLs
BASE_URL = "https://a.mkvking.homes/"
AJAX_URL = f"{BASE_URL}wp-admin/admin-ajax.php"

def clean_movie_name(name):
    """Remove a trailing year in parentheses OR without, only if it's at the end"""
    return re.sub(r'\s*(\(\d{4}\)|\d{4})\s*$', '', name).strip()

@lru_cache(maxsize=128)
def fetch_tmdb_images(name, year=None):
    """Fetch movie images from TMDB API with caching for performance"""
    try:
        base_url = "https://api.themoviedb.org/3/search/movie"
        headers = {
            "Authorization": f"Bearer {TMDB_BEARER_TOKEN}",
            "accept": "application/json"
        }

        def get_results(params):
            response = session.get(base_url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("results", [])
            return []

        # Try with year
        params = {"query": name}
        if year:
            params["primary_release_year"] = year
        results = get_results(params)

        # Retry without year
        if not results and year:
            results = get_results({"query": name})

        if results:
            movie = results[0]
            poster_path = movie.get("poster_path")
            backdrop_path = movie.get("backdrop_path")
            return {
                "tmdb_poster": f"https://image.tmdb.org/t/p/w780{poster_path}" if poster_path else None,
                "tmdb_backdrop": f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None,
            }

    except Exception as e:
        logger.error(f"Error fetching TMDB images for '{name} ({year})': {e}")

    return {"tmdb_poster": None, "tmdb_backdrop": None}

@lru_cache(maxsize=64)
def upload_to_cloudinary(image_url):
    """Upload mkvking poster images to Cloudinary with caching"""
    try:
        # Extract filename from image_url
        parsed_url = urlparse(image_url)
        filename = os.path.basename(parsed_url.path)
        name_without_ext = os.path.splitext(filename)[0]

        # Check if we've already uploaded this image (by URL as key)
        upload_result = cloudinary.uploader.upload(
            image_url,
            folder="cinebucket/posters",
            public_id=name_without_ext,
            overwrite=True,
            resource_type="image"
        )
        return upload_result.get('secure_url')
    except Exception as e:
        logger.error(f"Cloudinary upload failed for {image_url}: {e}")
        return None

def extract_post_id(soup):
    """Extract post ID from article tag"""
    article_tag = soup.find("article")
    if article_tag:
        article_id = article_tag.get("id")
        if article_id and article_id.startswith("post-"):
            return article_id.replace("post-", "")
    return None

def fetch_iframe_src(post_id):
    """Fetch iframe source via AJAX request"""
    if not post_id:
        return None
    
    form_data = {
        "action": "muvipro_player_content",
        "tab": "player2",
        "post_id": post_id
    }
    
    try:
        ajax_response = session.post(AJAX_URL, data=form_data, timeout=10)
        if ajax_response.status_code == 200:
            iframe_soup = BeautifulSoup(ajax_response.text, "html.parser")
            iframe_tag = iframe_soup.find("iframe")
            if iframe_tag and iframe_tag.get("src"):
                return iframe_tag.get("src")
    except Exception as e:
        logger.error(f"Error fetching iframe for post {post_id}: {e}")
    
    return None

def parse_movie_page(soup, movie_url):
    """Parse the HTML soup object to extract movie details"""
    movie_data = {
        "url": movie_url,
        "poster": None,
        "backdrop_path": None,
        "poster_alt": None,
        "name": None,
        "genre": [],
        "tags": [],
        "quality": None,
        "year": None,
        "duration": None,
        "rating": None,
        "iframe_src": None,
        "description": None,
        "release_date": None,
        "language": None,
        "download_links": []
    }
    
    # Extract poster image
    content_thumbnail = soup.find("figure", class_="pull-left")
    if content_thumbnail:
        img_tag = content_thumbnail.find("img")
        if img_tag:
            raw_src = img_tag.get("src")
            if raw_src:
                clean_src = re.sub(r'-\d+x\d+(?=\.(jpg|jpeg|png))', '', raw_src)
                movie_data["poster"] = clean_src
                movie_data["poster_alt"] = img_tag.get("alt")

    # Extract movie title
    entry_title = soup.find("h1", class_="entry-title")
    if entry_title:
        movie_data["name"] = entry_title.text.strip()

    # Extract genres
    gmr_movie_on = soup.find("span", class_="gmr-movie-genre")
    if gmr_movie_on:
        for a in gmr_movie_on.find_all("a", rel="category tag"):
            movie_data["genre"].append(a.text.strip())

    # Extract quality
    gmr_movie_quality = soup.find("span", class_="gmr-movie-quality")
    if gmr_movie_quality:
        a_tag = gmr_movie_quality.find("a")
        if a_tag:
            movie_data["quality"] = a_tag.text.strip()

    # Extract duration
    duration_span = soup.find("span", class_="gmr-movie-runtime")
    if duration_span:
        movie_data["duration"] = duration_span.text.strip()

    # Extract rating
    rating_value_span = soup.find("span", itemprop="ratingValue")
    if rating_value_span:
        try:
            movie_data["rating"] = float(rating_value_span.text.strip())
        except (ValueError, TypeError):
            pass

    # Extract description
    description_div = soup.find("div", class_="entry-content entry-content-single", itemprop="description")
    if description_div:
        first_paragraph = description_div.find("p")
        if first_paragraph:
            movie_data["description"] = first_paragraph.text.strip()

    # Extract release date and year
    time_tag = soup.find("time")
    if time_tag:
        movie_data["release_date"] = time_tag.text.strip()
        release_date_parts = movie_data["release_date"].split()
        if len(release_date_parts) > 2:
            try:
                movie_data["year"] = int(release_date_parts[-1])
            except ValueError:
                pass

    # Extract language
    language_span = soup.find("span", property="inLanguage")
    if language_span:
        movie_data["language"] = language_span.text.strip()

    # Extract tags
    tags_span = soup.find("span", class_="tags-links")
    if tags_span:
        for a in tags_span.find_all("a", rel="tag"):
            movie_data["tags"].append(a.text.strip())

    # Extract download links
    download_div = soup.find("div", id="download")
    if download_div:
        for li in download_div.find_all("li"):
            a_tag = li.find("a")
            if a_tag:
                # Remove nested spans to get clean text
                for span in a_tag.find_all("span"):
                    span.extract()
                movie_data["download_links"].append({
                    "label": a_tag.text.strip(),
                    "url": a_tag.get("href")
                })
    
    return movie_data

def fetch_movie_details(movie_url):
    """Fetch full movie details from a movie's page with improved error handling"""
    try:
        start_time = time.time()
        response = session.get(movie_url, timeout=15)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch movie: {movie_url}, Status: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Parse movie data from HTML
        movie_data = parse_movie_page(soup, movie_url)
        
        # Extract post_id and fetch iframe source
        post_id = extract_post_id(soup)
        movie_data["iframe_src"] = fetch_iframe_src(post_id)
        
        # Get TMDB images if we have a movie name
        if movie_data["name"]:
            movie_name = clean_movie_name(movie_data["name"])
            tmdb_images = fetch_tmdb_images(movie_name, movie_data["year"])
            
            # Use TMDB poster if available, otherwise use and possibly upload site poster
            if tmdb_images["tmdb_poster"]:
                movie_data["poster"] = tmdb_images["tmdb_poster"]
            elif movie_data["poster"] and "mkvking" in movie_data["poster"]:
                cloudinary_url = upload_to_cloudinary(movie_data["poster"])
                if cloudinary_url:
                    movie_data["poster"] = cloudinary_url
            
            # Add backdrop from TMDB
            movie_data["backdrop_path"] = tmdb_images["tmdb_backdrop"]
        
        logger.info(f"Movie fetched in {time.time() - start_time:.2f}s: {movie_data['name']}")
        return movie_data
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching movie: {movie_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching movie: {movie_url}, Error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching movie: {movie_url}, Error: {e}")
    
    return None

def get_movie_urls_from_page(page_url):
    """Extract all movie URLs from a page"""
    try:
        response = session.get(page_url, timeout=15)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch Page {page_url}: Status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        main_load_div = soup.find("div", id="gmr-main-load")
        if not main_load_div:
            logger.warning(f"No movie container found on {page_url}")
            return []

        articles = main_load_div.find_all("article")
        urls = []

        for article in articles:
            content_thumbnail = article.find("h2", class_="entry-title")
            if content_thumbnail:
                a_tag = content_thumbnail.find("a")
                if a_tag and a_tag.get("href"):
                    urls.append(a_tag.get("href"))

        return urls
    except Exception as e:
        logger.error(f"Error getting movie URLs from page {page_url}: {e}")
        return []

def scrape_movies_from_page(page_number, max_workers=8):
    """Scrape movies from a specific page number using concurrent requests"""
    if page_number == 1:
        page_url = BASE_URL
    else:
        page_url = f"{BASE_URL}page/{page_number}/"

    logger.info(f"Scraping Page {page_number} - URL: {page_url}")
    
    # First get all movie URLs from the page
    movie_urls = get_movie_urls_from_page(page_url)
    logger.info(f"Found {len(movie_urls)} movie URLs on page {page_number}")
    
    if not movie_urls:
        return []
    
    # Then fetch movie details concurrently
    movies = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_movie_details, url): url for url in movie_urls}
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_url)):
            url = future_to_url[future]
            try:
                movie_details = future.result()
                if movie_details:
                    movie_details["id"] = i + 1  # Set ID based on order of completion
                    movies.append(movie_details)
            except Exception as e:
                logger.error(f"Error processing {url}: {e}")
    
    logger.info(f"Completed scraping Page {page_number}, Total movies collected: {len(movies)}")
    return movies

@app.route('/api/movies', methods=['POST'])
def get_movies_from_page():
    """API endpoint to fetch movies from a specific page number"""
    start_time = time.time()
    data = request.get_json()

    if not data or 'page' not in data:
        return jsonify({"error": "Missing 'page' parameter in request body"}), 400

    try:
        page = int(data['page'])
    except ValueError:
        return jsonify({"error": "'page' must be an integer"}), 400

    if page < 1:
        return jsonify({"error": "Page number must be greater than or equal to 1"}), 400

    # Extract optional max_workers parameter with a default value
    max_workers = data.get('max_workers', 8)
    try:
        max_workers = int(max_workers)
        # Limit max_workers to a reasonable range
        max_workers = max(1, min(max_workers, 16))
    except (ValueError, TypeError):
        max_workers = 8

    movies = scrape_movies_from_page(page, max_workers)
    execution_time = time.time() - start_time

    return jsonify({
        "page": page,
        "movies": movies,
        "count": len(movies),
        "execution_time_seconds": round(execution_time, 2)
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()})
