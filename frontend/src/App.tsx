import type { ReactNode } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';

import { AppLayout } from './components/layout/AppLayout';
import { ConsentPage } from './features/auth/ConsentPage';
import { ForgotPasswordPage } from './features/auth/ForgotPasswordPage';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { ResetPasswordPage } from './features/auth/ResetPasswordPage';
import { HomePage } from './features/home/HomePage';
import { NewProjectPage } from './features/projects/NewProjectPage';
import { ProjectPage } from './features/projects/ProjectPage';
import { ProjectsPage } from './features/projects/ProjectsPage';
import { SettingsPage } from './features/settings/SettingsPage';
import { ExplorePage } from './features/community/ExplorePage';
import { GroupPage } from './features/community/GroupPage';
import { GroupsPage } from './features/community/GroupsPage';
import { RoutesPage } from './features/routing/RoutesPage';
import { ErrorsPage } from './features/errors/ErrorsPage';
import { AccessPage } from './features/iam/AccessPage';
import { MarketPage } from './features/templates/MarketPage';
import { WorkspacesPage } from './features/workspaces/WorkspacesPage';
import { ApisPage } from './features/apidocs/ApisPage';
import { ChecksPage } from './features/monitoring/ChecksPage';
import { QueuesPage } from './features/queues/QueuesPage';
import { DatabasesPage } from './features/databases/DatabasesPage';
import { FunctionsPage } from './features/functions/FunctionsPage';
import { AppsPage } from './features/apps/AppsPage';
import { BucketPage } from './features/storage/BucketPage';
import { StoragePage } from './features/storage/StoragePage';
import { ProfilePage } from './features/community/ProfilePage';
import { ThemeProvider } from './theme/ThemeProvider';

export function App(): ReactNode {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/password/forgot" element={<ForgotPasswordPage />} />
          <Route path="/password/reset" element={<ResetPasswordPage />} />
          <Route path="/oauth/consent" element={<ConsentPage />} />
          <Route element={<AppLayout />}>
            <Route index element={<HomePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/new" element={<NewProjectPage />} />
            <Route path="/explore" element={<ExplorePage />} />
            <Route path="/groups" element={<GroupsPage />} />
            <Route path="/groups/:slug" element={<GroupPage />} />
            <Route path="/apps" element={<AppsPage />} />
            <Route path="/functions" element={<FunctionsPage />} />
            <Route path="/databases" element={<DatabasesPage />} />
            <Route path="/queues" element={<QueuesPage />} />
            <Route path="/routes" element={<RoutesPage />} />
            <Route path="/checks" element={<ChecksPage />} />
            <Route path="/errors" element={<ErrorsPage />} />
            <Route path="/apis" element={<ApisPage />} />
            <Route path="/access" element={<AccessPage />} />
            <Route path="/workspaces" element={<WorkspacesPage />} />
            <Route path="/market" element={<MarketPage />} />
            <Route path="/storage" element={<StoragePage />} />
            <Route path="/storage/:name" element={<BucketPage />} />
            {/* A profile sits at the root too, so /bartek is a page. */}
            <Route path="/:login" element={<ProfilePage />} />
            {/* A project sits at the root, the way Git users expect. */}
            <Route path="/:owner/:slug" element={<ProjectPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
