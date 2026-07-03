import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Bell, LayoutGrid, LogOut, Settings as SettingsIcon, ShieldCheck, Tag } from "lucide-react";

import { Button } from "../components/ui/button";
import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";

/**
 * AppShell wraps owner-facing routes (dashboard, settings, tag edit, etc.).
 * Lightweight top nav + a bottom tab bar on mobile for thumb-friendly nav.
 */
export function AppShell() {
    const { logout, user } = useAuth();
    const { t } = useI18n();
    const navigate = useNavigate();

    const onLogout = async () => {
        await logout();
        navigate("/", { replace: true });
    };

    return (
        <div className="min-h-screen flex flex-col">
            <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <div className="mx-auto max-w-6xl px-4 sm:px-8 h-16 flex items-center justify-between gap-3">
                    <Link
                        to="/dashboard"
                        className="flex items-center gap-2 font-display font-black text-xl tracking-tight"
                        data-testid="brand-link"
                    >
                        <Tag className="h-5 w-5 text-accent" strokeWidth={2.5} />
                        <span>
                            Info-<span className="text-accent">Tag</span>
                        </span>
                    </Link>
                    <nav className="hidden md:flex items-center gap-1 text-sm">
                        <NavTab to="/dashboard" icon={<LayoutGrid className="h-4 w-4" />} label={t("common.dashboard")} testId="nav-dashboard" />
                        <NavTab to="/inbox" icon={<Bell className="h-4 w-4" />} label={t("common.inbox")} testId="nav-inbox" />
                        <NavTab to="/settings" icon={<SettingsIcon className="h-4 w-4" />} label={t("common.settings")} testId="nav-settings" />
                        {user?.role === "admin" && (
                            <NavTab to="/admin" icon={<ShieldCheck className="h-4 w-4" />} label="Admin" testId="nav-admin" />
                        )}
                    </nav>
                    <div className="flex items-center gap-1">
                        <LanguageSwitcher compact />
                        <ThemeToggle />
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={onLogout}
                            data-testid="logout-button"
                            className="gap-2"
                        >
                            <LogOut className="h-4 w-4" />
                            <span className="hidden sm:inline">{t("common.sign_out")}</span>
                        </Button>
                    </div>
                </div>
            </header>
            <main className="flex-1 pb-20 md:pb-10">
                <div className="mx-auto max-w-6xl px-4 sm:px-8 py-6 sm:py-10">
                    <Outlet />
                </div>
            </main>
            <BottomTabs t={t} />
            {user && (
                <div className="sr-only" data-testid="signed-in-as">
                    {user.email}
                </div>
            )}
        </div>
    );
}

function NavTab({ to, icon, label, testId }) {
    return (
        <NavLink
            to={to}
            data-testid={testId}
            className={({ isActive }) =>
                [
                    "inline-flex items-center gap-2 px-3 py-2 rounded-full transition-colors",
                    isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-foreground/70 hover:text-foreground hover:bg-muted",
                ].join(" ")
            }
        >
            {icon}
            <span>{label}</span>
        </NavLink>
    );
}

function BottomTabs({ t }) {
    const item =
        "flex flex-1 flex-col items-center justify-center gap-1 py-2 text-xs font-medium";
    return (
        <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 border-t bg-background/95 backdrop-blur">
            <div className="grid grid-cols-3">
                <NavLink to="/dashboard" data-testid="tab-dashboard" className={({ isActive }) => `${item} ${isActive ? "text-accent" : "text-muted-foreground"}`}>
                    <LayoutGrid className="h-5 w-5" />
                    {t("common.dashboard")}
                </NavLink>
                <NavLink to="/inbox" data-testid="tab-inbox" className={({ isActive }) => `${item} ${isActive ? "text-accent" : "text-muted-foreground"}`}>
                    <Bell className="h-5 w-5" />
                    {t("common.inbox")}
                </NavLink>
                <NavLink to="/settings" data-testid="tab-settings" className={({ isActive }) => `${item} ${isActive ? "text-accent" : "text-muted-foreground"}`}>
                    <SettingsIcon className="h-5 w-5" />
                    {t("common.settings")}
                </NavLink>
            </div>
        </nav>
    );
}
