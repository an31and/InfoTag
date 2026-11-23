import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalendarDays, MapPin, Plus, QrCode, ScanLine, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Skeleton } from "../components/ui/skeleton";
import { Switch } from "../components/ui/switch";
import api, { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

/**
 * Event Mode — list of events the signed-in admin / organiser may manage.
 * The backend scopes the list (organisers only ever get their own org).
 */
export default function EventsPage() {
    const { t } = useI18n();
    const [meta, setMeta] = useState(null);
    const [items, setItems] = useState(null);
    const [cursor, setCursor] = useState(null);
    const [archived, setArchived] = useState(false);
    const [error, setError] = useState("");

    const load = async (next = null, reset = true) => {
        try {
            const { data } = await api.get("/events", { params: { cursor: next || undefined, include_archived: archived } });
            setItems((prev) => (reset || !prev ? data.items : [...prev, ...data.items]));
            setCursor(data.next_cursor);
        } catch (e) {
            setError(formatApiError(e));
        }
    };

    useEffect(() => {
        api.get("/events/meta").then(({ data }) => setMeta(data)).catch((e) => setError(formatApiError(e)));
    }, []);
    useEffect(() => {
        load(null, true);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [archived]);

    if (error) return <div className="surface p-6 text-destructive text-sm" data-testid="events-error">{error}</div>;

    return (
        <div className="space-y-6" data-testid="events-page">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h1 className="font-display text-2xl font-bold tracking-tight flex items-center gap-2">
                        <QrCode className="h-6 w-6 text-accent" /> {t("events.title")}
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{t("events.lead")}</p>
                    {meta?.org && <p className="text-sm mt-1 font-medium">{meta.org.name}</p>}
                </div>
                {meta?.can_create && (
                    <Button asChild className="rounded-full gap-2" data-testid="new-event-btn">
                        <Link to="/events/new"><Plus className="h-4 w-4" /> {t("events.new_event")}</Link>
                    </Button>
                )}
            </div>

            <label className="flex items-center gap-2 text-sm text-muted-foreground w-fit cursor-pointer">
                <Switch checked={archived} onCheckedChange={setArchived} /> {t("events.show_archived")}
            </label>

            {items === null ? (
                <div className="grid md:grid-cols-2 gap-4">{[0, 1].map((i) => <Skeleton key={i} className="h-36 rounded-xl" />)}</div>
            ) : items.length === 0 ? (
                <div className="surface p-8 text-center text-muted-foreground" data-testid="events-empty">
                    {meta?.can_create ? t("events.empty") : t("events.empty_org")}
                </div>
            ) : (
                <div className="grid md:grid-cols-2 gap-4">
                    {items.map((ev) => (
                        <Link key={ev.id} to={`/events/${ev.id}`} className="surface p-5 hover:border-accent transition-colors block" data-testid="event-card">
                            <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                    <div className="font-display text-lg font-bold truncate">{ev.name}</div>
                                    <div className="text-xs text-muted-foreground flex flex-wrap gap-x-3 mt-1">
                                        {ev.date && <span className="inline-flex items-center gap-1"><CalendarDays className="h-3 w-3" />{ev.date}</span>}
                                        {ev.venue && <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{ev.venue}</span>}
                                        {ev.org_name && <span>{ev.org_name}</span>}
                                    </div>
                                </div>
                                <div className="flex flex-col items-end gap-1">
                                    <Badge variant="secondary" className="font-mono">{ev.code}</Badge>
                                    {ev.status === "archived" && <Badge variant="outline">{t("events.archived")}</Badge>}
                                </div>
                            </div>
                            <div className="grid grid-cols-3 gap-2 mt-4 text-center">
                                <MiniStat icon={<QrCode className="h-3.5 w-3.5" />} label={t("events.stats_generated")} value={ev.stats.generated} />
                                <MiniStat icon={<UserCheck className="h-3.5 w-3.5" />} label={t("events.stats_claimed")} value={ev.stats.claimed} />
                                <MiniStat icon={<ScanLine className="h-3.5 w-3.5" />} label={t("events.stats_scans")} value={ev.stats.scans} />
                            </div>
                        </Link>
                    ))}
                </div>
            )}
            {cursor && (
                <Button variant="outline" onClick={() => load(cursor, false)} className="rounded-full">{t("events.load_more")}</Button>
            )}
        </div>
    );
}

function MiniStat({ icon, label, value }) {
    return (
        <div className="rounded-lg bg-muted/60 py-2">
            <div className="font-display text-xl font-black">{(value ?? 0).toLocaleString()}</div>
            <div className="text-[11px] text-muted-foreground inline-flex items-center gap-1">{icon}{label}</div>
        </div>
    );
}

/** Create an event + its first signed batch of tags. */
export function EventCreatePage() {
    const { t } = useI18n();
    const navigate = useNavigate();
    const [meta, setMeta] = useState(null);
    const [busy, setBusy] = useState(false);
    const [f, setF] = useState({
        org_id: "", name: "", code: "", date: "", venue: "", tag_count: 200, output_type: "sticker_sheet",
        default_contact_mode: "masked", default_lang: "hi", reward_text: "", message: "", help_desk_note: "",
    });
    const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));

    useEffect(() => {
        api.get("/events/meta").then(({ data }) => setMeta(data)).catch((e) => toast.error(formatApiError(e)));
    }, []);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const payload = { ...f, tag_count: Number(f.tag_count), org_id: f.org_id || null, code: f.code.trim().toUpperCase() || null };
            const { data } = await api.post("/events", payload);
            toast.success(t("events.created"));
            navigate(`/events/${data.id}`, { replace: true });
        } catch (err) {
            toast.error(formatApiError(err));
        } finally {
            setBusy(false);
        }
    };

    if (meta && !meta.can_create) return <div className="surface p-6 text-sm">{t("events.admin_only")}</div>;

    return (
        <form onSubmit={submit} className="space-y-6 max-w-2xl" data-testid="event-create-form">
            <h1 className="font-display text-2xl font-bold tracking-tight">{t("events.new_event")}</h1>
            <div className="surface p-6 space-y-4">
                {meta?.role === "admin" && (
                    <Field label={t("events.org")}>
                        <select className="w-full h-10 rounded-md border bg-background px-3 text-sm" value={f.org_id} onChange={set("org_id")} data-testid="event-org">
                            <option value="">{t("events.org_none")}</option>
                            {meta.orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                        </select>
                    </Field>
                )}
                <Field label={t("events.name")}><Input required minLength={2} maxLength={120} value={f.name} onChange={set("name")} data-testid="event-name" /></Field>
                <div className="grid sm:grid-cols-2 gap-4">
                    <Field label={t("events.code")} hint={t("events.code_hint")}>
                        <Input maxLength={8} value={f.code} onChange={set("code")} className="uppercase font-mono" placeholder="PK24" data-testid="event-code" />
                    </Field>
                    <Field label={t("events.tag_count")}>
                        <Input type="number" min={1} max={meta?.org?.max_tags_per_event || 1000000} required value={f.tag_count} onChange={set("tag_count")} data-testid="event-count" />
                    </Field>
                    <Field label={t("events.date")}><Input type="date" value={f.date} onChange={set("date")} /></Field>
                    <Field label={t("events.venue")}><Input maxLength={160} value={f.venue} onChange={set("venue")} /></Field>
                </div>
                <Field label={t("events.output_type")}>
                    <div className="grid sm:grid-cols-3 gap-2">
                        {["sticker_sheet", "badge_cards", "guest_pack"].map((k) => (
                            <label key={k} className={`rounded-lg border p-3 text-sm cursor-pointer ${f.output_type === k ? "border-accent bg-accent/5 font-semibold" : ""}`}>
                                <input type="radio" name="output_type" className="sr-only" checked={f.output_type === k} onChange={() => set("output_type")(k)} />
                                {t(`events.out_${k}`)}
                            </label>
                        ))}
                    </div>
                </Field>
                <div className="grid sm:grid-cols-2 gap-4">
                    <Field label={t("events.contact_mode")}>
                        <select className="w-full h-10 rounded-md border bg-background px-3 text-sm" value={f.default_contact_mode} onChange={set("default_contact_mode")}>
                            <option value="masked">{t("events.masked")}</option>
                            <option value="direct">{t("events.direct")}</option>
                        </select>
                    </Field>
                    <Field label={t("events.default_lang")}>
                        <select className="w-full h-10 rounded-md border bg-background px-3 text-sm" value={f.default_lang} onChange={set("default_lang")}>
                            <option value="hi">हिन्दी</option>
                            <option value="en">English</option>
                        </select>
                    </Field>
                </div>
                <Field label={t("events.help_desk")}><Input maxLength={160} value={f.help_desk_note} onChange={set("help_desk_note")} /></Field>
                <Field label={t("events.reward")}><Input maxLength={120} value={f.reward_text} onChange={set("reward_text")} /></Field>
                <Field label={t("events.message")}><Input maxLength={300} value={f.message} onChange={set("message")} /></Field>
                <p className="text-xs text-muted-foreground">{t("events.permanent_note")}</p>
            </div>
            <Button type="submit" disabled={busy} className="rounded-full" data-testid="event-create-submit">
                {busy ? t("events.creating") : t("events.create")}
            </Button>
        </form>
    );
}

export function Field({ label, hint, children }) {
    return (
        <label className="block space-y-1.5">
            <span className="text-sm font-medium">{label}</span>
            {children}
            {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
        </label>
    );
}
