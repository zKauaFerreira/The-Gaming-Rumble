import { useState } from 'react';

export default function TestCron() {
  const [secret, setSecret] = useState('');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const testCron = async () => {
    setLoading(true);
    setResult(null);

    try {
      const response = await fetch('/api/update-games', {
        headers: {
          'Authorization': `Bearer ${secret}`
        }
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      setResult({ error: 'Failed to fetch' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">Testar Cron Job</h1>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">
              CRON_SECRET
            </label>
            <input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="Cole seu CRON_SECRET aqui"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <button
            onClick={testCron}
            disabled={loading || !secret}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg font-medium transition-colors"
          >
            {loading ? 'Executando...' : 'Testar Cron Job'}
          </button>

          {result && (
            <div className="mt-6 p-4 bg-gray-800 rounded-lg">
              <h2 className="text-lg font-semibold mb-2">Resultado:</h2>
              <pre className="text-sm overflow-auto">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}