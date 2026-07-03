/**
 * Landing page — TagIT-style redesign.
 *
 * Structure mirrors the approved mock: dark hero with an interactive QR tag
 * (tap → live finder demo), 3 simple steps, 8 use-case cards on a dark band,
 * feature grid with Core/New badges, free "products", FAQ accordion, saffron
 * CTA band and a dark footer.  All copy is deliberately 5th-grader simple and
 * lives in the i18n dictionary (EN + HI, other languages fall back to EN).
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Cloud, Instagram, Linkedin, Mail, Phone, PhoneCall, MessageCircle, Siren, Tag, Users, X } from "lucide-react";

import { Button } from "../components/ui/button";
import { FeedbackSection } from "../components/FeedbackSection";
import { LiveStats } from "../components/LiveStats";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { SponsorSection } from "../components/SponsorSection";
import { ThemeToggle } from "../components/ThemeToggle";
import { useI18n } from "../lib/i18n";
import { useAuth } from "../lib/auth";

const INK = "#0E1326";

/* Reveal-on-scroll: adds .in to .reveal elements as they enter the viewport */
function useReveal() {
    useEffect(() => {
        if (!("IntersectionObserver" in window)) {
            document.querySelectorAll(".reveal").forEach((el) => el.classList.add("in"));
            return undefined;
        }
        const io = new IntersectionObserver(
            (entries) => {
                entries.forEach((e) => {
                    if (e.isIntersecting) {
                        e.target.classList.add("in");
                        io.unobserve(e.target);
                    }
                });
            },
            { threshold: 0.12 }
        );
        document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
        return () => io.disconnect();
    }, []);
}

export default function LandingPage() {
    const { t } = useI18n();
    const { user } = useAuth();
    const navigate = useNavigate();
    const [demoOpen, setDemoOpen] = useState(false);
    useReveal();

    const goStart = () => navigate(user ? "/dashboard" : "/signup");

    return (
        <div className="min-h-screen">
            {/* ---------------- Sticky nav ---------------- */}
            <nav className="sticky top-0 z-50 backdrop-blur-md bg-background/85 border-b">
                <div className="mx-auto max-w-6xl px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
                    <Link to="/" className="flex items-center gap-2 font-display font-black text-xl tracking-tight" data-testid="landing-brand">
                        <span className="w-7 h-7 rounded-lg bg-primary text-primary-foreground grid place-items-center">
                            <Tag className="h-4 w-4" strokeWidth={2.5} />
                        </span>
                        <span>Info-<span className="text-accent">Tag</span></span>
                    </Link>
                    <ul className="hidden md:flex items-center gap-6 text-sm font-medium text-muted-foreground">
                        <li><a href="#how" className="hover:text-foreground">{t("landing.nav_how")}</a></li>
                        <li><a href="#usecases" className="hover:text-foreground">{t("landing.nav_uses")}</a></li>
                        <li><a href="#features" className="hover:text-foreground">{t("landing.nav_features")}</a></li>
                        <li><a href="#products" className="hover:text-foreground">{t("landing.nav_tags")}</a></li>
                        <li><a href="#faq" className="hover:text-foreground">{t("landing.nav_faq")}</a></li>
                    </ul>
                    <div className="flex items-center gap-1">
                        <LanguageSwitcher compact />
                        <ThemeToggle />
                        <Button variant="ghost" size="sm" onClick={() => navigate(user ? "/dashboard" : "/login")} data-testid="landing-sign-in">
                            {t("common.sign_in")}
                        </Button>
                        <Button size="sm" className="rounded-full" onClick={goStart} data-testid="landing-sign-up">
                            {user ? t("common.dashboard") : t("landing.cta_primary")}
                        </Button>
                    </div>
                </div>
            </nav>

            {/* ---------------- Hero (always dark, like the mock) ---------------- */}
            <header className="relative overflow-hidden text-white" style={{ background: INK }}>
                <div
                    className="absolute inset-0 pointer-events-none"
                    style={{
                        background:
                            "radial-gradient(700px 380px at 80% 15%, rgba(255,107,26,.16), transparent 65%), radial-gradient(500px 320px at 8% 90%, rgba(255,107,26,.07), transparent 60%)",
                    }}
                />
                <div className="relative z-10 mx-auto max-w-6xl px-4 sm:px-6 py-16 sm:py-24 grid lg:grid-cols-2 gap-12 items-center">
                    <div className="text-center lg:text-left">
                        <span className="font-mono text-xs tracking-[0.14em] uppercase text-accent">{t("landing.hero_kicker")}</span>
                        <h1 className="mt-4 font-display text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight leading-[1.05]">
                            {t("landing.hero_title")} <span className="text-accent">{t("landing.hero_title_hl")}</span>
                        </h1>
                        <p className="mt-5 text-lg text-white/70 max-w-xl mx-auto lg:mx-0">{t("landing.hero_subtitle")}</p>
                        <div className="mt-8 flex flex-wrap gap-3 justify-center lg:justify-start">
                            <Button size="lg" className="rounded-full bg-accent hover:bg-accent/90 text-white shadow-lg shadow-accent/30" onClick={goStart} data-testid="hero-cta-primary">
                                {t("landing.cta_primary")}
                            </Button>
                            <Button
                                size="lg"
                                variant="outline"
                                className="rounded-full bg-transparent text-white border-white/40 hover:bg-white hover:text-slate-900"
                                onClick={() => setDemoOpen(true)}
                                data-testid="hero-cta-demo"
                            >
                                {t("landing.cta_demo")}
                            </Button>
                        </div>
                        <p className="mt-7 font-mono text-[11px] tracking-[0.08em] text-white/45">{t("landing.hero_note")}</p>
                    </div>

                    {/* Interactive QR tag */}
                    <div className="flex justify-center">
                        <button
                            type="button"
                            onClick={() => setDemoOpen(true)}
                            aria-label={t("landing.cta_demo")}
                            className="qr-hero-tag text-left"
                            data-testid="hero-qr-tag"
                        >
                            <span className="flex items-center justify-between mb-4">
                                <span className="font-display font-black text-lg text-slate-900">Info-<span className="text-accent">Tag</span></span>
                                <span className="font-mono text-[10px] tracking-[0.08em] text-slate-500">TAG-IN-0001</span>
                            </span>
                            <span className="relative block bg-white border-2 border-slate-900 rounded-xl p-3 overflow-hidden">
                                <DemoQr />
                                <span className="absolute left-1.5 right-1.5 h-[3px] rounded bg-gradient-to-r from-transparent via-accent to-transparent animate-scan-sweep shadow-[0_0_14px_rgba(255,107,26,0.8)]" aria-hidden="true" />
                            </span>
                            <span className="mt-4 flex items-center justify-between">
                                <span className="font-semibold text-sm text-slate-900">{t("landing.tag_scan_to_reach")}</span>
                                <span className="font-mono text-[10px] tracking-[0.1em] text-accent animate-pulse-soft">{t("landing.tag_tap_demo")}</span>
                            </span>
                        </button>
                    </div>
                </div>
            </header>

            {demoOpen && <ScanDemo t={t} onClose={() => setDemoOpen(false)} />}

            <LiveStats />

            {/* ---------------- How it works ---------------- */}
            <section id="how" className="py-16 sm:py-20">
                <div className="mx-auto max-w-6xl px-4 sm:px-6">
                    <span className="font-mono text-xs tracking-[0.14em] uppercase text-accent">{t("landing.how_it_works")}</span>
                    <h2 className="mt-3 font-display text-3xl sm:text-4xl font-bold tracking-tight">{t("landing.how_title")}</h2>
                    <p className="mt-3 text-muted-foreground max-w-xl">{t("landing.how_lead")}</p>
                    <div className="mt-10 grid md:grid-cols-3 gap-6">
                        {[1, 2, 3].map((n) => (
                            <div key={n} className="surface p-7 reveal">
                                <span className="font-mono text-xs tracking-[0.12em] text-accent">STEP 0{n}</span>
                                <h3 className="mt-3 font-display font-bold text-lg">{t(`landing.how_step_${n}`)}</h3>
                                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{t(`landing.how_step_${n}_desc`)}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ---------------- Use cases (dark band) ---------------- */}
            <section id="usecases" className="py-16 sm:py-20 text-white" style={{ background: INK }}>
                <div className="mx-auto max-w-6xl px-4 sm:px-6">
                    <span className="font-mono text-xs tracking-[0.14em] uppercase text-accent">{t("landing.uses_kicker")}</span>
                    <h2 className="mt-3 font-display text-3xl sm:text-4xl font-bold tracking-tight">
                        {t("landing.uses_title")} <span className="text-accent">{t("landing.uses_title_hl")}</span>
                    </h2>
                    <p className="mt-3 text-white/65 max-w-xl">{t("landing.uses_lead")}</p>
                    <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {[
                            ["vehicle", "🚗"],
                            ["keys", "🔑"],
                            ["luggage", "🧳"],
                            ["pets", "🐕"],
                            ["gadgets", "💻"],
                            ["school", "🎒"],
                            ["elder", "👴"],
                            ["any", "📦"],
                        ].map(([key, emoji]) => (
                            <div key={key} className="reveal rounded-2xl border border-white/10 hover:border-accent transition-colors p-5" data-testid={`usecase-${key}`}>
                                <span className="text-2xl block mb-3" aria-hidden="true">{emoji}</span>
                                <h3 className="font-display font-bold">{t(`landing.uc_${key}`)}</h3>
                                <p className="mt-1.5 text-sm text-white/60 leading-relaxed">{t(`landing.uc_${key}_d`)}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ---------------- Features ---------------- */}
            <section id="features" className="py-16 sm:py-20">
                <div className="mx-auto max-w-6xl px-4 sm:px-6">
                    <span className="font-mono text-xs tracking-[0.14em] uppercase text-accent">{t("landing.feat_kicker")}</span>
                    <h2 className="mt-3 font-display text-3xl sm:text-4xl font-bold tracking-tight">{t("landing.feat_title")}</h2>
                    <p className="mt-3 text-muted-foreground max-w-xl">{t("landing.feat_lead")}</p>
                    <div className="mt-10 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
                        {[
                            ["f1", "core"], ["f2", "core"], ["f3", "new"],
                            ["f4", "new"], ["f5", "new"], ["f6", "new"],
                            ["f7", "new"], ["f8", "new"], ["f9", "new"],
                        ].map(([key, badge]) => (
                            <div key={key} className="surface p-6 reveal">
                                <span className={`inline-block font-mono text-[10px] tracking-[0.1em] uppercase rounded-full px-3 py-1 mb-3 ${badge === "new" ? "bg-accent text-white" : "bg-primary text-primary-foreground"}`}>
                                    {t(badge === "new" ? "landing.badge_new" : "landing.badge_core")}
                                </span>
                                <h3 className="font-display font-bold">{t(`landing.${key}`)}</h3>
                                <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{t(`landing.${key}_d`)}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ---------------- Get tags (free "products") ---------------- */}
            <section id="products" className="py-16 sm:py-20 text-white" style={{ background: INK }}>
                <div className="mx-auto max-w-6xl px-4 sm:px-6">
                    <span className="font-mono text-xs tracking-[0.14em] uppercase text-accent">{t("landing.tags_kicker")}</span>
                    <h2 className="mt-3 font-display text-3xl sm:text-4xl font-bold tracking-tight">
                        {t("landing.tags_title")} <span className="text-accent">{t("landing.tags_title_hl")}</span>
                    </h2>
                    <p className="mt-3 text-white/65 max-w-xl">{t("landing.tags_lead")}</p>
                    <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
                        {["p1", "p2", "p3", "p4"].map((key) => (
                            <div
                                key={key}
                                className={`relative reveal rounded-2xl bg-white text-slate-900 p-6 flex flex-col ${key === "p1" ? "border-2 border-accent" : "border border-white/10"}`}
                                data-testid={`product-${key}`}
                            >
                                {key === "p1" && (
                                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-accent text-white font-mono text-[10px] tracking-[0.1em] px-3 py-1 rounded-full">
                                        {t("landing.most_popular")}
                                    </span>
                                )}
                                <h3 className="font-display font-bold">{t(`landing.${key}`)}</h3>
                                <p className="text-xs text-slate-500 mt-0.5">{t(`landing.${key}_for`)}</p>
                                <p className="font-display font-black text-3xl mt-3">
                                    {t("landing.price_free")}{" "}
                                    <span className="text-xs font-normal text-slate-500 font-sans">{t("landing.price_free_note")}</span>
                                </p>
                                <p className="text-sm text-slate-600 mt-3 flex-1 leading-relaxed">{t(`landing.${key}_d`)}</p>
                                <Button className="mt-5 rounded-full bg-accent hover:bg-accent/90 text-white w-full" onClick={goStart}>
                                    {t("landing.p_cta")}
                                </Button>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            <SponsorSection />

            {/* ---------------- FAQ ---------------- */}
            <section id="faq" className="py-16 sm:py-20">
                <div className="mx-auto max-w-3xl px-4 sm:px-6">
                    <span className="font-mono text-xs tracking-[0.14em] uppercase text-accent">{t("landing.faq_kicker")}</span>
                    <h2 className="mt-3 font-display text-3xl sm:text-4xl font-bold tracking-tight">{t("landing.faq_title")}</h2>
                    <div className="mt-8 space-y-3">
                        {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                            <details key={n} className="faq-item surface overflow-hidden" data-testid={`faq-${n}`}>
                                <summary className="flex items-center justify-between gap-4 cursor-pointer p-5 font-semibold text-sm sm:text-base list-none">
                                    {t(`landing.faq_q${n}`)}
                                    <span className="faq-plus font-display text-xl text-accent shrink-0" aria-hidden="true">+</span>
                                </summary>
                                <p className="px-5 pb-5 text-sm text-muted-foreground leading-relaxed">{t(`landing.faq_a${n}`)}</p>
                            </details>
                        ))}
                    </div>
                </div>
            </section>

            {/* ---------------- CTA band ---------------- */}
            <section id="contact" className="pb-16">
                <div className="mx-auto max-w-6xl px-4 sm:px-6">
                    <div className="reveal rounded-3xl px-6 py-14 sm:px-12 text-center text-white bg-gradient-to-br from-accent to-orange-700">
                        <h2 className="font-display text-3xl sm:text-4xl font-bold tracking-tight">{t("landing.band_title")}</h2>
                        <p className="mt-2 opacity-90 max-w-xl mx-auto">{t("landing.band_sub")}</p>
                        <a
                            className="inline-block mt-7 bg-white text-orange-700 font-semibold rounded-full px-7 py-3 hover:-translate-y-0.5 transition-transform"
                            href="https://wa.me/918904223100?text=Hi%20Info-Tag!%20I%20want%20my%20free%20tags."
                            target="_blank"
                            rel="noopener noreferrer"
                            data-testid="cta-whatsapp"
                        >
                            {t("landing.band_btn")}
                        </a>
                    </div>
                </div>
            </section>

            <FeedbackSection />

            {/* ---------------- Footer ---------------- */}
            <footer className="text-white/70 pt-14 pb-8" style={{ background: INK }}>
                <div className="mx-auto max-w-6xl px-4 sm:px-6">
                    <div className="grid sm:grid-cols-3 gap-10 pb-9 border-b border-white/10">
                        <div>
                            <div className="flex items-center gap-2 font-display font-black text-xl text-white">
                                <span className="w-7 h-7 rounded-lg bg-accent grid place-items-center">
                                    <Tag className="h-4 w-4 text-white" strokeWidth={2.5} />
                                </span>
                                Info-<span className="text-accent">Tag</span>
                            </div>
                            <p className="mt-3 text-sm max-w-xs">{t("landing.footer_tagline")}</p>
                        </div>
                        <div>
                            <h4 className="font-mono text-[11px] tracking-[0.14em] uppercase text-white/45 mb-3">{t("landing.footer_explore")}</h4>
                            <ul className="space-y-2 text-sm">
                                <li><a href="#how" className="hover:text-white">{t("landing.nav_how")}</a></li>
                                <li><a href="#features" className="hover:text-white">{t("landing.nav_features")}</a></li>
                                <li><a href="#products" className="hover:text-white">{t("landing.nav_tags")}</a></li>
                                <li><a href="#faq" className="hover:text-white">{t("landing.nav_faq")}</a></li>
                                <li><Link to="/privacy" className="hover:text-white" data-testid="footer-privacy">{t("legal.privacy")}</Link></li>
                                <li><Link to="/terms" className="hover:text-white" data-testid="footer-terms">{t("legal.terms")}</Link></li>
                                <li><Link to="/medical-disclaimer" className="hover:text-white" data-testid="footer-medical">{t("legal.medical_disclaimer")}</Link></li>
                            </ul>
                        </div>
                        <div>
                            <h4 className="font-mono text-[11px] tracking-[0.14em] uppercase text-white/45 mb-3">{t("landing.footer_contact_h")}</h4>
                            <ul className="space-y-2 text-sm">
                                <li className="flex items-center gap-1.5" data-testid="footer-founder">
                                    <Cloud className="h-3.5 w-3.5 text-accent shrink-0" />
                                    Founder: <span className="text-white font-semibold">Anand Lakhera</span>
                                </li>
                                <li className="flex items-center gap-1.5" data-testid="footer-cofounder">
                                    <Users className="h-3.5 w-3.5 text-accent shrink-0" />
                                    Co-Founder: <span className="text-white font-semibold">Devesh Sen</span>
                                </li>
                                <li className="flex items-center gap-1.5" data-testid="footer-phone">
                                    <Phone className="h-3.5 w-3.5 text-accent shrink-0" />
                                    <a href="tel:+918904223100" className="hover:text-white">+91 89042 23100</a>
                                </li>
                                <li className="flex items-center gap-1.5" data-testid="footer-contact">
                                    <Mail className="h-3.5 w-3.5 text-accent shrink-0" />
                                    <a href="mailto:an.31and@gmail.com" className="hover:text-white">an.31and@gmail.com</a>
                                </li>
                                <li className="flex items-center gap-1.5">
                                    <MessageCircle className="h-3.5 w-3.5 text-accent shrink-0" />
                                    <a href="https://wa.me/918904223100" target="_blank" rel="noopener noreferrer" className="hover:text-white">WhatsApp</a>
                                </li>
                                <li className="flex items-center gap-1.5" data-testid="footer-linkedin">
                                    <Linkedin className="h-3.5 w-3.5 text-accent shrink-0" />
                                    <a href="https://www.linkedin.com/in/anand-lakhera/" target="_blank" rel="noopener noreferrer" className="hover:text-white">linkedin.com/in/anand-lakhera</a>
                                </li>
                                <li className="flex items-center gap-1.5" data-testid="footer-instagram">
                                    <Instagram className="h-3.5 w-3.5 text-accent shrink-0" />
                                    <a href="https://www.instagram.com/anandlakhera8" target="_blank" rel="noopener noreferrer" className="hover:text-white">@anandlakhera8</a>
                                </li>
                            </ul>
                        </div>
                    </div>
                    <div className="pt-6 flex flex-wrap justify-between gap-2 font-mono text-[11px] text-white/40">
                        <span>© 2026 Info-Tag · MIT open source</span>
                        <span>MADE IN INDIA 🇮🇳 · PRIVACY-FIRST BY DESIGN</span>
                    </div>
                </div>
            </footer>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Live scan demo — the phone overlay from the mock                    */
/* ------------------------------------------------------------------ */
function ScanDemo({ t, onClose }) {
    const [toast, setToast] = useState("");

    useEffect(() => {
        const onKey = (e) => e.key === "Escape" && onClose();
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [onClose]);

    const options = [
        { key: "call", Icon: PhoneCall },
        { key: "wa", Icon: MessageCircle },
        { key: "em", Icon: Siren },
    ];

    return (
        <div
            className="fixed inset-0 z-[90] flex items-center justify-center p-5 bg-slate-950/70 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            aria-label={t("landing.demo_title")}
            onClick={(e) => e.target === e.currentTarget && onClose()}
            data-testid="scan-demo"
        >
            <div className="w-full max-w-sm bg-white text-slate-900 rounded-3xl overflow-hidden shadow-2xl animate-rise">
                <div className="flex items-center justify-between px-5 py-3.5 text-white" style={{ background: INK }}>
                    <b className="font-display text-sm">{t("landing.demo_title")}</b>
                    <button onClick={onClose} aria-label={t("common.cancel")} className="p-1 hover:opacity-70" data-testid="scan-demo-close">
                        <X className="h-5 w-5" />
                    </button>
                </div>
                <div className="p-6">
                    <span className="font-mono text-[10px] tracking-[0.12em] uppercase text-accent">{t("landing.demo_scanned")}</span>
                    <h3 className="font-display font-bold text-xl mt-1.5">{t("landing.demo_headline")}</h3>
                    <p className="text-sm text-slate-500 mt-1 mb-4">{t("landing.demo_sub")}</p>
                    {options.map(({ key, Icon }) => (
                        <button
                            key={key}
                            type="button"
                            onClick={() => setToast(t(`landing.demo_toast_${key}`))}
                            className="w-full flex items-center gap-3.5 text-left bg-slate-50 border border-slate-200 hover:border-accent rounded-xl px-4 py-3 mb-2.5 transition-colors"
                            data-testid={`demo-opt-${key}`}
                        >
                            <span className="w-9 h-9 rounded-lg grid place-items-center text-white shrink-0" style={{ background: INK }}>
                                <Icon className="h-4.5 w-4.5" size={18} />
                            </span>
                            <span className="text-sm font-semibold">
                                {t(`landing.demo_opt_${key}`)}
                                <small className="block font-normal text-xs text-slate-500">{t(`landing.demo_opt_${key}_sub`)}</small>
                            </span>
                        </button>
                    ))}
                    {toast && (
                        <div className="mt-2 text-white text-sm rounded-xl px-4 py-3 animate-pop-in" style={{ background: INK }} data-testid="demo-toast">
                            {toast}
                        </div>
                    )}
                    <p className="font-mono text-[10px] text-slate-400 text-center pt-3">{t("landing.demo_foot")}</p>
                </div>
            </div>
        </div>
    );
}

/* Static demo QR artwork (decorative only — real tags get real QRs) */
function DemoQr() {
    return (
        <svg viewBox="0 0 29 29" shapeRendering="crispEdges" aria-hidden="true" className="block w-full h-auto">
            <rect width="29" height="29" fill="#fff" />
            <path
                fill={INK}
                d="M0 0h7v7H0zM1 1v5h5V1zM2 2h3v3H2zM22 0h7v7h-7zM23 1v5h5V1zM24 2h3v3h-3zM0 22h7v7H0zM1 23v5h5V1zM2 24h3v3H2zM9 0h2v2H9zM13 0h1v3h-1zM16 1h2v1h-2zM19 0h1v2h-1zM9 3h1v2H9zM11 3h3v1h-3zM15 3h1v2h-1zM18 3h2v2h-2zM8 6h2v1H8zM12 6h2v2h-2zM16 6h1v1h-1zM20 6h1v2h-1zM0 9h2v1H0zM3 9h2v2H3zM6 9h1v1H6zM8 8h1v3H8zM10 9h3v1h-3zM14 8h2v2h-2zM17 9h2v1h-2zM21 9h1v2h-1zM23 8h2v1h-2zM26 9h3v1h-3zM1 12h2v2H1zM4 13h2v1H4zM7 12h2v1H7zM10 12h1v3h-1zM12 13h3v2h-3zM16 12h2v2h-2zM19 13h1v1h-1zM22 12h2v1h-2zM25 12h2v2h-2zM28 13h1v2h-1zM0 16h1v2H0zM2 16h3v1H2zM6 16h2v2H6zM9 17h2v1H9zM13 16h1v2h-1zM15 17h3v1h-3zM19 16h2v1h-2zM23 16h2v2h-2zM26 16h1v1h-1zM28 17h1v1h-1zM8 20h2v2H8zM11 20h2v1h-2zM14 20h2v2h-2zM17 20h1v3h-1zM19 21h2v1h-2zM22 20h1v2h-1zM24 21h2v2h-2zM27 20h2v2h-2zM9 23h1v2H9zM11 23h3v2h-3zM15 24h1v2h-1zM19 23h2v2h-2zM22 24h2v1h-2zM26 24h3v1h-3zM8 26h2v2H8zM12 27h2v1h-2zM15 27h3v1h-3zM20 26h1v2h-1zM23 27h2v1h-2zM26 27h2v2h-2z"
            />
        </svg>
    );
}
