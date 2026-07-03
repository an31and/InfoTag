import { useEffect, useState } from "react";
import { HandHeart, Send } from "lucide-react";
import { toast } from "sonner";

import api, { formatApiError } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { useI18n } from "../lib/i18n";

/**
 * SponsorSection — civic enhancement that funds free physical stickers.
 *
 * Companies, schools, RWAs and individuals can pledge how many tags they'd
 * like to sponsor.  We collect the intent here; printing & distribution
 * happen offline.
 */
export function SponsorSection() {
    const { t } = useI18n();
    const [stats, setStats] = useState(null);
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({ name: "", email: "", organization: "", tag_count: 50, message: "", bot_check: "" });
    const [state, setState] = useState("idle");

    useEffect(() => {
        api.get("/sponsors/stats").then((r) => setStats(r.data)).catch(() => setStats({ total_pledged: 0, sponsor_count: 0 }));
    }, []);

    const submit = async (e) => {
        e.preventDefault();
        setState("sending");
        try {
            await api.post("/sponsors", form);
            toast.success("Thank you! We'll be in touch.");
            setState("sent");
            setForm({ name: "", email: "", organization: "", tag_count: 50, message: "", bot_check: "" });
            setOpen(false);
        } catch (err) {
            toast.error(formatApiError(err));
            setState("error");
        }
    };

    return (
        <section className="border-y bg-accent/5">
            <div className="mx-auto max-w-6xl px-4 sm:px-8 py-16 grid lg:grid-cols-12 gap-10 items-start">
                <div className="lg:col-span-5">
                    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border bg-card text-xs font-semibold tracking-wider uppercase">
                        <HandHeart className="h-3.5 w-3.5 text-accent" /> Sponsor a tag
                    </span>
                    <h2 className="mt-4 font-display text-3xl sm:text-4xl font-black tracking-tight leading-tight">
                        Fund printed stickers, free for an Indian family.
                    </h2>
                    <p className="mt-4 text-muted-foreground">
                        Info-Tag is and will always be free. But weather-proof printed stickers cost money. Sponsor a batch — we'll add a small "Sponsored by you" footer on the PDF and ship them to RTOs, pet shelters, hospitals and senior-citizen groups.
                    </p>
                    {stats && (
                        <div className="mt-6 flex gap-6">
                            <Stat n={Number(stats.total_pledged || 0).toLocaleString("en-IN")} label="stickers pledged" />
                            <Stat n={Number(stats.sponsor_count || 0).toLocaleString("en-IN")} label="kind humans" />
                        </div>
                    )}
                    {!open && (
                        <Button onClick={() => setOpen(true)} className="mt-6 rounded-full gap-2" data-testid="sponsor-open-btn">
                            <HandHeart className="h-4 w-4" /> I'd like to sponsor
                        </Button>
                    )}
                </div>
                {open && (
                    <form onSubmit={submit} className="lg:col-span-7 surface p-6 sm:p-8 space-y-4 animate-rise" data-testid="sponsor-form">
                        <div className="grid sm:grid-cols-2 gap-4">
                            <Field label="Your name">
                                <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="sponsor-name" />
                            </Field>
                            <Field label="Email">
                                <Input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="sponsor-email" />
                            </Field>
                            <Field label="Organization (optional)">
                                <Input value={form.organization} onChange={(e) => setForm({ ...form, organization: e.target.value })} data-testid="sponsor-org" />
                            </Field>
                            <Field label="How many stickers?">
                                <Input
                                    required
                                    type="number"
                                    min={1}
                                    max={100000}
                                    value={form.tag_count}
                                    onChange={(e) => setForm({ ...form, tag_count: parseInt(e.target.value || "0", 10) || 1 })}
                                    data-testid="sponsor-count"
                                />
                            </Field>
                        </div>
                        <Field label="A note for us (optional)">
                            <Textarea rows={3} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} data-testid="sponsor-message" />
                        </Field>
                        {/* Honeypot */}
                        <input
                            type="text"
                            value={form.bot_check}
                            onChange={(e) => setForm({ ...form, bot_check: e.target.value })}
                            tabIndex={-1}
                            autoComplete="off"
                            className="absolute left-[-9999px] top-[-9999px]"
                            aria-hidden="true"
                        />
                        <div className="flex items-center gap-3 justify-end">
                            <Button type="button" variant="ghost" onClick={() => setOpen(false)} data-testid="sponsor-cancel">Cancel</Button>
                            <Button type="submit" disabled={state === "sending"} className="rounded-full gap-2" data-testid="sponsor-submit">
                                <Send className="h-4 w-4" />
                                {state === "sending" ? t("common.loading") : "Send pledge"}
                            </Button>
                        </div>
                    </form>
                )}
            </div>
        </section>
    );
}

function Stat({ n, label }) {
    return (
        <div>
            <div className="font-display text-3xl font-black tracking-tight">{n}</div>
            <div className="text-xs uppercase tracking-widest text-muted-foreground mt-1">{label}</div>
        </div>
    );
}

function Field({ label, children }) {
    return (
        <div className="space-y-1.5">
            <Label>{label}</Label>
            {children}
        </div>
    );
}
