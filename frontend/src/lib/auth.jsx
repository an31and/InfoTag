// Auth context — one httpOnly JWT cookie session for both email/password and
// Google sign-in (the Google flow is handled server-side and lands on
// /dashboard with the cookie already set).
//
// On mount we call /api/auth/me to see if a cookie-backed session exists.
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useState,
} from "react";
import { Navigate, useLocation } from "react-router-dom";

import api from "./api";

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
        checkAuth();
    }, [checkAuth]);

    const login = async (email, password) => {
        const { data } = await api.post("/auth/login", { email, password });
        setUser(data);
        return data;
    };

    const register = async (email, password, display_name) => {
        const { data } = await api.post("/auth/register", { email, password, display_name });
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
