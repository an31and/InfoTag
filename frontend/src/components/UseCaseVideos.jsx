import { useEffect, useRef, useState } from "react";

import { useI18n } from "../lib/i18n";

// 10-second explainer clips (frontend/public/videos/). overview is portrait
// (720×1280), the other two are landscape (1280×720) — object-contain on a
// dark card handles both without cropping.
const VIDEOS = [
    { src: "/videos/overview.mp4", key: "video_overview", portrait: true },
    { src: "/videos/how-it-works.mp4", key: "video_how", portrait: false },
    { src: "/videos/use-cases.mp4", key: "video_uses", portrait: false },
];

/**
 * Swipeable strip of 10s use-case clips, shown right under the hero so it's
 * the first thing a mobile visitor sees. Native CSS scroll-snap does the
 * swiping (no library); an IntersectionObserver plays only the slide in
 * view so three videos never download/decode at once on slow connections.
 */
export function UseCaseVideos() {
    const { t } = useI18n();
    const trackRef = useRef(null);
    const [active, setActive] = useState(0);

    useEffect(() => {
        const track = trackRef.current;
        if (!track) return undefined;
        const slides = Array.from(track.querySelectorAll("[data-slide]"));
        if (!("IntersectionObserver" in window)) {
            slides.forEach((s) => s.querySelector("video")?.play().catch(() => {}));
            return undefined;
        }
        const io = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    const video = entry.target.querySelector("video");
                    if (!video) return;
                    if (entry.isIntersecting && entry.intersectionRatio > 0.55) {
                        setActive(Number(entry.target.dataset.slide));
                        video.play().catch(() => {});
                    } else {
                        video.pause();
                    }
                });
            },
            { root: null, threshold: [0.6] }
        );
        slides.forEach((s) => io.observe(s));
        return () => io.disconnect();
    }, []);

    const scrollTo = (i) => {
        const track = trackRef.current;
        const slide = track?.querySelector(`[data-slide="${i}"]`);
        slide?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    };

    return (
        <section className="py-10 sm:py-14 text-white" style={{ background: "#0E1326" }} data-testid="usecase-videos">
            <div className="mx-auto max-w-6xl px-4 sm:px-6">
                <div className="flex items-end justify-between gap-4">
                    <div>
                        <span className="font-mono text-xs tracking-[0.14em] uppercase text-accent">{t("landing.videos_kicker")}</span>
                        <h2 className="mt-2 font-display text-2xl sm:text-3xl font-bold tracking-tight">{t("landing.videos_title")}</h2>
                        <p className="mt-2 text-sm text-white/60 max-w-md">{t("landing.videos_lead")}</p>
                    </div>
                    <span className="hidden sm:block font-mono text-[11px] tracking-[0.1em] text-white/40 shrink-0 animate-pulse-soft">
                        {t("landing.videos_hint")}
                    </span>
                </div>
            </div>
            <div
                ref={trackRef}
                className="mt-6 flex gap-4 overflow-x-auto snap-x snap-mandatory scroll-smooth px-4 sm:px-6 pb-2 [-webkit-overflow-scrolling:touch] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                style={{ scrollPaddingInline: "16px" }}
            >
                {VIDEOS.map((v, i) => (
                    <figure
                        key={v.src}
                        data-slide={i}
                        className="snap-center shrink-0 w-[86%] sm:w-[360px] first:ml-auto last:mr-auto"
                        data-testid={`usecase-video-${i}`}
                    >
                        <div className="rounded-2xl overflow-hidden border border-white/10 bg-black h-[380px] sm:h-[420px] grid place-items-center">
                            <video
                                src={v.src}
                                muted
                                loop
                                playsInline
                                preload={i === 0 ? "auto" : "metadata"}
                                className={`h-full w-full ${v.portrait ? "object-cover" : "object-contain"}`}
                                aria-label={t(`landing.${v.key}`)}
                            />
                        </div>
                        <figcaption className="mt-2.5 text-center text-sm font-semibold text-white/85">
                            {t(`landing.${v.key}`)}
                        </figcaption>
                    </figure>
                ))}
            </div>
            <div className="mt-3 flex justify-center gap-2" role="tablist" aria-label={t("landing.videos_title")}>
                {VIDEOS.map((v, i) => (
                    <button
                        key={v.src}
                        role="tab"
                        aria-selected={active === i}
                        aria-label={t(`landing.${v.key}`)}
                        onClick={() => scrollTo(i)}
                        className={`h-2 rounded-full transition-all ${active === i ? "w-6 bg-accent" : "w-2 bg-white/25"}`}
                        data-testid={`usecase-video-dot-${i}`}
                    />
                ))}
            </div>
            <p className="mt-3 text-center sm:hidden font-mono text-[11px] tracking-[0.1em] text-white/40">{t("landing.videos_hint")}</p>
        </section>
    );
}
