import api from './client'

export async function fetchLeagueTendencies() {
  const { data } = await api.get('/league/tendencies')
  return data
}
