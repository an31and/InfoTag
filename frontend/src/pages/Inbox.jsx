import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapPin, MessageSquare, Share2 } from "lucide-react";

import api, { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

const ACTION_KEYS = {
    message: "inbox.action_message",
    wrong_parking: "inbox.action_wrong_parking",
    headlight_on: "inbox.action_headlight_on",
    found: "inbox.action_found",
    call_request: "inbox.action_call_request",
};

export default function InboxPage() {
    const { t } = useI18n();
    const [msgs, setMsgs] = useState(null);
    const [tags, setTags] = useState({});
    const [error, setError] = useState("");

    useEffect(() => {
        (async () => {
            try {
                const [{ data: m }, { data: ts }] = await Promise.all([
                    api.get("/inbox"),
                    api.get("/tags"),
                ]);
                setMsgs(m);
                setTags(Object.fromEntries(ts.map((tg) => [tg.id, tg])));
            } catch (e) {
                setError(formatApiError(e));
            }
        })();
    }, []);

    return (
        <div className="space-y-6 max-w-3xl" data-testid="inbox-root">
            <h1 className="font-display text-3xl font-black tracking-tight">{t("common.inbox")}</h1>
            <InboxBody msgs={msgs} tags={tags} t={t} />
            {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
    );
}

/* Forward a finder alert to family/friends over WhatsApp. */
function waShareUrl(m, tag, t) {
    const lines = [
        `📨 Info-Tag: ${t(ACTION_KEYS[m.action_type] || "inbox.action_message")}`,
        `🏷️ ${tag ? tag.display_name || tag.label : "Tag"}`,
    ];
    if (m.body) lines.push(`💬 ${m.body}`);
    if (m.finder_name || m.finder_contact) lines.push(`👤 ${[m.finder_name, m.finder_contact].filter(Boolean).join(" · ")}`);
    if (m.location) lines.push(`📍 https://maps.google.com/?q=${m.location.lat},${m.location.lng}`);
    return `https://wa.me/?text=${encodeURIComponent(lines.join("\n"))}`;
}

function InboxBody({ msgs, tags, t }) {
    if (msgs === null) {
        return <div className="text-muted-foreground animate-pulse-soft">{t("common.loading")}</div>;
    }
    if (msgs.length === 0) {
        return (
            <div className="surface p-10 text-center">
                <MessageSquare className="h-8 w-8 mx-auto text-muted-foreground" />
                <p className="mt-3 text-muted-foreground">{t("inbox.empty")}</p>
            </div>
        );
    }
    return (
        <div className="space-y-3">
            {msgs.map((m) => {
                const tag = tags[m.tag_id];
                return (
                    <div key={m.id} className="surface p-5 animate-rise" data-testid={`inbox-item-${m.id}`}>
                        <div className="flex items-center justify-between gap-3">
                            <div className="text-xs uppercase tracking-widest text-muted-foreground">
                                {ACTION_KEYS[m.action_type] ? t(ACTION_KEYS[m.action_type]) : m.action_type}
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {new Date(m.created_at).toLocaleString()}
                            </div>
                        </div>
                        <div className="font-display font-bold mt-1">
                            {tag ? tag.display_name || tag.label : "Tag"}
                        </div>
                        {m.body && <p className="text-sm mt-2 whitespace-pre-wrap">{m.body}</p>}
                        {m.location && (
                            <a
                                href={`https://maps.google.com/?q=${m.location.lat},${m.location.lng}`}
                                target="_blank"
                                rel="noreferrer"
                                className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400 hover:border-emerald-500"
                                data-testid={`inbox-gps-${m.id}`}
                            >
                                <MapPin className="h-4 w-4 shrink-0" />
                                <span className="font-medium">{t("inbox.view_location")}</span>
                                <span className="font-mono text-xs opacity-80">
                                    {Number(m.location.lat).toFixed(5)}, {Number(m.location.lng).toFixed(5)}
                                </span>
                            </a>
                        )}
                        <div className="text-xs text-muted-foreground mt-3 flex flex-wrap gap-3 items-center">
                            {m.finder_name && <span>{t("inbox.from")}: {m.finder_name}</span>}
                            {m.finder_contact && <span>· {m.finder_contact}</span>}
                            <a
                                href={waShareUrl(m, tag, t)}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 hover:underline"
                                data-testid={`inbox-share-${m.id}`}
                            >
                                <Share2 className="h-3.5 w-3.5" /> {t("inbox.share_whatsapp")}
                            </a>
                            {tag && (
                                <Link to={`/tags/${tag.id}`} className="ml-auto text-accent hover:underline">
                                    {t("inbox.open_tag")}
                                </Link>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
