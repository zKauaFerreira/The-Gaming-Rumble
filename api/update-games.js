import { kv } from '@vercel/kv';

export default async function handler(req, res) {
  const authHeader = req.headers.authorization;
  const cronSecret = process.env.CRON_SECRET;

  if (cronSecret && authHeader !== `Bearer ${cronSecret}`) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const response = await fetch('https://raw.githubusercontent.com/zKauaFerreira/The-Gaming-Rumble/refs/heads/games/online_fix_games.json');
    if (!response.ok) {
      throw new Error(`Failed to fetch: ${response.statusText}`);
    }
    const gamesData = await response.json();

    await kv.set('games', gamesData);

    console.log('Games data updated successfully in Vercel KV!');
    res.status(200).json({ success: true, message: 'Games data updated in Vercel KV.' });
  } catch (error) {
    console.error('Error updating games data:', error);
    res.status(500).json({ success: false, message: error.message });
  }
}

export const config = {
  api: {
    bodyParser: false,
  },
};