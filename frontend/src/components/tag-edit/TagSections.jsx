/**
 * TagEdit sub-components.  Extracted from the original 234-line page so
 * each section is independently understandable + testable.
 */
import { MessageCircle, MessageSquare, Phone, ShieldCheck } from "lucide-react";

import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Switch } from "../ui/switch";
import { Textarea } from "../ui/textarea";

function Field({ label, children }) {
    return (
        <div className="space-y-1.5">
            <Label>{label}</Label>
            {children}
        </div>
    );
}

export function Section({ title, children }) {
    return (
        <section className="surface p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">{title}</h2>
            {children}
        </section>
    );
}

export function TagBasicSection({ tag, set, isNew, t }) {
    return (
        <Section title={t("tag_edit.section_basic")}>
            {isNew && (
                <Field label="Type">
                    <Select value={tag.type} onValueChange={(v) => set("type", v)}>
                        <SelectTrigger data-testid="tag-type-trigger"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {["vehicle", "pet", "luggage", "keys", "medical", "special", "general"].map((k) => (
                                <SelectItem key={k} value={k}>{t(`dashboard.${k}`)}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </Field>
            )}
            <Field label={t("tag_edit.label")}>
                <Input value={tag.label || ""} onChange={(e) => set("label", e.target.value)} placeholder="My Bike" data-testid="tag-label-input" />
            </Field>
            <Field label={t("tag_edit.display_name")}>
                <Input value={tag.display_name || ""} onChange={(e) => set("display_name", e.target.value)} placeholder="Royal Enfield Classic 350" data-testid="tag-displayname-input" />
            </Field>
            <Field label={t("tag_edit.message")}>
                <Textarea
                    value={tag.message || ""}
                    onChange={(e) => set("message", e.target.value)}
                    rows={3}
                    placeholder="If you see this bike parked badly or with lights on, tap below."
                    data-testid="tag-message-input"
                />
            </Field>
            {!isNew && (
                <Field label={t("tag_edit.section_status")}>
                    <Select value={tag.status} onValueChange={(v) => set("status", v)}>
                        <SelectTrigger data-testid="tag-status-trigger"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="active">{t("dashboard.status_active")}</SelectItem>
                            <SelectItem value="lost">{t("dashboard.status_lost")}</SelectItem>
                            <SelectItem value="found">{t("dashboard.status_found")}</SelectItem>
                        </SelectContent>
                    </Select>
                </Field>
            )}
        </Section>
    );
}

export function TagDataSection({ tag, set, fields, t }) {
    if (fields.length === 0) return null;
    return (
        <Section title={t("tag_edit.section_data")}>
            {fields.map((f) => (
                <Field key={f} label={t(`tag_edit.${f}`)}>
                    <Input
                        value={(tag.data && tag.data[f]) || ""}
                        onChange={(e) => set(`data.${f}`, e.target.value)}
                        data-testid={`tag-data-${f}`}
                    />
                </Field>
            ))}
        </Section>
    );
}

export function TagContactSection({ tag, set, t, hasPhone }) {
    const contact = tag.contact || { mode: "masked", show_call: true, show_whatsapp: true, show_sms: true };
    const setContact = (key, value) => set("contact", { ...contact, [key]: value });
    const isDirect = contact.mode === "direct";

    const modeCard = (mode, title, desc, Icon) => (
        <button
            type="button"
            onClick={() => setContact("mode", mode)}
            className={`text-left p-4 rounded-lg border-2 transition-colors ${
                contact.mode === mode ? "border-accent bg-accent/5" : "border-border hover:border-accent/40"
            }`}
            data-testid={`contact-mode-${mode}`}
        >
            <div className="flex items-center gap-2 font-semibold">
                <Icon className={`h-4 w-4 ${mode === "masked" ? "text-emerald-500" : "text-accent"}`} />
                {title}
            </div>
            <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{desc}</p>
        </button>
    );

    const channels = [
        { key: "show_call", label: t("tag_edit.contact_show_call"), Icon: Phone },
        { key: "show_whatsapp", label: t("tag_edit.contact_show_whatsapp"), Icon: MessageCircle },
        { key: "show_sms", label: t("tag_edit.contact_show_sms"), Icon: MessageSquare },
    ];

    return (
        <Section title={t("tag_edit.section_contact")}>
            <div className="grid sm:grid-cols-2 gap-3">
                {modeCard("masked", t("tag_edit.contact_mode_masked"), t("tag_edit.contact_mode_masked_desc"), ShieldCheck)}
                {modeCard("direct", t("tag_edit.contact_mode_direct"), t("tag_edit.contact_mode_direct_desc"), Phone)}
            </div>
            {isDirect && !hasPhone && (
                <p className="text-sm text-amber-600 dark:text-amber-400" data-testid="contact-needs-phone">
                    {t("tag_edit.contact_needs_phone")}
                </p>
            )}
            {isDirect && (
                <div className="grid sm:grid-cols-3 gap-3">
                    {channels.map(({ key, label, Icon }) => (
                        <label key={key} className="flex items-center justify-between p-3 rounded-md border gap-2">
                            <span className="text-sm inline-flex items-center gap-2">
                                <Icon className="h-4 w-4 text-muted-foreground" /> {label}
                            </span>
                            <Switch
                                checked={!!contact[key]}
                                onCheckedChange={(v) => setContact(key, v)}
                                data-testid={`contact-${key}`}
                            />
                        </label>
                    ))}
                </div>
            )}
        </Section>
    );
}

export function TagPublicFieldsSection({ tag, set, t }) {
    return (
        <Section title={t("tag_edit.section_public")}>
            <p className="text-sm text-muted-foreground -mt-2 mb-2">
                Toggle off any field you'd like to keep private. Owners' phone numbers are <em>never</em> exposed.
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
                {Object.keys(tag.public_fields || {}).map((key) => (
                    <label key={key} className="flex items-center justify-between p-3 rounded-md border">
                        <span className="text-sm capitalize">{key.replace(/_/g, " ")}</span>
                        <Switch
                            checked={!!tag.public_fields[key]}
                            onCheckedChange={(v) => set(`public_fields.${key}`, v)}
                            data-testid={`public-${key}`}
                        />
                    </label>
                ))}
            </div>
        </Section>
    );
}
