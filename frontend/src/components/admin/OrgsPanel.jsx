import { useEffect, useState } from "react";
import { Building2, Check, Copy, KeyRound, MessageCircle, Plus, UserMinus, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import { Switch } from "../ui/switch";
import api, { formatApiError } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

/**
 * OrgsPanel — admin creates organisations and organiser logins.
 * Organisers sign in on /login and only ever see their own events (the
 * backend enforces it; this panel just issues the credentials).
 */
export function OrgsPanel() {
    const { t } = useI18n();
    const [orgs, setOrgs] = useState(null);
    const [f, setF] = useState({ name: "", contact_name: "", contact_phone: "", contact_email: "", can_generate: false, max_tags_per_event: 5000 });

    const load = () => api.get("/admin/orgs").then(({ data }) => setOrgs(data)).catch((e) => toast.error(formatApiError(e)));
    useEffect(() => {
        load();
    }, []);

    const create = async (e) => {
        e.preventDefault();
        try {
            await api.post("/admin/orgs", { ...f, max_tags_per_event: Number(f.max_tags_per_event) || 5000 });
            setF({ ...f, name: "", contact_name: "", contact_phone: "", contact_email: "" });
            load();
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };
    const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));

    return (
        <section className="surface p-6 space-y-4" data-testid="orgs-panel">
            <div>
                <h2 className="font-display font-bold flex items-center gap-2"><Building2 className="h-4 w-4 text-accent" />{t("orgs.title")}</h2>
                <p className="text-sm text-muted-foreground mt-1">{t("orgs.lead")}</p>
            </div>
            <form onSubmit={create} className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
                <Input required minLength={2} placeholder={t("orgs.name")} value={f.name} onChange={set("name")} data-testid="org-name" />
                <Input placeholder={t("orgs.contact_name")} value={f.contact_name} onChange={set("contact_name")} />
                <Input placeholder={t("orgs.contact_phone")} value={f.contact_phone} onChange={set("contact_phone")} />
                <Input placeholder={t("orgs.contact_email")} value={f.contact_email} onChange={set("contact_email")} />
                <label className="flex items-center gap-2 text-sm"><Switch checked={f.can_generate} onCheckedChange={set("can_generate")} />{t("orgs.can_generate")}</label>
                <label className="flex items-center gap-2 text-sm">{t("orgs.max_tags")}
                    <Input type="number" min={1} className="w-28" value={f.max_tags_per_event} onChange={set("max_tags_per_event")} />
                </label>
                <Button type="submit" className="gap-2 lg:col-start-4" data-testid="org-create"><Plus className="h-4 w-4" />{t("orgs.create")}</Button>
            </form>
            {orgs === null ? <Skeleton className="h-20" /> : orgs.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("orgs.none")}</p>
            ) : (
                <div className="space-y-3">{orgs.map((o) => <OrgCard key={o.id} org={o} onChange={load} />)}</div>
            )}
        </section>
    );
}

function OrgCard({ org, onChange }) {
    const { t } = useI18n();
    const [open, setOpen] = useState(false);
    const [members, setMembers] = useState(null);
    const [m, setM] = useState({ email: "", display_name: "" });
    const [creds, setCreds] = useState(null);

    const loadMembers = () => api.get(`/admin/orgs/${org.id}/members`).then(({ data }) => setMembers(data)).catch((e) => toast.error(formatApiError(e)));
    useEffect(() => {
        if (open) loadMembers();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const patch = async (body) => {
        try {
            await api.patch(`/admin/orgs/${org.id}`, body);
            onChange();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    const add = async (e) => {
        e.preventDefault();
        try {
            const { data } = await api.post(`/admin/orgs/${org.id}/members`, m);
            setCreds(data);
            setM({ email: "", display_name: "" });
            loadMembers();
            onChange();
        } catch (err) {
            toast.error(formatApiError(err));
        }
    };
    const reset = async (u) => {
        try {
            const { data } = await api.post(`/admin/orgs/${org.id}/members/${u.id}/reset-password`);
            setCreds({ ...data, org_name: org.name });
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };
    const remove = async (u) => {
        try {
            await api.delete(`/admin/orgs/${org.id}/members/${u.id}`);
            loadMembers();
            onChange();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    return (
        <div className="rounded-lg border p-4" data-testid="org-card">
            <div className="flex flex-wrap items-center gap-3">
                <button type="button" className="font-semibold text-left" onClick={() => setOpen(!open)}>{org.name}</button>
                <Badge variant="secondary">{org.members} · {t("orgs.members")}</Badge>
                <Badge variant="outline">{org.events} {t("orgs.events")}</Badge>
                <span className="ml-auto flex flex-wrap items-center gap-4 text-sm">
                    <label className="flex items-center gap-2"><Switch checked={org.can_generate} onCheckedChange={(v) => patch({ can_generate: v })} />{t("orgs.can_generate")}</label>
                    <label className="flex items-center gap-2"><Switch checked={org.active} onCheckedChange={(v) => patch({ active: v })} />{t("orgs.active")}</label>
                    <Button size="sm" variant="outline" onClick={() => setOpen(!open)} className="gap-1"><UserPlus className="h-3.5 w-3.5" />{t("orgs.members")}</Button>
                </span>
            </div>
            {open && (
                <div className="mt-4 space-y-3">
                    <form onSubmit={add} className="flex flex-wrap gap-2">
                        <Input type="email" required placeholder={t("orgs.email")} className="w-64" value={m.email} onChange={(e) => setM({ ...m, email: e.target.value })} data-testid="member-email" />
                        <Input placeholder={t("orgs.display_name")} className="w-48" value={m.display_name} onChange={(e) => setM({ ...m, display_name: e.target.value })} />
                        <Button type="submit" className="gap-1.5" data-testid="member-add"><UserPlus className="h-4 w-4" />{t("orgs.add_member")}</Button>
                    </form>
                    {creds && <Credentials creds={creds} onClose={() => setCreds(null)} />}
                    <ul className="divide-y text-sm">
                        {(members || []).map((u) => (
                            <li key={u.id} className="py-2 flex flex-wrap items-center gap-2">
                                <span className="font-medium">{u.display_name}</span>
                                <span className="text-muted-foreground">{u.email}</span>
                                <span className="ml-auto flex gap-1">
                                    <Button size="sm" variant="ghost" className="gap-1" onClick={() => reset(u)}><KeyRound className="h-3.5 w-3.5" />{t("orgs.reset")}</Button>
                                    <Button size="sm" variant="ghost" className="gap-1 text-destructive" onClick={() => remove(u)}><UserMinus className="h-3.5 w-3.5" />{t("orgs.remove")}</Button>
                                </span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

function Credentials({ creds, onClose }) {
    const { t } = useI18n();
    const [copied, setCopied] = useState(false);
    const loginUrl = `${window.location.origin}/login`;
    if (!creds.password) {
        return <div className="rounded-lg bg-muted p-3 text-sm">{t("orgs.linked")} <Button size="sm" variant="ghost" onClick={onClose}>OK</Button></div>;
    }
    const text = `Info-Tag — ${creds.org_name || ""}\n${t("orgs.login_url")}: ${loginUrl}\nEmail: ${creds.email}\n${t("orgs.password")}: ${creds.password}`;
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            toast.error("Copy failed");
        }
    };
    return (
        <div className="rounded-lg border-2 border-accent/40 bg-accent/5 p-4 space-y-2" data-testid="member-credentials">
            <p className="text-sm font-semibold">{t("orgs.credentials")}</p>
            <pre className="text-sm whitespace-pre-wrap font-mono bg-background rounded p-3 border">{text}</pre>
            <div className="flex flex-wrap gap-2">
                <Button size="sm" className="gap-1.5" onClick={copy}>{copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{copied ? t("orgs.copied") : t("orgs.copy")}</Button>
                <Button asChild size="sm" variant="outline" className="gap-1.5">
                    <a href={`https://wa.me/?text=${encodeURIComponent(text)}`} target="_blank" rel="noreferrer"><MessageCircle className="h-3.5 w-3.5" />{t("orgs.share_wa")}</a>
                </Button>
                <Button size="sm" variant="ghost" onClick={onClose}>OK</Button>
            </div>
        </div>
    );
}
