from flask import Flask, request, jsonify
import requests
import sys
import re
from bs4 import BeautifulSoup

app = Flask(__name__)

TMDB_BEARER_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI2YjljMGQ1ZTJhYTk0OTVjZTQzZmY4MzQyNTNjYmRjOCIsIm5iZiI6MS43NDYzNDIyMDIyNTQwMDAyZSs5LCJzdWIiOiI2ODE3MTEzYWVlOGFlODcwZWQ4NGNmZDEiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6rfRRKkn7eqsUv1VwIifWCehwT3f-YwK-6KV7x1kfx8'

def clean_movie_name(name):
    # Remove a trailing year in parentheses OR without, only if it's at the end
    return re.sub(r'\s*(\(\d{4}\)|\d{4})\s*$', '', name).strip()

def fetch_tmdb_images(name, year=None):
    try:
        base_url = "https://api.themoviedb.org/3/search/movie"
        headers = {
            "Authorization": f"Bearer {TMDB_BEARER_TOKEN}",
            "accept": "application/json"
        }

        def get_results(params):
            response = requests.get(base_url, headers=headers, params=params)
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
                "tmdb_poster": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
                "tmdb_backdrop": f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None,
            }

    except Exception as e:
        print(f"Error fetching TMDB images for '{name} ({year})': {e}")
        sys.stdout.flush()

    return {"tmdb_poster": None, "tmdb_backdrop": None}

def fetch_movie_details(movie_url):
    """ Fetch full movie details from a movie's page. """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    response = requests.get(movie_url, headers=headers)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

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

    content_thumbnail = soup.find("figure", class_="pull-left")
    if content_thumbnail:
        img_tag = content_thumbnail.find("img")
        if img_tag:
            raw_src = img_tag.get("src")
            clean_src = re.sub(r'-\d+x\d+(?=\.(jpg|jpeg|png))', '', raw_src)
            movie_data["poster"] = clean_src
            movie_data["poster_alt"] = img_tag.get("alt")

    entry_title = soup.find("h1", class_="entry-title")
    if entry_title:
        movie_data["name"] = entry_title.text.strip()

    gmr_movie_on = soup.find("span", class_="gmr-movie-genre")
    if gmr_movie_on:
        for a in gmr_movie_on.find_all("a", rel="category tag"):
            movie_data["genre"].append(a.text.strip())

    gmr_movie_quality = soup.find("span", class_="gmr-movie-quality")
    if gmr_movie_quality:
        a_tag = gmr_movie_quality.find("a")
        if a_tag:
            movie_data["quality"] = a_tag.text.strip()

    entry_title = soup.find("span", class_="gmr-movie-runtime")
    if entry_title:
        movie_data["duration"] = entry_title.text.strip()

    rating_value_span = soup.find("span", itemprop="ratingValue")
    if rating_value_span:
        movie_data["rating"] = float(rating_value_span.text.strip())

    # Extract post_id from <article id="post-XXXXX">
    article_tag = soup.find("article")
    post_id = None
    if article_tag:
        article_id = article_tag.get("id")  # Example: 'post-149861'
        if article_id and article_id.startswith("post-"):
            post_id = article_id.replace("post-", "")

    # Fetch correct iframe_src via admin-ajax.php
    if post_id:
        ajax_url = "https://a.mkvking.homes/wp-admin/admin-ajax.php"
        form_data = {
            "action": "muvipro_player_content",
            "tab": "player2",
            "post_id": post_id
        }
        ajax_response = requests.post(ajax_url, data=form_data, headers=headers)

        if ajax_response.status_code == 200:
            iframe_soup = BeautifulSoup(ajax_response.text, "html.parser")
            iframe_tag = iframe_soup.find("iframe")
            if iframe_tag and iframe_tag.get("src"):
                movie_data["iframe_src"] = iframe_tag.get("src")

    description_div = soup.find("div", class_="entry-content entry-content-single", itemprop="description")
    if description_div:
        first_paragraph = description_div.find("p")
        if first_paragraph:
            movie_data["description"] = first_paragraph.text.strip()

    time_tag = soup.find("time")
    if time_tag:
        movie_data["release_date"] = time_tag.text.strip()
        release_date_parts = movie_data["release_date"].split()
        if len(release_date_parts) > 2:
            try:
                movie_data["year"] = int(release_date_parts[-1])
            except ValueError:
                pass

    language_span = soup.find("span", property="inLanguage")
    if language_span:
        movie_data["language"] = language_span.text.strip()

    gmr_movie_on = soup.find("span", class_="tags-links")
    if gmr_movie_on:
        for a in gmr_movie_on.find_all("a", rel="tag"):
            movie_data["tags"].append(a.text.strip())

    download_div = soup.find("div", id="download")
    if download_div:
        for li in download_div.find_all("li"):
            a_tag = li.find("a")
            if a_tag:
                for span in a_tag.find_all("span"):
                    span.extract()
                movie_data["download_links"].append({
                    "label": a_tag.text.strip(),
                    "url": a_tag.get("href")
                })

    # Add TMDB poster and backdrop
    if movie_data["name"]:
        movie_name = clean_movie_name(movie_data["name"])
        tmdb_images = fetch_tmdb_images(movie_name, movie_data["year"])
        movie_data["poster"] = tmdb_images["tmdb_poster"] if tmdb_images["tmdb_poster"] else movie_data["poster"]
        movie_data["backdrop_path"] = tmdb_images["tmdb_backdrop"]

    return movie_data

def scrape_movies_from_page(page_number):
    """ Scrape movies from a specific page number. """
    base_url = "https://a.mkvking.homes/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    if page_number == 1:
        page_url = base_url
    else:
        page_url = f"{base_url}page/{page_number}/"

    print(f"Scraping Page {page_number} - URL: {page_url}")
    sys.stdout.flush()

    response = requests.get(page_url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch Page {page_number}: Status {response.status_code}")
        sys.stdout.flush()
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    main_load_div = soup.find("div", id="gmr-main-load")
    if not main_load_div:
        print(f"No movie container found on Page {page_number}")
        sys.stdout.flush()
        return []

    articles = main_load_div.find_all("article")

    movies = []
    movie_id = 1  # You can assign a temporary ID per page

    for article in articles:
        content_thumbnail = article.find("h2", class_="entry-title")
        url = None

        if content_thumbnail:
            a_tag = content_thumbnail.find("a")
            if a_tag:
                url = a_tag.get("href")

        if url:
            movie_details = fetch_movie_details(url)
            if movie_details:
                movie_details["id"] = movie_id
                movies.append(movie_details)
                print(f"Fetched Movie {movie_id}: {movie_details['name']}")
                sys.stdout.flush()
                movie_id += 1

    print(f"Completed scraping Page {page_number}, Total movies collected: {len(movies)}")
    sys.stdout.flush()

    return movies

@app.route('/api/movies', methods=['POST'])
def get_movies_from_page():
    """ API endpoint to fetch movies from a specific page number. """
    data = request.get_json()

    if not data or 'page' not in data:
        return jsonify({"error": "Missing 'page' parameter in request body"}), 400

    try:
        page = int(data['page'])
    except ValueError:
        return jsonify({"error": "'page' must be an integer"}), 400

    if page < 1:
        return jsonify({"error": "Page number must be greater than or equal to 1"}), 400

    movies = scrape_movies_from_page(page)
    return jsonify({
        "page": page,
        "movies": movies
    })
