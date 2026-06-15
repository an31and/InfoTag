import { useEffect } from "react";
import { useParams } from "react-router-dom";

/**
 * `/tag/:slug` is the human-friendly preview URL.  The actual QR-encoded URL
 * is the SSR endpoint `/api/finder/:slug`, which serves a fully server-rendered
 * page in <3 KB gzipped — well under the 75 KB 3G budget.
 *
 * On the rare path that someone lands at `/tag/:slug` (e.g. clicking
 * "Preview" from the dashboard), we hop them over to the fast page instead
 * of loading the whole SPA.
 */
export function FinderRedirect() {
    const { slug } = useParams();
    useEffect(() => {
        if (!slug) return;
        // Use replace so the back button returns to the dashboard.
        window.location.replace(`/api/finder/${slug}`);
    }, [slug]);
    return (
        <div className="min-h-screen flex items-center justify-center px-6 text-center text-muted-foreground">
            <div className="animate-pulse-soft">Loading finder…</div>
        </div>
    );
}
