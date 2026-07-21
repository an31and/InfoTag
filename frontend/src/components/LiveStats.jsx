import { useEffect, useState } from "react";
import { PackageCheck, ScanLine, Tag, Users } from "lucide-react";

import api from "../lib/api";
import { useI18n } from "../lib/i18n";

/**
 * LiveStats — public social-proof counters pulled from /api/public/stats.
 * Renders nothing until data arrives so the hero never jumps.
 */
export function LiveStats() {
    const { t } = useI18n();
    const [stats, setStats] = useState(null);

    useEffect(() => {
        api.get("/public/stats")
            .then(({ data }) => setStats(data))
            .catch(() => {}); // counters are decorative — never block the page
    }, []);

    if (!stats) return null;

    const items = [
        { icon: ScanLine, label: t("stats.scans"), value: stats.scans_total },
        { icon: PackageCheck, label: t("stats.recovered"), value: stats.items_recovered },
        { icon: Tag, label: t("stats.active"), value: stats.tags_active },
        { icon: Users, label: t("stats.visitors"), value: stats.visitors_total },
    ];

    return (
        <div className="border-y bg-card/60" data-testid="live-stats">
            <div className="mx-auto max-w-6xl px-4 sm:px-8 py-6 grid grid-cols-2 md:grid-cols-4 gap-4">
                {items.map(({ icon: Icon, label, value }) => (
                    <div key={label} className="flex items-center gap-3">
                        <div className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-accent/10 shrink-0">
                            <Icon className="h-4 w-4 text-accent" />
                        </div>
                        <div>
                            <div className="font-display font-black text-xl leading-none">
                                {Number(value || 0).toLocaleString("en-IN")}
                            </div>
                            <div className="text-[11px] text-muted-foreground mt-0.5 uppercase tracking-wider font-semibold">
                                {label}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
