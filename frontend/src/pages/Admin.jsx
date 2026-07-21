import { useEffect, useState } from "react";
import {
    BarChart3,
    CheckCircle2,
    Eye,
    EyeOff,
    HandHeart,
    LayoutList,
    MessageCircle,
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

/**
 * AdminPage — founder-only portal.
 *
 * Visibility of this page is gated in App.js (role === "admin"), but the
 * real security boundary is the backend: every /api/admin/* endpoint
 * re-verifies the role server-side.
 */
export default function AdminPage() {
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

            <LandingSectionsPanel />

            <WhatsAppDiagnostics />

            {/* Scan trend — dependency-free mini bar chart */}
            <section className="surface p-6">
                <div className="flex items-center gap-2 mb-4">
                    <BarChart3 className="h-4 w-4 text-accent" />
                    <h2 className="font-display font-bold">Scans — last 14 days</h2>
                </div>
                {daily.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No scans yet. Share some tags!</p>
                ) : (
                    <div className="flex items-end gap-1.5 h-28" data-testid="scan-trend">
                        {daily.map((d) => {
                            const max = Math.max(...daily.map((x) => x.count), 1);
                            return (
                                <div key={d.day} className="flex-1 flex flex-col items-center gap-1" title={`${d.day}: ${d.count}`}>
                                    <div
                                        className="w-full rounded-t bg-accent/70 min-h-[3px]"
                                        style={{ height: `${Math.max(4, (d.count / max) * 100)}%` }}
                                    />
                                    <span className="text-[9px] text-muted-foreground">{d.day.slice(8)}</span>
                                </div>
                            );
                        })}
                    </div>
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
 * WhatsAppDiagnostics — makes the invisible visible. `send_whatsapp` in the
 * request path swallows errors, so a misconfigured setup fails silently.
 * This panel calls the admin diagnostic endpoints and shows Meta's *actual*
 * response, so the reason a message didn't go out is obvious.
 */
function WhatsAppDiagnostics() {
    const [health, setHealth] = useState(null);
    const [checking, setChecking] = useState(false);
    const [to, setTo] = useState("");
    const [testResult, setTestResult] = useState(null);
    const [sending, setSending] = useState(false);

    const runHealth = async () => {
        setChecking(true);
        setHealth(null);
        try {
            const { data } = await api.get("/admin/whatsapp/health");
            setHealth(data);
        } catch (e) {
            setHealth({ error: formatApiError(e) });
        } finally {
            setChecking(false);
        }
    };

    const sendTest = async () => {
        setSending(true);
        setTestResult(null);
        try {
            const { data } = await api.post("/admin/whatsapp/test", { to });
            setTestResult(data);
        } catch (e) {
            setTestResult({ error: formatApiError(e) });
        } finally {
            setSending(false);
        }
    };

    const cfg = health?.config;
    const Dot = ({ ok }) => (
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
    );

    return (
        <section className="surface p-6" data-testid="whatsapp-diagnostics">
            <div className="flex items-center gap-2">
                <MessageCircle className="h-4 w-4 text-emerald-600" />
                <h2 className="font-display font-bold">WhatsApp diagnostics</h2>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
                Not receiving WhatsApp alerts? Run a health check, then send a test to your own number — the result shows exactly what Meta says.
            </p>

            <div className="mt-4 flex flex-wrap gap-2">
                <Button size="sm" onClick={runHealth} disabled={checking} data-testid="wa-health-btn">
                    {checking ? "Checking…" : "Run health check"}
                </Button>
            </div>

            {cfg && (
                <div className="mt-4 grid sm:grid-cols-2 gap-x-8 gap-y-1.5 text-sm">
                    {[
                        ["Access token set", cfg.token_set],
                        ["Phone number ID set", cfg.phone_number_id_set],
                        ["Business number set", cfg.business_number_set],
                        ["Webhook verify token set", cfg.verify_token_set],
                        ["App secret set (signatures)", cfg.app_secret_set],
                        ["WhatsApp enabled", cfg.enabled],
                    ].map(([label, ok]) => (
                        <div key={label} className="flex items-center gap-2">
                            <Dot ok={ok} /> <span className={ok ? "" : "text-muted-foreground"}>{label}</span>
                        </div>
                    ))}
                </div>
            )}
            {health?.probe && (
                <div className="mt-3 text-sm">
                    <span className="font-medium">Live token check: </span>
                    {health.probe.ok ? (
                        <span className="text-emerald-600">
                            ✓ Valid — number {health.probe.response?.display_phone_number || ""} ({health.probe.response?.verified_name || ""})
                        </span>
                    ) : (
                        <span className="text-red-600">✗ {health.probe.reason || `HTTP ${health.probe.status_code}`}</span>
                    )}
                    {!health.probe.ok && health.probe.response && (
                        <pre className="mt-2 text-xs bg-muted rounded-md p-3 overflow-x-auto">{JSON.stringify(health.probe.response, null, 2)}</pre>
                    )}
                </div>
            )}
            {health?.error && <p className="mt-3 text-sm text-destructive">{health.error}</p>}

            <div className="mt-5 border-t border-border/60 pt-4">
                <label className="text-sm font-medium">Send a test message</label>
                <div className="mt-2 flex flex-wrap gap-2">
                    <input
                        type="tel"
                        value={to}
                        onChange={(e) => setTo(e.target.value)}
                        placeholder="+91 98765 43210"
                        className="flex-1 min-w-[200px] rounded-md border border-border bg-background px-3 py-2 text-sm"
                        data-testid="wa-test-number"
                    />
                    <Button size="sm" onClick={sendTest} disabled={sending || !to} data-testid="wa-test-btn">
                        {sending ? "Sending…" : "Send test"}
                    </Button>
                </div>
                {testResult && (
                    <div className="mt-3 text-sm">
                        {testResult.error ? (
                            <p className="text-destructive">{testResult.error}</p>
                        ) : testResult.ok ? (
                            <p className="text-emerald-600">✓ Meta accepted the message (HTTP {testResult.status_code}). Check that phone for the message.</p>
                        ) : (
                            <>
                                <p className="text-red-600">✗ {testResult.reason || `Meta rejected it (HTTP ${testResult.status_code})`}</p>
                                {testResult.response && (
                                    <pre className="mt-2 text-xs bg-muted rounded-md p-3 overflow-x-auto">{JSON.stringify(testResult.response, null, 2)}</pre>
                                )}
                            </>
                        )}
                    </div>
                )}
                <p className="mt-2 text-xs text-muted-foreground">
                    Tip: WhatsApp only allows a free message if that number messaged your business first in the last 24h. If the test fails with a
                    "re-engagement"/131047 error, open the window by messaging your business number, then retry.
                </p>
            </div>
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
