// -----------------------------------------------------------------------------
// Landing-page use-case video reel — EDIT THIS FILE to add or remove videos.
//
// Two kinds of entries are supported:
//
//   1. Self-hosted MP4 (recommended for short 10s loops — instant autoplay,
//      no ads, works offline):
//         { src: "/videos/my-clip.mp4", title: "My caption", portrait: false }
//      Drop the file in  frontend/public/videos/  first. Keep clips small
//      (≤3 MB, H.264/AAC). portrait: true = 9:16 video fills the card.
//
//   2. YouTube (good for longer videos — YouTube pays the bandwidth):
//         { youtubeId: "dQw4w9WgXcQ", title: "My caption" }
//      Only the thumbnail loads up front; the player appears on tap, so it
//      stays light even on slow connections.
//
// Captions: use `key` for the built-in translated captions (defined in
// src/lib/locales/*.js under landing.*), or `title` for a plain string that
// shows the same in every language. If both are set, `key` wins.
// -----------------------------------------------------------------------------

export const VIDEOS = [
    { src: "/videos/overview.mp4", key: "video_overview", portrait: true },
    { src: "/videos/how-it-works.mp4", key: "video_how", portrait: false },
    { src: "/videos/use-cases.mp4", key: "video_uses", portrait: false },
];
