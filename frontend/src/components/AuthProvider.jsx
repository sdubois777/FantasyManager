import { useEffect } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { registerTokenGetter } from '../api/client'

/**
 * Registers the Clerk token getter with the API client.
 * Mount once inside ClerkProvider so axios can attach
 * Bearer tokens to every request automatically.
 */
export default function AuthProvider({ children }) {
  const { getToken, isLoaded } = useAuth()

  useEffect(() => {
    if (isLoaded) {
      registerTokenGetter(() => getToken())
    }
  }, [isLoaded, getToken])

  return children
}
