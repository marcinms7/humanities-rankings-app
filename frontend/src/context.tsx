import { createContext, useContext } from 'react'
import type { User } from './types'

export type AppContextValue = {
  user: User | null; version: number; reload: () => void; setUser: (user: User | null) => void;
  notify: (message: string, error?: boolean) => void; requireLogin: () => boolean;
  mutate: (operation: () => Promise<unknown>, message?: string) => Promise<boolean>;
}
export const AppContext = createContext<AppContextValue>(null!)
export const useApp = () => useContext(AppContext)
