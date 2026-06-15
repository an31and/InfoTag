import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AuthCallback, AuthProvider, ProtectedRoute, useAuth } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { ThemeProvider } from "@/lib/theme";

import { AppShell } from "@/components/AppShell";
import { Toaster } from "@/components/ui/sonner";

import LandingPage from "@/pages/Landing";
import AuthPage from "@/pages/Auth";
import DashboardPage from "@/pages/Dashboard";
import TagEditPage from "@/pages/TagEdit";
import TagQRPage from "@/pages/TagQR";
import TagMedicalPage from "@/pages/TagMedical";
import InboxPage from "@/pages/Inbox";
import SettingsPage from "@/pages/Settings";
import { FinderRedirect } from "@/pages/FinderRedirect";
import ClaimPage from "@/pages/Claim";
import { MedicalDisclaimerPage, PrivacyPage, TermsPage } from "@/pages/Legal";

/**
 * AppRouter — handle the Emergent Google `session_id` fragment FIRST, before
 * any other route renders.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 * THIS BREAKS THE AUTH.
 */
function AppRouter() {
    const location = useLocation();
    if (typeof window !== "undefined" && window.location.hash?.includes("session_id=")) {
        return <AuthCallback />;
    }
    return (
        <Routes>
            {/* Public */}
            <Route path="/" element={<HomeOrDashboard />} />
            <Route path="/login" element={<AuthPage mode="login" />} />
            <Route path="/signup" element={<AuthPage mode="signup" />} />
            <Route path="/auth/callback" element={<AuthCallback />} />

            <Route path="/tag/:slug" element={<FinderRedirect />} />
            <Route path="/claim/:slug" element={<ClaimPage />} />

            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/medical-disclaimer" element={<MedicalDisclaimerPage />} />

            {/* Owner area */}
            <Route
                element={
                    <ProtectedRoute>
                        <AppShell />
                    </ProtectedRoute>
                }
            >
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/inbox" element={<InboxPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/tags/new" element={<TagEditPage />} />
                <Route path="/tags/:id" element={<TagEditPage />} />
                <Route path="/tags/:id/qr" element={<TagQRPage />} />
                <Route path="/tags/:id/medical" element={<TagMedicalPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

function HomeOrDashboard() {
    const { user, loading } = useAuth();
    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center text-muted-foreground">
                <div className="animate-pulse-soft">Loading…</div>
            </div>
        );
    }
    return user ? <Navigate to="/dashboard" replace /> : <LandingPage />;
}

export default function App() {
    return (
        <ThemeProvider>
            <I18nProvider>
                <BrowserRouter>
                    <AuthProvider>
                        <AppRouter />
                        <Toaster position="top-center" richColors />
                    </AuthProvider>
                </BrowserRouter>
            </I18nProvider>
        </ThemeProvider>
    );
}
