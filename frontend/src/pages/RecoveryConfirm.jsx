import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, PackageSearch } from "lucide-react";

import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { RecoveryAnswerButtons } from "../components/RecoveryPrompts";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import api from "../lib/api";
import { useI18n } from "../lib/i18n";

/**
 * RecoveryConfirmPage — login-free, one-tap owner answer.
 *
 * The one-time token arrives in the URL *fragment* (#t=…) so it's never sent
 * to any server in a request line or Referer header. Opening the page is
 * read-only (GET); only pressing a button consumes the token — so email link
 * scanners / chat previews can't answer on the owner's behalf.
 */
function readToken() {
    try {
        const params = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
        return params.get("t") || "";
    } catch {
        return "";
    }
}

const ERROR_KEYS = { 409: "recovery.err_used", 410: "recovery.err_expired" };

export default function RecoveryConfirmPage() {
    const { t } = useI18n();
    const [token] = useState(readToken);
    const [info, setInfo] = useState(null);
    const [errorKey, setErrorKey] = useState(token ? "" : "recovery.err_invalid");
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState("");

    useEffect(() => {
        if (!token) return;
        api.get(`/public/recovery/${encodeURIComponent(token)}`)
            .then(({ data }) => setInfo(data))
            .catch((e) => setErrorKey(ERROR_KEYS[e?.response?.status] || "recovery.err_invalid"));
    }, [token]);

    const answer = async (value) => {
        setBusy(true);
        try {
            await api.post(`/public/recovery/${encodeURIComponent(token)}`, { answer: value });
            setDone(value);
        } catch (e) {
            setErrorKey(ERROR_KEYS[e?.response?.status] || "recovery.err_invalid");
        } finally {
            setBusy(false);
        }
    };

    const high = info?.priority === "high";
    const thanksKey =
        done === "found" ? (high ? "recovery.thanks_found_safe" : "recovery.thanks_found") : `recovery.thanks_${done}`;

    return (
        <div className="min-h-screen flex flex-col items-center justify-center px-4 py-10">
            <div className="w-full max-w-md flex justify-end mb-3">
                <LanguageSwitcher />
            </div>
            <main className="max-w-md w-full surface p-6 sm:p-8 space-y-5 animate-rise" data-testid="recovery-confirm-root">
                <div className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-accent/10">
                    <PackageSearch className="h-5 w-5 text-accent" aria-hidden="true" />
                </div>

                {errorKey ? (
                    <div className="space-y-4" role="alert" data-testid="recovery-confirm-error">
                        <p className="text-sm">{t(errorKey)}</p>
                        <Link to="/dashboard">
                            <Button variant="outline" className="rounded-full">{t("recovery.open_dashboard")}</Button>
                        </Link>
                    </div>
                ) : done ? (
                    <div className="space-y-4" role="status" aria-live="polite" data-testid="recovery-confirm-done">
                        <CheckCircle2 className="h-8 w-8 text-emerald-500" aria-hidden="true" />
                        <p className="font-display text-lg font-bold">{t(thanksKey)}</p>
                        <Link to="/dashboard">
                            <Button variant="outline" className="rounded-full">{t("recovery.open_dashboard")}</Button>
                        </Link>
                    </div>
                ) : !info ? (
                    <div className="space-y-3" aria-busy="true">
                        <Skeleton className="h-7 w-3/4" />
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-10 w-full" />
                    </div>
                ) : (
                    <>
                        <div>
                            <h1 className="font-display text-2xl font-bold tracking-tight">
                                {high ? t("recovery.page_title_safe") : t("recovery.page_title")}
                            </h1>
                            <p className="text-sm text-muted-foreground mt-2">{t("recovery.page_subtitle")}</p>
                        </div>
                        {info.tag_name && (
                            <p className="text-sm">
                                <span className="text-muted-foreground">{t("recovery.tag_label")}: </span>
                                <span className="font-medium">{info.tag_name}</span>
                            </p>
                        )}
                        <RecoveryAnswerButtons onAnswer={answer} busy={busy} highPriority={high} testIdPrefix="recovery-confirm" />
                        <p className="text-xs text-muted-foreground">{t("recovery.no_login_note")}</p>
                    </>
                )}
            </main>
        </div>
    );
}
