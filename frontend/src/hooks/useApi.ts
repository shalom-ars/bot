import { useState, useEffect } from 'react';
import client from '../api/client';

export function useApi<T>(endpoint: string, defaultValue: T) {
  const [data, setData] = useState<T>(defaultValue);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    client.get(endpoint)
      .then((res) => {
        if (isMounted) {
          setData(res.data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          if (err.response) {
            setError(`API Error: ${err.response.status} - ${err.response.data?.detail || err.response.statusText}`);
          } else if (err.request) {
            setError('REQUEST TIMEOUT: CHECK BACKEND CONNECTION');
          } else {
            setError(`Error: ${err.message}`);
          }
          setLoading(false);
        }
      });

    return () => { isMounted = false; };
  }, [endpoint]);

  return { data, loading, error };
}
