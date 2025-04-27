// api/run-cron.js
import { put } from '@vercel/blob';
import fetch from 'node-fetch';

export default async function handler(req, res) {
  try {
    // 1. Fetch your API
    const response = await fetch('https://mkvking-scraper.vercel.app/api/movies');

    if (!response.ok) {
      throw new Error(`Failed to fetch API: ${response.status}`);
    }

    const movies = await response.json();

    // 2. Upload to Vercel Blob
    const blob = await put('movies.json', JSON.stringify(movies), {
      access: 'public',  // or 'private'
    });

    console.log('✅ Successfully uploaded to:', blob.url);

    res.status(200).json({ success: true, url: blob.url });

  } catch (error) {
    console.error('❌ Error:', error);
    res.status(500).json({ error: error.message });
  }
}
