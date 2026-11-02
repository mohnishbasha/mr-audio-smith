const DARK =
  "--as-bg:#101512;--as-surface:#18201B;--as-surface-2:#222C25;--as-border:#2E3A32;--as-text:#E8EFE9;--as-text-muted:#A3B2A7;--as-accent:#7DBF92;--as-accent-hover:#93CEA6;--as-accent-soft:#23362A;--as-glyph:#101512;";

export const STYLES = `
:host{--as-bg:#FFFFFF;--as-surface:#F6F8F5;--as-surface-2:#ECF1EA;--as-border:#D7E0D3;--as-text:#1E2A22;--as-text-muted:#5B6B60;--as-text-inverse:#FFFFFF;--as-accent:#4E8A62;--as-accent-hover:#3F7552;--as-accent-soft:#DCEBDF;--as-sun:#F4B740;--as-sky:#5AA9E6;--as-error:#B3261E;--as-focus:#1F6FEB;--as-glyph:var(--as-text-inverse);display:block;font:inherit;color:var(--as-text)}
@media (prefers-color-scheme:dark){:host(:not([theme="light"])){${DARK}}}
:host([theme="dark"]){${DARK}}
:host([hidden]){display:none}
*{box-sizing:border-box}
[hidden]{display:none!important}
.card{--_scale:1;--_pad:12px;display:grid;grid-template-columns:auto 1fr auto;grid-template-areas:"play label tools" "play wave wave";align-items:center;column-gap:12px;row-gap:4px;padding:var(--_pad);background:var(--as-surface);border:1px solid var(--as-border);border-radius:12px;font-family:inherit;line-height:1.4}
.card[data-size="kid"]{--_scale:1.25;--_pad:20px;grid-template-columns:auto 1fr;grid-template-areas:"play label" "wave wave" "tools tools";row-gap:12px}
.card[data-size="kid"] .label{font-size:22px}
.card[data-size="kid"] .time{font-size:18px}
.card[data-size="kid"] .tools{justify-content:flex-end}
@media (max-width:480px){.card{grid-template-columns:auto 1fr;grid-template-areas:"play label" "wave wave" "tools tools"}.tools{justify-content:flex-end}}
.play{grid-area:play;width:44px;height:44px;border-radius:50%;border:0;padding:0;background:var(--as-accent);color:var(--as-glyph);display:grid;place-items:center;cursor:pointer;transition:background-color 120ms ease-out}
.card[data-size="kid"] .play{width:64px;height:64px;box-shadow:0 0 0 3px var(--as-sun)}
.play:hover{background:var(--as-accent-hover)}
.play:disabled{opacity:.5;cursor:default}
.play svg{width:24px;height:24px;fill:currentColor}
.card[data-size="kid"] .play svg{width:32px;height:32px}
.card[data-state="loading"][data-slow] .play{outline:3px dotted var(--as-sky);outline-offset:2px}
.label{grid-area:label;font-size:16px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.tools{grid-area:tools;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.time{font-size:14px;color:var(--as-text-muted);font-variant-numeric:tabular-nums}
.cc,.lang button,.dl,.retry{min-width:44px;min-height:44px;padding:0 12px;border:1px solid var(--as-border);border-radius:8px;background:var(--as-bg);color:var(--as-text);font:inherit;font-size:14px;font-weight:600;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;text-decoration:none;transition:background-color 120ms ease-out,color 120ms ease-out}
.cc:hover,.lang button:hover,.dl:hover,.retry:hover{background:var(--as-surface-2)}
.cc[aria-pressed="true"],.lang button[aria-checked="true"]{background:var(--as-accent-soft);border-color:var(--as-accent)}
.retry:disabled{opacity:.5;cursor:default}
.lang{display:inline-flex;gap:8px}
.wave{grid-area:wave;display:flex;align-items:center;gap:2px;min-height:44px;cursor:pointer;border-radius:8px}
.card[data-size="kid"] .wave{min-height:52px}
.bar{flex:1;min-width:2px;border-radius:2px;background:var(--as-surface-2);transform-origin:center}
.bar.on{background:var(--as-accent)}
.card[data-size="kid"] .bar.on{background:var(--as-sky)}
.wave[data-playing] .bar.head{background:var(--as-accent);animation:breathe 1.6s ease-in-out infinite alternate}
@keyframes breathe{from{transform:scale(1)}to{transform:scale(1.15)}}
.flat{flex:1;height:8px;border-radius:4px;background:var(--as-surface-2);overflow:hidden}
.fill{display:block;height:100%;width:0;background:var(--as-accent)}
.err{grid-column:1/-1;grid-row:1;display:flex;flex-wrap:wrap;align-items:center;gap:12px;color:var(--as-text)}
.err svg{width:24px;height:24px;fill:var(--as-error);flex:none}
.msg{flex:1;min-width:0;font-size:16px}
.card[data-failed] .play,.card[data-failed] .label,.card[data-failed] .wave,.card[data-failed] .tools{display:none}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.status{grid-column:2/-1;font-size:14px;color:var(--as-text-muted)}
.cap{margin:8px 0 0;padding:0 4px;font-size:16px;line-height:1.6;min-height:1.6em;color:var(--as-text)}
.cap[data-size="kid"]{font-size:22px}
button:focus-visible,a:focus-visible,.wave:focus-visible{outline:2px solid var(--as-focus);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}.bar.head{animation:none!important}}
`;
