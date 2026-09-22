import { useState, type ReactNode } from 'react';
import { Outlet } from 'react-router';

import { AccountContext } from '../../features/account/AccountContext';
import { useCurrentAccount } from '../../features/account/useCurrentAccount';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

/** Shell shared by every signed-in page: top bar, side menu, content. */
export function AppLayout(): ReactNode {
  const [menuOpen, setMenuOpen] = useState(false);
  const account = useCurrentAccount();

  return (
    <AccountContext.Provider value={account}>
      <div className="min-h-screen bg-app text-app">
        <TopBar
          account={account}
          menuOpen={menuOpen}
          onToggleMenu={() => {
            setMenuOpen((open) => !open);
          }}
        />
        {/* The row fills the viewport below the top bar so the side menu reaches the bottom. */}
        <div className="flex min-h-[calc(100vh-3.5rem)]">
          <Sidebar
            open={menuOpen}
            onClose={() => {
              setMenuOpen(false);
            }}
          />
          <main className="min-w-0 flex-1">
            <Outlet />
          </main>
        </div>
      </div>
    </AccountContext.Provider>
  );
}
