import axios from 'axios'

export const api = axios.create({
  baseURL: '/api/v1',
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('eb_token') || window._authToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})
