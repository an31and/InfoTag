import { useEffect, useState } from "react";
import { CheckCircle2, Clock, PackageSearch, Siren, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import api, { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

/**
 * RecoveryAnswerButtons — the three owner answers, shared by the login-free
 * confirmation page and the dashboard card. Only "found" ever counts as a
 * recovery (enforced server-side). High-priority tags (child / pet /
 * medical) use "found safe" wording.
 */
export function RecoveryAnswerButtons({ onAnswer, busy, highPriority = false, testIdPrefix = "recovery" }) {
    const { t } = useI18n();
    return (
        <div className="grid sm:grid-cols-3 gap-2" role="group">
            <Button
                onClick={() => onAnswer("found")}
                disabled={busy}
                className="rounded-full gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
                data-testid={`${testIdPrefix}-found`}
            >
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                {highPriority ? t("recovery.yes_found_safe") : t("recovery.yes_found")}
            </Button>
            <Button
                variant="outline"
                onClick={() => onAnswer("not_found")}
                disabled={busy}
                className="rounded-full gap-1.5"
                data-testid={`${testIdPrefix}-not-found`}
            >
                <XCircle className="h-4 w-4" aria-hidden="true" />
                {t("recovery.not_found")}
            </Button>
            <Button
                variant="ghost"
                onClick={() => onAnswer("not_yet")}
                disabled={busy}
                className="rounded-full gap-1.5"
                data-testid={`${testIdPrefix}-not-yet`}
            >
                <Clock className="h-4 w-4" aria-hidden="true" />
                {t("recovery.not_yet")}
            </Button>
        </div>
    );
}

/**
 * RecoveryPrompts — dashboard card listing cases where a finder reached out
 * and the owner hasn't confirmed yet. Renders nothing when there are none.
 */
export function RecoveryPrompts() {
    const { t } = useI18n();
    const [cases, setCases] = useState([]);
    const [busyId, setBusyId] = useState(null);

    useEffect(() => {
        api.get("/recoveries/pending")
            .then(({ data }) => setCases(data))
            .catch(() => {}); // secondary card — never block the dashboard
    }, []);

    const answer = async (id, value) => {
        setBusyId(id);
        try {
            await api.post(`/recoveries/${id}/respond`, { answer: value });
            toast.success(t("recovery.saved"));
            // "Not yet" keeps the case open; refresh its status in place.
            if (value === "not_yet") {
                setCases((prev) => prev.map((c) => (c.id === id ? { ...c, status: "awaiting_owner" } : c)));
            } else {
                setCases((prev) => prev.filter((c) => c.id !== id));
            }
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setBusyId(null);
        }
    };

    if (cases.length === 0) return null;

    return (
        <section className="surface p-5 sm:p-6 border-accent/40" aria-labelledby="recovery-prompts-title" data-testid="recovery-prompts">
            <div className="flex items-center gap-2">
                <PackageSearch className="h-5 w-5 text-accent" aria-hidden="true" />
                <h2 id="recovery-prompts-title" className="font-display text-lg font-bold">
                    {t("recovery.dashboard_title")}
                </h2>
            </div>
            <p className="text-sm text-muted-foreground mt-1">{t("recovery.dashboard_subtitle")}</p>
            <ul className="mt-4 space-y-3">
                {cases.map((c) => {
                    const high = c.priority === "high";
                    return (
                        <li key={c.id} className="rounded-xl border p-4 space-y-3" data-testid={`recovery-case-${c.id}`}>
                            <div className="flex flex-wrap items-center gap-2">
                                {high && (
                                    <Badge variant="destructive" className="gap-1">
                                        <Siren className="h-3 w-3" aria-hidden="true" /> {t("recovery.high_priority")}
                                    </Badge>
                                )}
                                <span className="font-medium">{c.tag_name || t("dashboard.untitled")}</span>
                                <Badge variant="secondary">{t(`recovery.status_${c.status}`)}</Badge>
                                {c.first_contact_at && (
                                    <span className="text-xs text-muted-foreground">
                                        {t("recovery.contacted_on")}: {new Date(c.first_contact_at).toLocaleDateString()}
                                    </span>
                                )}
                            </div>
                            <RecoveryAnswerButtons
                                onAnswer={(v) => answer(c.id, v)}
                                busy={busyId === c.id}
                                highPriority={high}
                                testIdPrefix={`recovery-${c.id}`}
                            />
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}
