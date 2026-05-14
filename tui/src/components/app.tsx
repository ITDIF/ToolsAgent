import React from 'react'
import { TypedEventBus } from '../bridge/event-bus.js'
import { TuiClient } from '../bridge/tui-client.js'
import { ThemeProvider } from '../theme/context.js'
import { UiStoreProvider } from '../store/ui-store.js'
import { MessageStoreProvider } from '../store/message-store.js'
import { EventSubscriber } from './event-subscriber.js'
import { REPL } from './repl.js'
import type { ThemeName } from '../theme/theme.js'

export function App({
  bus,
  client,
  initialTheme,
  terminalMode,
}: {
  bus: TypedEventBus
  client: TuiClient
  initialTheme: ThemeName
  terminalMode: 'full' | 'fallback'
}) {
  return (
    <ThemeProvider initialTheme={initialTheme}>
      <UiStoreProvider>
        <MessageStoreProvider>
          <EventSubscriber bus={bus}>
            <REPL client={client} hasRawMode={true} />
          </EventSubscriber>
        </MessageStoreProvider>
      </UiStoreProvider>
    </ThemeProvider>
  )
}
