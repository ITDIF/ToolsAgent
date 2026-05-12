import React, { createContext, useContext, useState, useCallback } from 'react'
import { type Theme, type ThemeName, THEME_NAMES, getTheme } from './theme.js'

interface ThemeContextValue {
  theme: Theme
  themeName: ThemeName
  setThemeName: (name: ThemeName) => void
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: getTheme('dark'),
  themeName: 'dark',
  setThemeName: () => {},
})

export function ThemeProvider({
  initialTheme,
  children,
}: {
  initialTheme: ThemeName
  children: React.ReactNode
}) {
  const [themeName, setThemeName] = useState<ThemeName>(initialTheme)
  const theme = getTheme(themeName)

  const value = useCallback(() => ({
    theme,
    themeName,
    setThemeName,
  }), [theme, themeName])

  return (
    <ThemeContext.Provider value={value()}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext)
}

export { type ThemeName, THEME_NAMES }
