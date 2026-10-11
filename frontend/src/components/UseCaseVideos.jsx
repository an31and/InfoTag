import { useEffect, useRef, useState } from "react";
import { Play, Volume2, VolumeX } from "lucide-react";

import { VIDEOS } from "../constants/videos";
import { useI18n } from "../lib/i18n";

/**
 * Swipeable strip of short use-case clips, shown right under the hero so it's
 * the first thing a mobile visitor sees. Native CSS scroll-snap does the
 * swiping (no library). The reel plays like a playlist: exactly one clip
 * plays at a time — on a laptop, where every slide is on screen at once, the
 * clips still run one by one — and when a clip ends the next one starts and
 * scrolls into view. Swiping or tapping a dot jumps the playlist there.
 * Nothing plays while the reel is off screen.
 *
 * The playing clip tries to start *with audio*; browsers that block unmuted
 * autoplay fall back to muted playback (the speaker button then turns sound
 * on with one tap). The speaker button also lets a visitor silence the reel
 * entirely; that choice sticks for later clips. YouTube entries
 * render as a thumbnail that swaps to the real player on tap. The list of
 * videos lives in src/constants/videos.js.
 */
export function UseCaseVideos() {
    const { t } = useI18n();
    const trackRef = useRef(null);
    const [active, setActive] = useState(0);
    const [audioOn, setAudioOn] = useState(true); // sound follows the on-screen slide until muted
    const audioOnRef = useRef(true);
    audioOnRef.current = audioOn;

    const caption = (v) => (v.key ? t(`landing.${v.key}`) : v.title || "");

    // Play a clip with sound, falling back to muted if the browser blocks
    // unmuted autoplay.
    const playWithSound = (video) => {
        const wantSound = audioOnRef.current;
        video.muted = !wantSound;
        video.play().catch(() => {
            if (wantSound) {
                video.muted = true;
                video.play().catch(() => {});
            }
        });
    };

    // Is the reel on screen at all? Nothing plays while it's scrolled away.
    const [inView, setInView] = useState(false);
    useEffect(() => {
        const track = trackRef.current;
        if (!track) return undefined;
        if (!("IntersectionObserver" in window)) {
            setInView(true);
            return undefined;
        }
        const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.5 });
        io.observe(track);
        return () => io.disconnect();
    }, []);

    // Exactly one clip plays: the active one. Every other clip is paused,
    // muted and rewound so it starts fresh when its turn comes.
    useEffect(() => {
        const track = trackRef.current;
        if (!track) return;
        track.querySelectorAll("[data-slide]").forEach((slide) => {
            const video = slide.querySelector("video");
            if (!video) return;
            if (inView && Number(slide.dataset.slide) === active) {
                playWithSound(video);
            } else {
                video.pause();
                video.muted = true;
                if (Number(slide.dataset.slide) !== active) video.currentTime = 0;
            }
        });
    }, [active, inView]);

    // Center a slide inside the reel without moving the page vertically.
    const scrollTo = (i) => {
        const track = trackRef.current;
        const slide = track?.querySelector(`[data-slide="${i}"]`);
        if (!slide) return;
        const t = track.getBoundingClientRect();
        const r = slide.getBoundingClientRect();
        track.scrollTo({ left: track.scrollLeft + (r.left + r.width / 2) - (t.left + t.width / 2), behavior: "smooth" });
    };

    const userScroll = useRef(false);
    const goTo = (i) => {
        userScroll.current = false;
        setActive(i);
        scrollTo(i);
    };

    // When a clip finishes, the next one takes over (wrapping to the first).
    const onEnded = (i) => goTo((i + 1) % VIDEOS.length);

    // A manual swipe (mobile) makes the slide nearest the center active once
    // scrolling settles. Only scrolls the visitor started count, so the
    // auto-advance scroll above can't re-pick a slide.
    useEffect(() => {
        const track = trackRef.current;
        if (!track) return undefined;
        let timer;
        const markUser = () => {
            userScroll.current = true;
        };
        const onScroll = () => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                if (!userScroll.current) return;
                userScroll.current = false;
                const t = track.getBoundingClientRect();
                const center = t.left + t.width / 2;
                let best = 0;
                let bestDist = Infinity;
                track.querySelectorAll("[data-slide]").forEach((slide) => {
                    const r = slide.getBoundingClientRect();
                    const dist = Math.abs(r.left + r.width / 2 - center);
                    if (dist < bestDist) {
                        bestDist = dist;
                        best = Number(slide.dataset.slide);
                    }
                });
                setActive(best);
            }, 150);
        };
        const userEvents = ["touchstart", "wheel", "pointerdown", "keydown"];
        userEvents.forEach((e) => track.addEventListener(e, markUser, { passive: true }));
        track.addEventListener("scroll", onScroll, { passive: true });
        return () => {
            clearTimeout(timer);
            userEvents.forEach((e) => track.removeEventListener(e, markUser));
            track.removeEventListener("scroll", onScroll);
        };
    }, []);

    const toggleSound = () => {
        const next = !audioOn;
        setAudioOn(next);
        audioOnRef.current = next;
        // Apply immediately to the slide currently on screen.
        const track = trackRef.current;
        const video = track?.querySelector(`[data-slide="${active}"] video`);
        if (video) {
            video.muted = !next;
            if (next) video.play().catch(() => {});
        }
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
                        key={v.src || v.youtubeId}
                        data-slide={i}
                        className="snap-center shrink-0 w-[86%] sm:w-[360px] first:ml-auto last:mr-auto"
                        data-testid={`usecase-video-${i}`}
                    >
                        <div className="relative rounded-2xl overflow-hidden border border-white/10 bg-black h-[380px] sm:h-[420px] grid place-items-center">
                            {v.youtubeId ? (
                                <LiteYouTube id={v.youtubeId} label={caption(v)} />
                            ) : (
                                <>
                                    <video
                                        src={v.src}
                                        muted
                                        playsInline
                                        onEnded={() => onEnded(i)}
                                        preload={i === 0 ? "auto" : "metadata"}
                                        className={`h-full w-full ${v.portrait ? "object-cover" : "object-contain"}`}
                                        aria-label={caption(v)}
                                    />
                                    <button
                                        type="button"
                                        onClick={toggleSound}
                                        aria-label={audioOn ? "Mute" : "Unmute"}
                                        className="absolute bottom-3 right-3 w-10 h-10 rounded-full grid place-items-center bg-black/60 backdrop-blur border border-white/25 text-white active:scale-95 transition-transform"
                                        data-testid={`usecase-video-sound-${i}`}
                                    >
                                        {audioOn ? <Volume2 className="h-5 w-5" /> : <VolumeX className="h-5 w-5" />}
                                    </button>
                                </>
                            )}
                        </div>
                        <figcaption className="mt-2.5 text-center text-sm font-semibold text-white/85">{caption(v)}</figcaption>
                    </figure>
                ))}
            </div>
            <div className="mt-3 flex justify-center gap-2" role="tablist" aria-label={t("landing.videos_title")}>
                {VIDEOS.map((v, i) => (
                    <button
                        key={v.src || v.youtubeId}
                        role="tab"
                        aria-selected={active === i}
                        aria-label={caption(v)}
                        onClick={() => goTo(i)}
                        className={`h-2 rounded-full transition-all ${active === i ? "w-6 bg-accent" : "w-2 bg-white/25"}`}
                        data-testid={`usecase-video-dot-${i}`}
                    />
                ))}
            </div>
            <p className="mt-3 text-center sm:hidden font-mono text-[11px] tracking-[0.1em] text-white/40">{t("landing.videos_hint")}</p>
        </section>
    );
}

/**
 * Click-to-load YouTube embed: shows only the thumbnail (one small image)
 * until tapped, then swaps in the real player with sound. Keeps the landing
 * page light — no YouTube JS loads unless the visitor asks for it.
 */
function LiteYouTube({ id, label }) {
    const [playing, setPlaying] = useState(false);

    if (playing) {
        return (
            <iframe
                src={`https://www.youtube-nocookie.com/embed/${id}?autoplay=1&playsinline=1&rel=0`}
                title={label}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="h-full w-full border-0"
            />
        );
    }
    return (
        <button
            type="button"
            onClick={() => setPlaying(true)}
            aria-label={`Play: ${label}`}
            className="relative h-full w-full group"
            data-testid={`youtube-thumb-${id}`}
        >
            <img
                src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`}
                alt={label}
                loading="lazy"
                className="h-full w-full object-cover"
            />
            <span className="absolute inset-0 grid place-items-center bg-black/25 group-hover:bg-black/10 transition-colors">
                <span className="w-14 h-14 rounded-full grid place-items-center bg-accent text-white shadow-lg shadow-black/40">
                    <Play className="h-6 w-6 translate-x-0.5" fill="currentColor" />
                </span>
            </span>
        </button>
    );
}
