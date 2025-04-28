// api/scrape.js

import fetch from 'node-fetch';
import { put } from '@vercel/blob'; // <-- this is the Vercel Blob SDK
import { Readable } from 'stream';

export default async function handler(req, res) {
    const bearerToken = 'EQ2KSf4i49LwaT5DyLKfRXrj'; // Your bearer token

    async function scrapeAllMovies(totalPages = 20) {
        const allMovies = [];

        for (let page = 1; page <= totalPages; page++) {
            try {
                const response = await fetch('https://mkvking-scraper.vercel.app/api/movies', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${bearerToken}` 
                    },
                    body: JSON.stringify({ page })
                });

                if (!response.ok) {
                    console.error(`Failed to fetch page ${page}: ${response.status}`);
                    continue;
                }

                const data = await response.json();
                if (data.movies && Array.isArray(data.movies)) {
                    allMovies.push(...data.movies);
                    console.log(`Page ${page}: Added ${data.movies.length} movies (Total so far: ${allMovies.length})`);
                }
            } catch (error) {
                console.error(`Error fetching page ${page}:`, error);
            }
        }

        return allMovies;
    }

    try {
        const movies = await scrapeAllMovies(1282);

        // Convert movies array to JSON
        const jsonContent = JSON.stringify({ movies }, null, 2);

        // Upload the JSON to Vercel Blob
        const blob = await put('movies.json', Readable.from([jsonContent]), {
            access: 'public', // Or 'private' depending on your choice
        });

        console.log('✅ Upload successful:', blob.url);

        return res.status(200).json({
            success: true,
            message: 'Movies scraped and uploaded successfully!',
            uploadedUrl: blob.url, // You can save this URL somewhere if needed
        });

    } catch (error) {
        console.error('Scraping and upload failed:', error);
        return res.status(500).json({
            success: false,
            error: error.message,
        });
    }
}
