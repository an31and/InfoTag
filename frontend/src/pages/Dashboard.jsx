import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
    Bike,
    Briefcase,
    HandHeart,
    HeartPulse,
    Inbox,
    KeyRound,
    PawPrint,
    Plus,
    QrCode,
    ScanLine,
    Tag as TagIcon,
} from "lucide-react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import api, { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

const TYPE_META = {
    vehicle: { icon: Bike, color: "text-accent", bg: "bg-accent/10" },
    pet: { icon: PawPrint, color: "text-emerald-500", bg: "bg-emerald-500/10" },
    luggage: { icon: Briefcase, color: "text-sky-500", bg: "bg-sky-500/10" },
    keys: { icon: KeyRound, color: "text-amber-500", bg: "bg-amber-500/10" },
    medical: { icon: HeartPulse, color: "text-destructive", bg: "bg-destructive/10" },
    special: { icon: HandHeart, color: "text-sky-600", bg: "bg-sky-500/10" },
    general: { icon: TagIcon, color: "text-foreground", bg: "bg-muted" },
};

export default function DashboardPage() {
    const { t } = useI18n();
    const navigate = useNavigate();
    const [tags, setTags] = useState(null);
    const [error, setError] = useState("");
    const [filter, setFilter] = useState("all");
    const [inboxCount, setInboxCount] = useState(0);

    useEffect(() => {
        (async () => {
            try {
                const [{ data: tagList }, { data: inbox }] = await Promise.all([
                    api.get("/tags"),
                    api.get("/inbox"),
                ]);
                setTags(tagList);
                setInboxCount(inbox.length);
            } catch (e) {
                setError(formatApiError(e));
                setTags([]);
            }
        })();
    }, []);

    const stats = useMemo(() => {
        if (!tags) return null;
        return {
            active: tags.filter((tg) => tg.status === "active").length,
            total: tags.length,
        };
    }, [tags]);

    const filtered = useMemo(() => {
        if (!tags) return [];
        return filter === "all" ? tags : tags.filter((tg) => tg.type === filter);
    }, [tags, filter]);

    return (
        <div className="space-y-8" data-testid="dashboard-root">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <h1 className="font-display text-3xl sm:text-4xl font-black tracking-tight">{t("dashboard.title")}</h1>
                    <p className="text-muted-foreground mt-1">{t("common.tagline")}</p>
                </div>
                <Button onClick={() => navigate("/tags/new")} className="rounded-full gap-2" size="lg" data-testid="dashboard-new-tag-btn">
                    <Plus className="h-4 w-4" /> {t("dashboard.new_tag")}
                </Button>
            </div>

            {/* Stat strip */}
            <div className="grid sm:grid-cols-3 gap-4" data-testid="dashboard-stats">
                <StatTile
                    label={t("dashboard.active_tags")}
                    value={stats?.active ?? "—"}
                    icon={<TagIcon className="h-5 w-5" />}
                    testId="stat-active-tags"
                />
                <StatTile
                    label={t("dashboard.scans_today")}
                    value={stats ? stats.total : "—"}
                    icon={<ScanLine className="h-5 w-5" />}
                    testId="stat-scans"
                />
                <StatTile
                    label={t("dashboard.messages_today")}
                    value={inboxCount}
                    icon={<Inbox className="h-5 w-5" />}
                    onClick={() => navigate("/inbox")}
                    testId="stat-inbox"
                />
            </div>

            {/* Filter tabs */}
            <Tabs value={filter} onValueChange={setFilter} className="w-full">
                <TabsList className="flex flex-wrap gap-1 h-auto p-1 bg-muted/50">
                    {["all", "vehicle", "pet", "luggage", "keys", "medical", "special", "general"].map((k) => (
                        <TabsTrigger key={k} value={k} className="rounded-full text-sm px-4 py-1.5" data-testid={`tab-${k}`}>
                            {t(`dashboard.${k}`)}
                        </TabsTrigger>
                    ))}
                </TabsList>
                <TabsContent value={filter} className="mt-6">
                    <DashboardTagGrid tags={tags} filtered={filtered} onCreate={() => navigate("/tags/new")} />
                </TabsContent>
            </Tabs>

            {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
    );
}

function StatTile({ label, value, icon, onClick, testId }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className="surface p-5 text-left transition-transform hover:-translate-y-0.5 hover:border-foreground/30"
            data-testid={testId}
        >
            <div className="flex items-center justify-between">
                <div className="text-xs uppercase tracking-widest text-muted-foreground">{label}</div>
                <div className="text-muted-foreground">{icon}</div>
            </div>
            <div className="mt-3 font-display text-3xl font-black tracking-tight">
                {value === "—" ? (
                    <span className="inline-block h-8 w-12 rounded bg-muted animate-pulse-soft" aria-label="loading" />
                ) : (
                    value
                )}
            </div>
        </button>
    );
}

function DashboardTagGrid({ tags, filtered, onCreate }) {
    if (tags === null) return <SkeletonGrid />;
    if (filtered.length === 0) return <EmptyState onCreate={onCreate} />;
    return (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((tag) => (
                <TagCard key={tag.id} tag={tag} />
            ))}
        </div>
    );
}

function SkeletonGrid() {
    const placeholders = ["sk-a", "sk-b", "sk-c"];
    return (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {placeholders.map((id) => (
                <div key={id} className="surface p-5 space-y-3">
                    <Skeleton className="h-5 w-1/3" />
                    <Skeleton className="h-7 w-3/4" />
                    <Skeleton className="h-12 w-full" />
                </div>
            ))}
        </div>
    );
}

function EmptyState({ onCreate }) {
    const { t } = useI18n();
    return (
        <div className="surface p-10 text-center animate-rise">
            <div className="mx-auto inline-flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
                <Plus className="h-6 w-6" />
            </div>
            <h3 className="mt-4 font-display text-xl font-bold">{t("dashboard.empty_title")}</h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">{t("dashboard.empty_subtitle")}</p>
            <Button onClick={onCreate} className="mt-5 rounded-full" data-testid="empty-new-tag-btn">
                <Plus className="h-4 w-4 mr-1" /> {t("dashboard.new_tag")}
            </Button>
        </div>
    );
}

function TagCard({ tag }) {
    const { t } = useI18n();
    const meta = TYPE_META[tag.type] || TYPE_META.general;
    const Icon = meta.icon;
    const finderUrl = `${window.location.origin}/api/finder/${tag.slug}`;
    return (
        <div className="surface p-5 flex flex-col gap-4 animate-rise" data-testid={`tag-card-${tag.id}`}>
            <div className="flex items-start justify-between gap-3">
                <div className={`inline-flex items-center justify-center w-10 h-10 rounded-lg ${meta.bg}`}>
                    <Icon className={`h-5 w-5 ${meta.color}`} strokeWidth={2.4} />
                </div>
                <Badge variant={tag.status === "lost" ? "destructive" : "secondary"} data-testid={`tag-status-${tag.id}`}>
                    {t(`dashboard.status_${tag.status}`)}
                </Badge>
            </div>
            <div>
                <div className="text-xs uppercase tracking-widest text-muted-foreground">{t(`dashboard.${tag.type}`)}</div>
                <div className="font-display text-lg font-bold leading-tight mt-1 line-clamp-2">
                    {tag.display_name || tag.label || t("dashboard.untitled")}
                </div>
                <div className="text-xs text-muted-foreground mt-2 font-mono break-all">/tag/{tag.slug}</div>
            </div>
            <div className="flex flex-wrap gap-2 mt-auto">
                <Link to={`/tags/${tag.id}`} className="flex-1">
                    <Button variant="outline" size="sm" className="w-full rounded-full" data-testid={`edit-tag-${tag.id}`}>
                        {t("common.edit")}
                    </Button>
                </Link>
                <Link to={`/tags/${tag.id}/qr`}>
                    <Button variant="outline" size="sm" className="rounded-full gap-1" data-testid={`qr-tag-${tag.id}`}>
                        <QrCode className="h-4 w-4" /> QR
                    </Button>
                </Link>
                <a href={finderUrl} target="_blank" rel="noreferrer">
                    <Button variant="ghost" size="sm" className="rounded-full" data-testid={`preview-tag-${tag.id}`}>
                        {t("dashboard.preview")}
                    </Button>
                </a>
            </div>
        </div>
    );
}
