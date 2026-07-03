/**
 * Auth sub-components.  Extracted from the original 177-line AuthPage so
 * the email/password form, the Google button and the visual side panel
 * stand on their own.
 */
import { Link } from "react-router-dom";
import { Tag } from "lucide-react";

import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

/**
 * Trigger the Emergent Google OAuth flow.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 * THIS BREAKS THE AUTH.
 */
function startGoogleAuth() {
    const redirectUrl = window.location.origin + "/auth/callback";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
}

function GoogleIcon() {
    return (
        <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.75h3.57c2.08-1.92 3.28-4.74 3.28-8.07z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.75c-.99.66-2.25 1.05-3.71 1.05-2.85 0-5.27-1.92-6.13-4.51H2.18v2.84A11 11 0 0 0 12 23z" />
            <path fill="#FBBC05" d="M5.87 14.13a6.62 6.62 0 0 1 0-4.26V7.04H2.18a11 11 0 0 0 0 9.92l3.69-2.83z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.07.56 4.21 1.64l3.16-3.16C17.46 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.04l3.69 2.83C6.73 7.3 9.15 5.38 12 5.38z" />
        </svg>
    );
}

export function GoogleAuthButton({ label }) {
    return (
        <Button
            type="button"
            variant="outline"
            className="w-full h-11 rounded-full gap-2"
            onClick={startGoogleAuth}
            data-testid="google-login-btn"
        >
            <GoogleIcon /> {label}
        </Button>
    );
}

export function AuthVisualPanel({ t }) {
    return (
        <div className="hidden md:flex relative bg-primary text-primary-foreground p-12 flex-col justify-between overflow-hidden">
            <div className="absolute inset-0 bg-grid opacity-10" />
            <Link to="/" className="relative inline-flex items-center gap-2 font-display font-black text-2xl" data-testid="auth-brand">
                <Tag className="h-6 w-6 text-accent" strokeWidth={2.5} />
                Info-<span className="text-accent">Tag</span>
            </Link>
            <div className="relative max-w-md space-y-4">
                <p className="font-display text-3xl font-bold tracking-tight leading-tight">
                    {t("landing.hero_title")}
                </p>
                <p className="text-primary-foreground/80">{t("common.tagline")}</p>
                <p className="text-xs uppercase tracking-widest text-primary-foreground/60">
                    🇮🇳 {t("common.made_in_india")} · {t("common.free_public_service")}
                </p>
            </div>
        </div>
    );
}

export function EmailPasswordForm({
    isSignup,
    t,
    email,
    setEmail,
    password,
    setPassword,
    displayName,
    setDisplayName,
    submitting,
    error,
    onSubmit,
}) {
    let buttonLabel = isSignup ? t("common.sign_up") : t("common.sign_in");
    if (submitting) buttonLabel = t("common.loading");

    return (
        <form onSubmit={onSubmit} className="w-full max-w-sm space-y-5" data-testid={isSignup ? "signup-form" : "login-form"}>
            <div>
                <h1 className="font-display text-3xl font-bold tracking-tight">
                    {isSignup ? t("auth.sign_up_title") : t("auth.sign_in_title")}
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                    {isSignup ? t("auth.sign_up_subtitle") : t("auth.sign_in_subtitle")}
                </p>
            </div>

            <GoogleAuthButton label={t("auth.continue_with_google")} />

            <div className="flex items-center gap-3 text-xs uppercase tracking-widest text-muted-foreground">
                <span className="flex-1 h-px bg-border" />
                {t("auth.or_use_email")}
                <span className="flex-1 h-px bg-border" />
            </div>

            {isSignup && (
                <div className="space-y-1.5">
                    <Label htmlFor="display_name">{t("auth.display_name")}</Label>
                    <Input
                        id="display_name"
                        type="text"
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        placeholder="Anand Lakhera"
                        autoComplete="name"
                        data-testid="register-name-input"
                    />
                </div>
            )}

            <div className="space-y-1.5">
                <Label htmlFor="email">{t("auth.email")}</Label>
                <Input
                    id="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    data-testid={isSignup ? "register-email-input" : "login-email-input"}
                />
            </div>

            <div className="space-y-1.5">
                <Label htmlFor="password">{t("auth.password")}</Label>
                <Input
                    id="password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete={isSignup ? "new-password" : "current-password"}
                    data-testid={isSignup ? "register-password-input" : "login-password-input"}
                />
            </div>

            {error && (
                <div className="text-sm text-destructive" data-testid="auth-error">
                    {error}
                </div>
            )}

            <Button
                type="submit"
                className="w-full h-11 rounded-full"
                disabled={submitting}
                data-testid={isSignup ? "register-submit-button" : "login-submit-button"}
            >
                {buttonLabel}
            </Button>

            <p className="text-sm text-muted-foreground text-center">
                {isSignup ? t("auth.already_have_account") : t("auth.need_account")}{" "}
                {isSignup ? (
                    <Link to="/login" className="text-accent font-medium" data-testid="register-login-link">
                        {t("common.sign_in")}
                    </Link>
                ) : (
                    <Link to="/signup" className="text-accent font-medium" data-testid="login-register-link">
                        {t("common.sign_up")}
                    </Link>
                )}
            </p>
        </form>
    );
}
