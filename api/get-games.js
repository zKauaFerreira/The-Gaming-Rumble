export default async function handler(req, res) {
  try {
    const response = await fetch('https://mkuqgpwafiakxxi1.public.blob.vercel-storage.com/games.json');
    if (!response.ok) {
      throw new Error(`Failed to fetch: ${response.statusText}`);
    }
    const gamesData = await response.json();

    res.status(200).json(gamesData);
  } catch (error) {
    console.error('Error fetching games data:', error);
    res.status(500).json({ error: error.message });
  }
}

export const config = {
  api: {
    bodyParser: false,
  },
};