import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Tag } from "lucide-react";

import { AuthVisualPanel, EmailPasswordForm } from "../components/auth/AuthParts";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { ThemeToggle } from "../components/ThemeToggle";

import { useAuth } from "../lib/auth";
import { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

/**
 * Two-pane auth screen (visual + form).  All form / Google logic lives in
 * `<EmailPasswordForm>` and `<GoogleAuthButton>` inside `AuthParts.jsx`.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 * THIS BREAKS THE AUTH.
 */
export default function AuthPage({ mode = "login" }) {
    const isSignup = mode === "signup";
    const { t } = useI18n();
    const { login, register } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");

    const onSubmit = async (e) => {
        e.preventDefault();
        setError("");
        if (password.length < 8) {
            setError(t("auth.password_min"));
            return;
        }
        setSubmitting(true);
        try {
            if (isSignup) {
                await register(email, password, displayName);
            } else {
                await login(email, password);
            }
            const next = location.state?.from?.pathname || "/dashboard";
            navigate(next, { replace: true });
        } catch (err) {
            setError(formatApiError(err));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen grid md:grid-cols-2">
            <AuthVisualPanel t={t} />

            <div className="flex flex-col">
                <div className="flex items-center justify-between p-4 border-b md:border-0">
                    <Link to="/" className="md:hidden inline-flex items-center gap-2 font-display font-black text-lg">
                        <Tag className="h-5 w-5 text-accent" /> Info-<span className="text-accent">Tag</span>
                    </Link>
                    <div className="ml-auto flex items-center gap-1">
                        <LanguageSwitcher compact />
                        <ThemeToggle />
                    </div>
                </div>
                <div className="flex-1 flex items-center justify-center p-6">
                    <EmailPasswordForm
                        isSignup={isSignup}
                        t={t}
                        email={email}
                        setEmail={setEmail}
                        password={password}
                        setPassword={setPassword}
                        displayName={displayName}
                        setDisplayName={setDisplayName}
                        submitting={submitting}
                        error={error}
                        onSubmit={onSubmit}
                    />
                </div>
            </div>
        </div>
    );
}
