import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
    ArrowLeft, BadgeCheck, Download, ExternalLink, FileSpreadsheet, IdCard, Loader2, MessageSquare,
    Printer, QrCode, RotateCcw, ScanLine, Search, Settings2, ShieldOff, Undo2, UserCheck, Users,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Skeleton } from "../components/ui/skeleton";
import { Switch } from "../components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import api, { formatApiError } from "../lib/api";
import { downloadApiFile, toQuery } from "../lib/download";
import { useI18n } from "../lib/i18n";
import { Field } from "./Events";

export default function EventDetailPage() {
    const { id } = useParams();
    const { t } = useI18n();
    const [ev, setEv] = useState(null);
    const [meta, setMeta] = useState(null);
    const [error, setError] = useState("");

    const reload = async () => {
        try {
            const { data } = await api.get(`/events/${id}`);
            setEv(data);
        } catch (e) {
            setError(formatApiError(e));
        }
    };
    useEffect(() => {
        reload();
        api.get("/events/meta").then(({ data }) => setMeta(data)).catch(() => {});
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    if (error) return <div className="surface p-6 text-destructive text-sm">{error}</div>;
    if (!ev) return <Skeleton className="h-64 rounded-xl" />;
    const s = ev.stats;

    return (
        <div className="space-y-6" data-testid="event-detail">
            <Link to="/events" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-4 w-4" /> {t("events.title")}
            </Link>
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h1 className="font-display text-2xl font-bold tracking-tight">{ev.name}</h1>
                    <p className="text-sm text-muted-foreground">
                        {[ev.date, ev.venue, ev.org_name].filter(Boolean).join(" · ")}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="font-mono text-sm">{ev.code}</Badge>
                    {ev.status === "archived" && <Badge variant="outline">{t("events.archived")}</Badge>}
                </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                <Stat icon={<QrCode className="h-4 w-4" />} label={t("events.stats_generated")} value={s.generated} />
                <Stat icon={<UserCheck className="h-4 w-4" />} label={t("events.stats_claimed")} value={s.claimed} />
                <Stat icon={<Users className="h-4 w-4" />} label={t("events.stats_owners")} value={s.owners} />
                <Stat icon={<ScanLine className="h-4 w-4" />} label={t("events.stats_scans")} value={s.scans} />
                <Stat icon={<Search className="h-4 w-4" />} label={t("events.stats_found")} value={s.found} />
                <Stat icon={<BadgeCheck className="h-4 w-4 text-emerald-500" />} label={t("events.stats_returned")} value={s.returned} />
            </div>
            <p className="text-xs text-muted-foreground">{t("events.permanent_note")}</p>

            <Tabs defaultValue="print">
                <TabsList className="flex-wrap h-auto">
                    <TabsTrigger value="print" className="gap-1.5" data-testid="tab-print"><Printer className="h-4 w-4" />{t("events.tab_print")}</TabsTrigger>
                    <TabsTrigger value="digital" className="gap-1.5" data-testid="tab-digital"><IdCard className="h-4 w-4" />{t("events.tab_digital")}</TabsTrigger>
                    <TabsTrigger value="tags" className="gap-1.5" data-testid="tab-tags"><QrCode className="h-4 w-4" />{t("events.tab_tags")}</TabsTrigger>
                    <TabsTrigger value="settings" className="gap-1.5" data-testid="tab-settings-ev"><Settings2 className="h-4 w-4" />{t("events.tab_settings")}</TabsTrigger>
                </TabsList>
                <TabsContent value="print" className="mt-4"><PrintPanel ev={ev} meta={meta} /></TabsContent>
                <TabsContent value="digital" className="mt-4"><DigitalPanel ev={ev} /></TabsContent>
                <TabsContent value="tags" className="mt-4"><TagsPanel ev={ev} onChange={reload} /></TabsContent>
                <TabsContent value="settings" className="mt-4"><SettingsPanel ev={ev} meta={meta} onSaved={setEv} reload={reload} /></TabsContent>
            </Tabs>
        </div>
    );
}

function Stat({ icon, label, value }) {
    return (
        <div className="surface p-4">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-semibold uppercase tracking-wide">{icon}{label}</div>
            <div className="font-display text-2xl font-black mt-1">{(value ?? 0).toLocaleString()}</div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Print studio
// ---------------------------------------------------------------------------
const NUM_FIELDS = ["page_w", "page_h", "rows", "cols", "margin_top", "margin_left", "cell_w", "cell_h", "gap_x", "gap_y", "qr_mm"];
const MODE_FOR_OUTPUT = { sticker_sheet: "sticker_sheet", badge_cards: "badge_cards", guest_pack: "guest_pack" };

function PrintPanel({ ev, meta }) {
    const { t } = useI18n();
    const presets = useMemo(() => meta?.presets || [], [meta]);
    const [mode, setMode] = useState(MODE_FOR_OUTPUT[ev.output_type] || "sticker_sheet");
    const modePresets = useMemo(() => presets.filter((p) => p.layout.mode === mode), [presets, mode]);
    const [presetId, setPresetId] = useState("");
    const [custom, setCustom] = useState(false);
    const [lay, setLay] = useState(null);
    const [opts, setOpts] = useState({ start_slot: 1, offset_x: 0, offset_y: 0, cut_marks: false, border: true, show_domain: true });
    const [manifest, setManifest] = useState(null);
    const [busy, setBusy] = useState("");

    useEffect(() => {
        const p = modePresets[0];
        if (p) {
            setPresetId(p.id);
            setLay(p.layout);
        }
    }, [modePresets]);
    useEffect(() => {
        api.get(`/events/${ev.id}/print/manifest`).then(({ data }) => setManifest(data)).catch((e) => toast.error(formatApiError(e)));
    }, [ev.id, ev.stats.generated]);

    const pickPreset = (pid) => {
        setPresetId(pid);
        const p = presets.find((x) => x.id === pid);
        if (p) setLay(p.layout);
    };
    const params = () => {
        const q = { mode, preset: presetId, ...opts };
        if (custom && lay) NUM_FIELDS.forEach((k) => (q[k] = lay[k]));
        return q;
    };
    const run = async (key, path, name) => {
        setBusy(key);
        try {
            await downloadApiFile(path, name);
        } catch (e) {
            toast.error(e.message);
        } finally {
            setBusy("");
        }
    };
    const chunkPath = (c) => `/events/${ev.id}/print.pdf${toQuery({ ...params(), from_serial: c.from_serial, count: c.count })}`;
    const chunkName = (c) => `${ev.code}-${String(c.from_serial + 1).padStart(6, "0")}-${mode}.pdf`;
    const downloadAll = async () => {
        setBusy("all");
        try {
            for (const c of manifest.chunks.filter((x) => x.status !== "revoked")) {
                // one by one: keeps the free-tier server and the phone's memory happy
                await downloadApiFile(chunkPath(c), chunkName(c));
            }
        } catch (e) {
            toast.error(e.message);
        } finally {
            setBusy("");
        }
    };
    const setO = (k) => (v) => setOpts((o) => ({ ...o, [k]: v }));
    const perPage = lay ? lay.rows * lay.cols : 0;

    return (
        <div className="grid lg:grid-cols-[1.1fr_1fr] gap-6">
            <section className="surface p-5 space-y-4" data-testid="print-settings">
                <Field label={t("events.print_mode")}>
                    <select className="w-full h-10 rounded-md border bg-background px-3 text-sm" value={mode} onChange={(e) => setMode(e.target.value)} data-testid="print-mode">
                        <option value="sticker_sheet">{t("events.out_sticker_sheet")}</option>
                        <option value="badge_cards">{t("events.out_badge_cards")}</option>
                        {ev.pack_size === 4 && <option value="guest_pack">{t("events.out_guest_pack")}</option>}
                    </select>
                </Field>
                <Field label={t("events.preset")}>
                    <select className="w-full h-10 rounded-md border bg-background px-3 text-sm" value={presetId} onChange={(e) => pickPreset(e.target.value)} data-testid="print-preset">
                        {modePresets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                    </select>
                </Field>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <Switch checked={custom} onCheckedChange={setCustom} data-testid="print-custom" /> {t("events.custom")}
                </label>
                {custom && lay && (
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        {NUM_FIELDS.map((k) => (
                            <Field key={k} label={t(`events.${k}`)}>
                                <Input type="number" step={k === "rows" || k === "cols" ? 1 : 0.1} value={lay[k]}
                                    onChange={(e) => setLay((l) => ({ ...l, [k]: e.target.value === "" ? "" : Number(e.target.value) }))} />
                            </Field>
                        ))}
                    </div>
                )}
                <div className="grid grid-cols-3 gap-3">
                    <Field label={t("events.start_slot")}>
                        <Input type="number" min={1} max={perPage || 1} value={opts.start_slot} onChange={(e) => setO("start_slot")(Number(e.target.value) || 1)} data-testid="print-start-slot" />
                    </Field>
                    <Field label={t("events.offset_x")}><Input type="number" step={0.1} value={opts.offset_x} onChange={(e) => setO("offset_x")(Number(e.target.value))} /></Field>
                    <Field label={t("events.offset_y")}><Input type="number" step={0.1} value={opts.offset_y} onChange={(e) => setO("offset_y")(Number(e.target.value))} /></Field>
                </div>
                <p className="text-xs text-muted-foreground -mt-2">{t("events.start_slot_hint")}</p>
                <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                    <label className="flex items-center gap-2"><Switch checked={opts.cut_marks} onCheckedChange={setO("cut_marks")} />{t("events.cut_marks")}</label>
                    <label className="flex items-center gap-2"><Switch checked={opts.border} onCheckedChange={setO("border")} />{t("events.border")}</label>
                    <label className="flex items-center gap-2"><Switch checked={opts.show_domain} onCheckedChange={setO("show_domain")} />{t("events.show_domain")}</label>
                </div>
                <div className="border-t pt-4 space-y-3">
                    <div className="flex flex-wrap gap-2">
                        <Button variant="outline" className="gap-2" disabled={!!busy}
                            onClick={() => run("cal", `/events/print/calibration.pdf${toQuery(params())}`, "info-tag-calibration.pdf")} data-testid="print-calibration">
                            {busy === "cal" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} {t("events.calibration")}
                        </Button>
                        <Button variant="outline" className="gap-2" disabled={!!busy}
                            onClick={() => run("poster", `/events/${ev.id}/poster.pdf`, `${ev.code}-poster.pdf`)} data-testid="print-poster">
                            {busy === "poster" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} {t("events.poster")}
                        </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">{t("events.calibration_hint")}</p>
                    <p className="text-xs text-muted-foreground">{t("events.poster_hint")} <a className="underline break-all" href={ev.poster_url} target="_blank" rel="noreferrer">{ev.poster_url}</a></p>
                </div>
            </section>

            <section className="surface p-5 space-y-3" data-testid="print-chunks">
                <div className="flex items-center justify-between gap-2">
                    <h2 className="font-display font-bold">{t("events.chunks")}</h2>
                    {manifest && manifest.chunks.length > 1 && (
                        <Button size="sm" className="gap-2 rounded-full" disabled={!!busy} onClick={downloadAll}>
                            {busy === "all" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} {t("events.download_all")}
                        </Button>
                    )}
                </div>
                <p className="text-xs text-muted-foreground">{t("events.chunks_hint")}</p>
                {!manifest ? <Skeleton className="h-20" /> : (
                    <ul className="divide-y max-h-[28rem] overflow-y-auto">
                        {manifest.chunks.map((c) => (
                            <li key={`${c.bid}-${c.from_serial}`} className="flex items-center justify-between gap-2 py-2">
                                <span className="text-sm">
                                    {t("events.chunk_label").replace("{from}", c.from_serial + 1).replace("{to}", c.from_serial + c.count)}
                                    {c.kind === "spare" && <Badge variant="outline" className="ml-2">{t("events.spare")}</Badge>}
                                    {c.status === "revoked" && <Badge variant="destructive" className="ml-2">{t("events.revoked")}</Badge>}
                                </span>
                                <Button size="sm" variant="outline" className="gap-1.5" disabled={!!busy || c.status === "revoked"}
                                    onClick={() => run(`c${c.from_serial}`, chunkPath(c), chunkName(c))} data-testid="print-chunk-btn">
                                    {busy === `c${c.from_serial}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />} PDF
                                </Button>
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Digital IDs
// ---------------------------------------------------------------------------
function DigitalPanel({ ev }) {
    const { t } = useI18n();
    const [busy, setBusy] = useState(false);
    const [first, setFirst] = useState(null);
    useEffect(() => {
        api.get(`/events/${ev.id}/tags`, { params: { limit: 1 } }).then(({ data }) => setFirst(data.items[0] || null)).catch(() => {});
    }, [ev.id]);
    return (
        <section className="surface p-5 space-y-4 max-w-2xl" data-testid="digital-panel">
            <p className="text-sm">{t("events.digital_lead")}</p>
            <Button className="gap-2 rounded-full" disabled={busy} data-testid="digital-csv"
                onClick={async () => {
                    setBusy(true);
                    try { await downloadApiFile(`/events/${ev.id}/digital-ids.csv`, `${ev.code}-digital-ids.csv`); } catch (e) { toast.error(e.message); } finally { setBusy(false); }
                }}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />} {t("events.digital_csv")}
            </Button>
            <p className="text-xs text-muted-foreground">{t("events.digital_hint")}</p>
            {first && (
                <a className="inline-flex items-center gap-1.5 text-sm underline" href={first.digital_id_url} target="_blank" rel="noreferrer">
                    <IdCard className="h-4 w-4" /> {first.code} <ExternalLink className="h-3 w-3" />
                </a>
            )}
        </section>
    );
}

// ---------------------------------------------------------------------------
// Tags table (help desk)
// ---------------------------------------------------------------------------
function TagsPanel({ ev, onChange }) {
    const { t } = useI18n();
    const [filter, setFilter] = useState("all");
    const [from, setFrom] = useState(0);
    const [page, setPage] = useState(null);
    const [code, setCode] = useState("");
    const [found, setFound] = useState(null);
    const [names, setNames] = useState(false);
    const [busy, setBusy] = useState(false);

    const load = async (f = from) => {
        try {
            const { data } = await api.get(`/events/${ev.id}/tags`, { params: { from_serial: f, limit: 50, status: filter } });
            setPage(data);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    useEffect(() => {
        load(from);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [from, filter, ev.id]);

    const lookup = async (e) => {
        e.preventDefault();
        try {
            const { data } = await api.get(`/events/${ev.id}/lookup`, { params: { code } });
            setFound(data);
        } catch (err) {
            setFound(null);
            toast.error(formatApiError(err));
        }
    };
    const refresh = async () => {
        await load(from);
        if (found) {
            const { data } = await api.get(`/events/${ev.id}/lookup`, { params: { code: found.code } });
            setFound(data);
        }
        onChange?.();
    };

    return (
        <div className="space-y-4">
            <form onSubmit={lookup} className="surface p-4 flex flex-wrap gap-2 items-end" data-testid="tag-lookup">
                <Field label={t("events.lookup")}>
                    <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("events.lookup_ph")} className="font-mono uppercase w-64" />
                </Field>
                <Button type="submit" className="gap-2"><Search className="h-4 w-4" />{t("events.lookup")}</Button>
                <div className="ml-auto flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-2 text-sm"><Switch checked={names} onCheckedChange={setNames} />{t("events.report_names")}</label>
                    <Button type="button" variant="outline" className="gap-2" disabled={busy}
                        onClick={async () => {
                            setBusy(true);
                            try { await downloadApiFile(`/events/${ev.id}/report.csv${toQuery({ include_names: names })}`, `${ev.code}-report.csv`); } catch (er) { toast.error(er.message); } finally { setBusy(false); }
                        }}>
                        <FileSpreadsheet className="h-4 w-4" />{t("events.report_csv")}
                    </Button>
                </div>
            </form>
            {found && <div className="surface p-1"><TagRow ev={ev} row={found} onDone={refresh} highlight /></div>}

            <div className="flex items-center gap-2">
                <select className="h-9 rounded-md border bg-background px-3 text-sm" value={filter} onChange={(e) => { setFrom(0); setFilter(e.target.value); }}>
                    <option value="all">{t("events.filter_all")}</option>
                    <option value="claimed">{t("events.filter_claimed")}</option>
                </select>
                {from > 0 && <Button size="sm" variant="ghost" onClick={() => setFrom(0)}>{t("events.prev")}</Button>}
                {page?.next_from != null && <Button size="sm" variant="outline" onClick={() => setFrom(page.next_from)}>{t("events.next")}</Button>}
            </div>
            {!page ? <Skeleton className="h-40" /> : (
                <div className="surface divide-y" data-testid="tags-table">
                    {page.items.map((r) => <TagRow key={r.serial} ev={ev} row={r} onDone={refresh} />)}
                </div>
            )}
        </div>
    );
}

const STATUS_VARIANT = { unclaimed: "outline", claimed: "secondary", returned: "default", revoked: "destructive" };

function TagRow({ ev, row, onDone, highlight }) {
    const { t } = useI18n();
    const [msg, setMsg] = useState(null);
    const claimed = row.status === "claimed" || row.status === "returned";
    const setReturned = async (v) => {
        try {
            await api.post(`/events/${ev.id}/tags/${row.serial}/returned`, { returned: v });
            onDone?.();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    const send = async () => {
        try {
            await api.post(`/events/${ev.id}/tags/${row.serial}/notify`, { message: msg });
            toast.success(t("events.notify_sent"));
            setMsg(null);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    return (
        <div className={`p-3 text-sm ${highlight ? "bg-accent/5 rounded-lg" : ""}`} data-testid="tag-row">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <span className="text-muted-foreground w-12">#{row.serial + 1}</span>
                <span className="font-mono font-semibold">{row.code}</span>
                <Badge variant={STATUS_VARIANT[row.status] || "outline"}>{t(`events.st_${row.status}`)}</Badge>
                {row.item_type && <span>{row.item_type}</span>}
                {claimed && <span className="text-muted-foreground">{[row.owner_name, row.owner_phone_hint, row.owner_email_hint].filter(Boolean).join(" · ")}</span>}
                <span className="text-muted-foreground">{t("events.scans")}: {row.scan_count}</span>
                <span className="ml-auto flex flex-wrap gap-1">
                    <Button asChild size="sm" variant="ghost" className="gap-1"><a href={row.tag_url} target="_blank" rel="noreferrer"><QrCode className="h-3.5 w-3.5" />{t("events.open_tag")}</a></Button>
                    <Button asChild size="sm" variant="ghost" className="gap-1"><a href={row.digital_id_url} target="_blank" rel="noreferrer"><IdCard className="h-3.5 w-3.5" />{t("events.open_digital_id")}</a></Button>
                    {claimed && (
                        <>
                            <Button size="sm" variant="outline" className="gap-1" onClick={() => setMsg(msg === null ? "" : null)}><MessageSquare className="h-3.5 w-3.5" />{t("events.notify")}</Button>
                            {row.status === "returned" ? (
                                <Button size="sm" variant="outline" className="gap-1" onClick={() => setReturned(false)}><Undo2 className="h-3.5 w-3.5" />{t("events.undo_returned")}</Button>
                            ) : (
                                <Button size="sm" className="gap-1" onClick={() => setReturned(true)} data-testid="mark-returned"><BadgeCheck className="h-3.5 w-3.5" />{t("events.mark_returned")}</Button>
                            )}
                        </>
                    )}
                </span>
            </div>
            {msg !== null && (
                <div className="flex gap-2 mt-2">
                    <Input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder={t("events.notify_ph")} maxLength={500} />
                    <Button disabled={!msg.trim()} onClick={send}>{t("events.notify")}</Button>
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
function SettingsPanel({ ev, meta, onSaved, reload }) {
    const { t } = useI18n();
    const [f, setF] = useState({
        name: ev.name, date: ev.date || "", venue: ev.venue || "", help_desk_note: ev.help_desk_note || "",
        reward_text: ev.reward_text || "", message: ev.message || "", default_contact_mode: ev.default_contact_mode,
        default_lang: ev.default_lang, claims_open: ev.claims_open !== false,
    });
    const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));
    const patch = async (body) => {
        try {
            const { data } = await api.patch(`/events/${ev.id}`, body);
            onSaved(data);
            toast.success(t("events.saved"));
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    const spare = async () => {
        try {
            await api.post(`/events/${ev.id}/batches`, { percent: 10 });
            toast.success(t("events.spare_done"));
            reload();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    const revoke = async (b, restore) => {
        if (!restore && !window.confirm(t("events.revoke_confirm"))) return;
        try {
            await api.post(`/events/${ev.id}/batches/${b.bid}/${restore ? "restore" : "revoke"}`, {});
            reload();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    const canGenerate = meta?.can_create;

    return (
        <div className="grid lg:grid-cols-2 gap-6">
            <form className="surface p-5 space-y-4" onSubmit={(e) => { e.preventDefault(); patch(f); }} data-testid="event-settings">
                <Field label={t("events.name")}><Input value={f.name} onChange={set("name")} maxLength={120} /></Field>
                <div className="grid grid-cols-2 gap-3">
                    <Field label={t("events.date")}><Input type="date" value={f.date} onChange={set("date")} /></Field>
                    <Field label={t("events.venue")}><Input value={f.venue} onChange={set("venue")} maxLength={160} /></Field>
                </div>
                <Field label={t("events.help_desk")}><Input value={f.help_desk_note} onChange={set("help_desk_note")} maxLength={160} /></Field>
                <Field label={t("events.reward")}><Input value={f.reward_text} onChange={set("reward_text")} maxLength={120} /></Field>
                <Field label={t("events.message")}><Input value={f.message} onChange={set("message")} maxLength={300} /></Field>
                <div className="grid grid-cols-2 gap-3">
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
                <label className="flex items-center gap-2 text-sm"><Switch checked={f.claims_open} onCheckedChange={set("claims_open")} />{t("events.claims_open")}</label>
                <div className="flex flex-wrap gap-2">
                    <Button type="submit">{t("events.save")}</Button>
                    <Button type="button" variant="outline" onClick={() => patch({ status: ev.status === "archived" ? "active" : "archived" })}>
                        {ev.status === "archived" ? t("events.unarchive") : t("events.archive")}
                    </Button>
                </div>
            </form>

            <section className="surface p-5 space-y-4">
                <div className="flex items-center justify-between gap-2">
                    <h2 className="font-display font-bold">{t("events.batches")}</h2>
                    {canGenerate && <Button size="sm" variant="outline" onClick={spare} data-testid="spare-btn">{t("events.spare_btn")}</Button>}
                </div>
                <ul className="divide-y text-sm">
                    {(ev.batches || []).map((b) => (
                        <li key={b.bid} className="py-2 flex items-center justify-between gap-2">
                            <span>
                                #{b.serial_start + 1}–{b.serial_start + b.count} · {b.count.toLocaleString()}
                                {b.kind === "spare" && <Badge variant="outline" className="ml-2">{t("events.spare")}</Badge>}
                                {(b.status === "revoked" || (b.revoked_ranges || []).length > 0) && <Badge variant="destructive" className="ml-2">{t("events.revoked")}</Badge>}
                            </span>
                            {meta?.can_revoke && (b.status === "revoked" || (b.revoked_ranges || []).length > 0 ? (
                                <Button size="sm" variant="outline" className="gap-1" onClick={() => revoke(b, true)}><RotateCcw className="h-3.5 w-3.5" />{t("events.restore")}</Button>
                            ) : (
                                <Button size="sm" variant="ghost" className="gap-1 text-destructive" onClick={() => revoke(b, false)}><ShieldOff className="h-3.5 w-3.5" />{t("events.revoke")}</Button>
                            ))}
                        </li>
                    ))}
                </ul>
                {meta?.role === "admin" && <p className="text-xs text-muted-foreground">{t("events.signing_note")}</p>}
            </section>
        </div>
    );
}
