import { useEffect, useState } from "react";
import {
    BarChart3,
    CheckCircle2,
    Eye,
    EyeOff,
    HandHeart,
    HeartHandshake,
    LayoutList,
    MessageSquareText,
    PackageCheck,
    ScanLine,
    ShieldCheck,
    Star,
    Tag as TagIcon,
    Trash2,
    Users,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { Switch } from "../components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import api, { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

/**
 * AdminPage — founder-only portal.
 *
 * Visibility of this page is gated in App.js (role === "admin"), but the
 * real security boundary is the backend: every /api/admin/* endpoint
 * re-verifies the role server-side.
 */
export default function AdminPage() {
    const { t } = useI18n();
    const [stats, setStats] = useState(null);
    const [daily, setDaily] = useState([]);
    const [feedback, setFeedback] = useState(null);
    const [sponsors, setSponsors] = useState(null);
    const [error, setError] = useState("");

    const load = async () => {
        try {
            const [{ data: s }, { data: d }, { data: fb }, { data: sp }] = await Promise.all([
                api.get("/admin/stats"),
                api.get("/admin/scans/daily?days=14"),
                api.get("/admin/feedback"),
                api.get("/admin/sponsors"),
            ]);
            setStats(s);
            setDaily(d);
            setFeedback(fb);
            setSponsors(sp);
        } catch (e) {
            setError(formatApiError(e));
        }
    };

    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const moderate = async (id, isPublic) => {
        try {
            await api.patch(`/admin/feedback/${id}`, { is_public: isPublic });
            setFeedback((prev) => prev.map((f) => (f.id === id ? { ...f, is_public: isPublic } : f)));
        } catch (e) {
            setError(formatApiError(e));
        }
    };

    const removeFeedback = async (id) => {
        try {
            await api.delete(`/admin/feedback/${id}`);
            setFeedback((prev) => prev.filter((f) => f.id !== id));
        } catch (e) {
            setError(formatApiError(e));
        }
    };

    if (error) {
        return (
            <div className="surface p-6 text-destructive text-sm" data-testid="admin-error">
                {error}
            </div>
        );
    }

    return (
        <div className="space-y-8" data-testid="admin-page">
            <div className="flex items-center gap-3">
                <div className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-accent/10">
                    <ShieldCheck className="h-5 w-5 text-accent" />
                </div>
                <div>
                    <h1 className="font-display text-2xl font-bold tracking-tight">Admin portal</h1>
                    <p className="text-sm text-muted-foreground">Founder dashboard — visible only to you.</p>
                </div>
            </div>

            {/* Stat cards */}
            {!stats ? (
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {[...Array(4)].map((_, i) => (
                        <Skeleton key={i} className="h-28 rounded-xl" />
                    ))}
                </div>
            ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatCard
                        icon={<Users className="h-5 w-5" />}
                        label="Visitors"
                        value={stats.visitors.total}
                        sub={`${stats.visitors.today} today · ${stats.visitors.last_7d} this week`}
                        testId="stat-visitors"
                    />
                    <StatCard
                        icon={<ScanLine className="h-5 w-5" />}
                        label="Tag scans"
                        value={stats.scans.total}
                        sub={`${stats.scans.today} today · ${stats.scans.last_7d} this week`}
                        testId="stat-scans"
                    />
                    <StatCard
                        icon={<PackageCheck className="h-5 w-5 text-emerald-500" />}
                        label="Items recovered"
                        value={stats.found.items_recovered}
                        sub={`${stats.found.reports} found reports · ${stats.found.currently_lost} still lost`}
                        testId="stat-found"
                    />
                    <StatCard
                        icon={<MessageSquareText className="h-5 w-5" />}
                        label="Feedback"
                        value={stats.feedback.total}
                        sub={`${stats.feedback.pending_review} awaiting review`}
                        testId="stat-feedback"
                    />
                    <StatCard icon={<Users className="h-5 w-5" />} label="Registered users" value={stats.users_total} />
                    <StatCard icon={<TagIcon className="h-5 w-5" />} label="Tags created" value={stats.tags_total} />
                    <StatCard icon={<MessageSquareText className="h-5 w-5" />} label="Finder messages" value={stats.messages_total} />
                    <StatCard icon={<HandHeart className="h-5 w-5" />} label="Sponsor intents" value={stats.sponsors_total} />
                </div>
            )}

            {stats?.recovery && <RecoveryPanel r={stats.recovery} />}

            <LandingSectionsPanel />

            {/* Scan trend + confirmed-recovery line — dependency-free mini chart */}
            <section className="surface p-6">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
                    <div className="flex items-center gap-2">
                        <BarChart3 className="h-4 w-4 text-accent" />
                        <h2 className="font-display font-bold">{t("recovery.chart_title")}</h2>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden="true">
                        <span className="inline-flex items-center gap-1">
                            <span className="inline-block w-3 h-3 rounded-sm bg-accent/70" /> {t("recovery.chart_scans")}
                        </span>
                        <span className="inline-flex items-center gap-1">
                            <span className="inline-block w-3 h-0.5 bg-emerald-500" /> {t("recovery.chart_recovered")}
                        </span>
                    </div>
                </div>
                {daily.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No scans yet. Share some tags!</p>
                ) : (
                    <TrendChart daily={daily} />
                )}
            </section>

            {/* Feedback + sponsors */}
            <Tabs defaultValue="feedback">
                <TabsList>
                    <TabsTrigger value="feedback" data-testid="tab-feedback">
                        Feedback {stats ? `(${stats.feedback.pending_review} pending)` : ""}
                    </TabsTrigger>
                    <TabsTrigger value="sponsors" data-testid="tab-sponsors">
                        Sponsors
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="feedback" className="mt-4 space-y-3">
                    {feedback === null ? (
                        <Skeleton className="h-24 rounded-xl" />
                    ) : feedback.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No feedback yet.</p>
                    ) : (
                        feedback.map((f) => (
                            <div key={f.id} className="surface p-4 flex flex-col sm:flex-row sm:items-start gap-3" data-testid="feedback-row">
                                <div className="flex-1 min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className="font-medium">{f.name || "Anonymous"}</span>
                                        {f.email && <span className="text-xs text-muted-foreground">{f.email}</span>}
                                        <span className="inline-flex items-center gap-0.5 text-amber-500 text-xs">
                                            {[...Array(f.rating || 5)].map((_, i) => (
                                                <Star key={i} className="h-3 w-3 fill-current" />
                                            ))}
                                        </span>
                                        <Badge variant={f.is_public ? "default" : "secondary"}>
                                            {f.is_public ? "Public" : "Hidden"}
                                        </Badge>
                                    </div>
                                    <p className="text-sm mt-1.5 whitespace-pre-wrap break-words">{f.message}</p>
                                    <p className="text-xs text-muted-foreground mt-1">{new Date(f.created_at).toLocaleString()}</p>
                                </div>
                                <div className="flex gap-2 shrink-0">
                                    {f.is_public ? (
                                        <Button size="sm" variant="outline" onClick={() => moderate(f.id, false)} className="gap-1.5">
                                            <EyeOff className="h-3.5 w-3.5" /> Hide
                                        </Button>
                                    ) : (
                                        <Button size="sm" onClick={() => moderate(f.id, true)} className="gap-1.5" data-testid="approve-feedback">
                                            <Eye className="h-3.5 w-3.5" /> Approve
                                        </Button>
                                    )}
                                    <Button size="sm" variant="destructive" onClick={() => removeFeedback(f.id)} className="gap-1.5">
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            </div>
                        ))
                    )}
                </TabsContent>

                <TabsContent value="sponsors" className="mt-4 space-y-3">
                    {sponsors === null ? (
                        <Skeleton className="h-24 rounded-xl" />
                    ) : sponsors.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No sponsor intents yet.</p>
                    ) : (
                        sponsors.map((s) => (
                            <div key={s.id} className="surface p-4" data-testid="sponsor-row">
                                <div className="flex flex-wrap items-center gap-2">
                                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                                    <span className="font-medium">{s.name}</span>
                                    {s.organization && <span className="text-xs text-muted-foreground">· {s.organization}</span>}
                                    <Badge variant="secondary">{s.tag_count} tags</Badge>
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">{s.email} · {new Date(s.created_at).toLocaleString()}</p>
                                {s.message && <p className="text-sm mt-1.5">{s.message}</p>}
                            </div>
                        ))
                    )}
                </TabsContent>
            </Tabs>
        </div>
    );
}

/**
 * LandingSectionsPanel — switch any landing-page section on or off.
 * Saved server-side (settings collection), applied instantly for every
 * visitor via /api/public/site-settings. Handy when the page feels long:
 * switch off what you don't need instead of editing code.
 */
function LandingSectionsPanel() {
    const [flags, setFlags] = useState(null);
    const [labels, setLabels] = useState({});

    useEffect(() => {
        api.get("/admin/settings")
            .then(({ data }) => {
                setFlags(data.landing_sections || {});
                setLabels(data.section_labels || {});
            })
            .catch((e) => toast.error(formatApiError(e)));
    }, []);

    const toggle = async (key, value) => {
        const prev = flags;
        setFlags({ ...flags, [key]: value }); // optimistic — feels instant
        try {
            await api.patch("/admin/settings", { landing_sections: { [key]: value } });
        } catch (e) {
            setFlags(prev);
            toast.error(formatApiError(e));
        }
    };

    return (
        <section className="surface p-6" data-testid="landing-sections-panel">
            <div className="flex items-center gap-2">
                <LayoutList className="h-4 w-4 text-accent" />
                <h2 className="font-display font-bold">Landing page sections</h2>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
                Switch off anything you don't want visitors to see — the page updates instantly, no deploy needed.
            </p>
            {flags === null ? (
                <Skeleton className="h-24 rounded-xl mt-4" />
            ) : (
                <div className="mt-4 grid sm:grid-cols-2 gap-x-8 gap-y-1">
                    {Object.entries(labels).map(([key, label]) => (
                        <label
                            key={key}
                            className="flex items-center justify-between gap-3 py-2 border-b border-border/60 last:border-0 sm:[&:nth-last-child(2)]:border-0 cursor-pointer"
                            data-testid={`section-toggle-${key}`}
                        >
                            <span className={`text-sm ${flags[key] ? "" : "text-muted-foreground line-through"}`}>{label}</span>
                            <Switch checked={!!flags[key]} onCheckedChange={(v) => toggle(key, v)} />
                        </label>
                    ))}
                </div>
            )}
        </section>
    );
}

/**
 * TrendChart — scan bars with an overlaid line of owner-confirmed
 * recoveries per day. The line has its own scale (recoveries are far fewer
 * than scans); exact numbers are in each column's tooltip / sr-only text.
 */
function TrendChart({ daily }) {
    const maxScans = Math.max(...daily.map((x) => x.count), 1);
    const maxRec = Math.max(...daily.map((x) => x.recovered || 0), 1);
    const n = daily.length;
    const points = daily
        .map((d, i) => `${((i + 0.5) / n) * 100},${100 - ((d.recovered || 0) / maxRec) * 90}`)
        .join(" ");
    return (
        <div data-testid="scan-trend">
            <div className="relative h-28">
                <div className="absolute inset-0 flex items-end gap-1.5">
                    {daily.map((d) => (
                        <div
                            key={d.day}
                            className="flex-1 h-full flex items-end"
                            title={`${d.day}: ${d.count} scans · ${d.recovered || 0} recovered`}
                        >
                            <div
                                className="w-full rounded-t bg-accent/70 min-h-[3px]"
                                style={{ height: `${Math.max(4, (d.count / maxScans) * 100)}%` }}
                            />
                            <span className="sr-only">{`${d.day}: ${d.count} scans, ${d.recovered || 0} recovered`}</span>
                        </div>
                    ))}
                </div>
                <svg
                    className="absolute inset-0 w-full h-full pointer-events-none overflow-visible"
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    aria-hidden="true"
                    data-testid="recovery-trend-line"
                >
                    <polyline
                        points={points}
                        fill="none"
                        stroke="rgb(16 185 129)"
                        strokeWidth="2"
                        strokeLinejoin="round"
                        vectorEffect="non-scaling-stroke"
                    />
                </svg>
            </div>
            <div className="flex gap-1.5 mt-1">
                {daily.map((d) => (
                    <span key={d.day} className="flex-1 text-center text-[9px] text-muted-foreground">
                        {d.day.slice(8)}
                    </span>
                ))}
            </div>
        </div>
    );
}

/**
 * RecoveryPanel — honest recovery numbers. Confirmed and probable are shown
 * side by side and never summed; the rate uses confirmed only.
 */
function RecoveryPanel({ r }) {
    const { t } = useI18n();
    const rate = r.recovery_rate == null ? "—" : `${Math.round(r.recovery_rate * 1000) / 10}%`;
    return (
        <section className="surface p-6" aria-labelledby="recovery-panel-title" data-testid="recovery-panel">
            <div className="flex items-center gap-2">
                <HeartHandshake className="h-4 w-4 text-emerald-500" />
                <h2 id="recovery-panel-title" className="font-display font-bold">{t("recovery.admin_title")}</h2>
            </div>
            <p className="text-sm text-muted-foreground mt-1">{t("recovery.admin_subtitle")}</p>
            <div className="mt-4 grid grid-cols-2 lg:grid-cols-5 gap-4">
                <StatCard icon={<ScanLine className="h-5 w-5" />} label={t("recovery.admin_total_scans")} value={r.total_scans} testId="rec-total-scans" />
                <StatCard
                    icon={<MessageSquareText className="h-5 w-5" />}
                    label={t("recovery.admin_finder_contacts")}
                    value={r.finder_contacts}
                    sub={`${r.awaiting_owner} ${t("recovery.admin_awaiting")}`}
                    testId="rec-finder-contacts"
                />
                <StatCard
                    icon={<PackageCheck className="h-5 w-5 text-emerald-500" />}
                    label={t("recovery.admin_confirmed")}
                    value={r.confirmed_recoveries}
                    sub={`${r.legacy_manual_found} ${t("recovery.admin_legacy")}`}
                    testId="rec-confirmed"
                />
                <StatCard
                    icon={<PackageCheck className="h-5 w-5 text-amber-500" />}
                    label={t("recovery.admin_probable")}
                    value={r.probable_unconfirmed}
                    sub={`${r.owner_not_found} ${t("recovery.admin_not_found")}`}
                    testId="rec-probable"
                />
                <StatCard
                    icon={<BarChart3 className="h-5 w-5" />}
                    label={t("recovery.admin_rate")}
                    value={rate}
                    sub={t("recovery.admin_rate_hint")}
                    testId="rec-rate"
                />
            </div>
            <p className="text-xs text-muted-foreground mt-3">{t("recovery.admin_public_note")}</p>
        </section>
    );
}

function StatCard({ icon, label, value, sub, testId }) {
    return (
        <div className="surface p-5" data-testid={testId}>
            <div className="flex items-center gap-2 text-muted-foreground">
                {icon}
                <span className="text-xs font-semibold uppercase tracking-wider">{label}</span>
            </div>
            <div className="font-display text-3xl font-black mt-2">{value ?? 0}</div>
            {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        </div>
    );
}
