// Auth context — covers both JWT email/password and Emergent Google session.
//
// On mount we call /api/auth/me to see if a cookie-backed session exists.
// However, if the URL has `#session_id=...` (the Emergent Google callback)
// we *skip* that check and let <AuthCallback> establish the session first —
// this avoids a 401 race that would otherwise log the user out instantly.
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useState,
} from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import api, { formatApiError } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null); // null = unknown, false = not authed
    const [loading, setLoading] = useState(true);

    const checkAuth = useCallback(async () => {
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
        } catch {
            setUser(false);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        // CRITICAL: If we're returning from Google OAuth, skip /me — the
        // AuthCallback component will exchange the session_id first.
        // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT
        // URLS, THIS BREAKS THE AUTH.
        if (typeof window !== "undefined" && window.location.hash?.includes("session_id=")) {
            setLoading(false);
            return;
        }
        checkAuth();
    }, [checkAuth]);

    // `identifier` is a mobile number or an email — the backend figures out which.
    const login = async (identifier, password) => {
        const { data } = await api.post("/auth/login", { identifier, password });
        setUser(data);
        return data;
    };

    // Phone-first signup; email is optional. Extra fields are simply omitted
    // when blank so the backend's "phone or email required" rule applies.
    const register = async ({ phone, email, password, display_name }) => {
        const { data } = await api.post("/auth/register", {
            phone: phone || undefined,
            email: email || undefined,
            password,
            display_name: display_name || undefined,
        });
        setUser(data);
        return data;
    };

    const logout = async () => {
        try {
            await api.post("/auth/logout");
        } catch (err) {
            // Logout is best-effort — even if the server call fails (network),
            // we still clear the user locally so the UI feels responsive.
            console.warn("Server logout failed; clearing client session anyway:", err?.message || err);
        }
        setUser(false);
    };

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
        } catch {
            setUser(false);
        }
    }, []);

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout, refresh, setUser }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
    return ctx;
}

export function ProtectedRoute({ children }) {
    const { user, loading } = useAuth();
    const location = useLocation();
    if (loading || user === null) {
        return (
            <div className="min-h-screen flex items-center justify-center text-muted-foreground">
                <div className="animate-pulse-soft">Loading…</div>
            </div>
        );
    }
    if (!user) {
        return <Navigate to="/login" replace state={{ from: location }} />;
    }
    return children;
}

/**
 * AuthCallback — exchanges Emergent Google `session_id` (from URL fragment)
 * for our JWT cookie session, then redirects to /dashboard.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 * THIS BREAKS THE AUTH.
 */
export function AuthCallback() {
    const navigate = useNavigate();
    const { setUser } = useAuth();
    const [error, setError] = useState("");

    useEffect(() => {
        let cancelled = false;
        const hash = window.location.hash || "";
        const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
        const sessionId = params.get("session_id");
        if (!sessionId) {
            navigate("/login", { replace: true });
            return;
        }
        (async () => {
            try {
                const { data } = await api.post("/auth/google/session", { session_id: sessionId });
                if (cancelled) return;
                setUser(data);
                // Clear the URL fragment so a refresh doesn't re-trigger the exchange.
                window.history.replaceState(null, "", window.location.pathname);
                navigate("/dashboard", { replace: true });
            } catch (e) {
                if (!cancelled) setError(formatApiError(e));
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [navigate, setUser]);

    return (
        <div className="min-h-screen flex items-center justify-center px-6 text-center">
            <div>
                <div className="font-display text-2xl mb-2">Signing you in…</div>
                {error ? (
                    <p className="text-destructive text-sm">{error}</p>
                ) : (
                    <p className="text-muted-foreground text-sm animate-pulse-soft">
                        Finishing your Google sign-in
                    </p>
                )}
            </div>
        </div>
    );
}
