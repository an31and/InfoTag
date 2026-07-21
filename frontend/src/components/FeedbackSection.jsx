import { useEffect, useState } from "react";
import { MessageSquareHeart, Send, Star } from "lucide-react";

import api, { formatApiError } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { useI18n } from "../lib/i18n";

/**
 * FeedbackSection — public testimonials + a "share your experience" form.
 *
 * Only admin-approved feedback is shown (GET /public/feedback returns
 * is_public=true entries only). Submissions are honeypot-protected and
 * land in the admin portal's moderation queue.
 */
export function FeedbackSection() {
    const { t } = useI18n();
    const [items, setItems] = useState([]);
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [message, setMessage] = useState("");
    const [rating, setRating] = useState(5);
    const [botCheck, setBotCheck] = useState(""); // honeypot
    const [sending, setSending] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        api.get("/public/feedback")
            .then(({ data }) => setItems(data || []))
            .catch(() => {}); // testimonials are decorative — never block the page
    }, []);

    const submit = async (e) => {
        e.preventDefault();
        setError("");
        if (!message.trim()) {
            setError(t("feedback.write_something"));
            return;
        }
        setSending(true);
        try {
            await api.post("/public/feedback", {
                name,
                email,
                message,
                rating,
                bot_check: botCheck,
            });
            setSent(true);
            setName("");
            setEmail("");
            setMessage("");
        } catch (err) {
            setError(formatApiError(err));
        } finally {
            setSending(false);
        }
    };

    return (
        <section id="feedback" className="border-t bg-muted/30">
            <div className="mx-auto max-w-6xl px-4 sm:px-8 py-16 grid lg:grid-cols-2 gap-10">
                {/* Testimonials */}
                <div>
                    <div className="flex items-center gap-2">
                        <MessageSquareHeart className="h-5 w-5 text-accent" />
                        <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">
                            {t("feedback.title")}
                        </h2>
                    </div>
                    <p className="text-sm text-muted-foreground mt-2 max-w-md">
                        {t("feedback.lead")}
                    </p>
                    <div className="mt-6 space-y-4">
                        {items.length === 0 ? (
                            <p className="text-sm text-muted-foreground surface p-5">
                                {t("feedback.empty")}
                            </p>
                        ) : (
                            items.slice(0, 6).map((f) => (
                                <blockquote key={f.id} className="surface p-5" data-testid="testimonial">
                                    <div className="flex items-center gap-0.5 text-amber-500">
                                        {[...Array(f.rating || 5)].map((_, i) => (
                                            <Star key={i} className="h-3.5 w-3.5 fill-current" />
                                        ))}
                                    </div>
                                    <p className="text-sm mt-2 leading-relaxed">{f.message}</p>
                                    <footer className="text-xs text-muted-foreground mt-2 font-medium">
                                        — {f.name || t("feedback.anonymous")}
                                    </footer>
                                </blockquote>
                            ))
                        )}
                    </div>
                </div>

                {/* Submission form */}
                <div className="surface p-6 sm:p-8 h-fit">
                    <h3 className="font-display font-bold text-lg">{t("feedback.form_title")}</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                        {t("feedback.form_lead")}
                    </p>
                    {sent ? (
                        <p className="mt-6 text-sm text-emerald-600 font-medium" data-testid="feedback-sent">
                            {t("feedback.sent")}
                        </p>
                    ) : (
                        <form onSubmit={submit} className="mt-5 space-y-3" data-testid="feedback-form">
                            <div className="grid sm:grid-cols-2 gap-3">
                                <Input
                                    placeholder={t("feedback.name_ph")}
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    maxLength={120}
                                    data-testid="feedback-name"
                                />
                                <Input
                                    type="email"
                                    placeholder={t("feedback.email_ph")}
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    maxLength={160}
                                    data-testid="feedback-email"
                                />
                            </div>
                            <Textarea
                                placeholder={t("feedback.message_ph")}
                                value={message}
                                onChange={(e) => setMessage(e.target.value)}
                                maxLength={1000}
                                rows={4}
                                required
                                data-testid="feedback-message"
                            />
                            {/* Honeypot — visually hidden; bots fill it, humans never see it */}
                            <input
                                type="text"
                                value={botCheck}
                                onChange={(e) => setBotCheck(e.target.value)}
                                tabIndex={-1}
                                autoComplete="off"
                                aria-hidden="true"
                                style={{ position: "absolute", left: "-9999px", height: 0, width: 0, opacity: 0 }}
                            />
                            <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-1" aria-label="Rating">
                                    {[1, 2, 3, 4, 5].map((n) => (
                                        <button
                                            key={n}
                                            type="button"
                                            onClick={() => setRating(n)}
                                            className="p-0.5"
                                            aria-label={`${n} star`}
                                        >
                                            <Star
                                                className={`h-5 w-5 ${n <= rating ? "text-amber-500 fill-current" : "text-muted-foreground/40"}`}
                                            />
                                        </button>
                                    ))}
                                </div>
                                <Button type="submit" disabled={sending} className="gap-2" data-testid="feedback-submit">
                                    <Send className="h-4 w-4" /> {sending ? t("feedback.sending") : t("feedback.send")}
                                </Button>
                            </div>
                            {error && <p className="text-sm text-destructive">{error}</p>}
                        </form>
                    )}
                </div>
            </div>
        </section>
    );
}
