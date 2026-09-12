import axios, { type InternalAxiosRequestConfig } from 'axios';

const client = axios.create({
  baseURL: 'http://127.0.0.1:8000/api',
});

// Interceptor to add auth token
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default client;
