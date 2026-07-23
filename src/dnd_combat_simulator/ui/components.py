"""Focused Streamlit UI helpers."""

from __future__ import annotations

from contextlib import nullcontext

from dnd_combat_simulator import APP_TITLE

SHARE_TOOLBAR_HTML = """
<div class="share-toolbar" role="group" aria-label="Share configuration">
    <button
        class="share-button"
        type="button"
        title="Copy share link"
        aria-label="Copy share link"
    >
        <svg
            class="share-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
            focusable="false"
        >
            <path
                d="M6 18c.8-4.9 4-7.3 9.1-7.3h1.2"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
            />
            <path
                d="M13.8 6.2 18.6 11l-4.8 4.8"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
            />
        </svg>
        <span class="share-label">Share Configuration</span>
    </button>
    <a class="share-link" href="" target="_blank" rel="noopener noreferrer" hidden></a>
    <input class="share-fallback" type="text" readonly hidden />
    <span class="share-status" aria-live="polite"></span>
</div>
"""

SHARE_TOOLBAR_CSS = """
.share-toolbar {
    min-height: 42px;
    height: 42px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    width: max-content;
    max-width: 100%;
    color: var(--st-text-color);
    background: var(--st-background-color);
    font-family: var(--st-font);
    overflow: hidden;
}

.share-button {
    height: 42px;
    min-width: 42px;
    box-sizing: border-box;
    padding: 0 0.9rem;
    border-radius: 999px; /* legacy circle control used border-radius: 50% */
    border: 1px solid var(--st-border-color);
    background: var(--st-secondary-background-color);
    color: var(--st-text-color);
    font-family: var(--st-font);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    line-height: 1;
    cursor: pointer;
}

.share-button:hover:not(:disabled) {
    border-color: var(--st-primary-color);
    color: var(--st-primary-color);
}

.share-button:focus-visible {
    outline: 2px solid var(--st-primary-color);
    outline-offset: 2px;
}

.share-button:disabled {
    cursor: not-allowed;
    opacity: 0.6;
}

.share-icon {
    width: 20px;
    height: 20px;
    flex: 0 0 auto;
}

.share-link {
    min-width: 0;
    max-width: min(42rem, 55vw);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--st-primary-color);
    font-family: var(--st-font);
    align-self: center;
}

.share-link[hidden] {
    display: none;
}

.share-status {
    min-width: 12rem;
    color: var(--st-text-color);
    font-family: var(--st-font);
    opacity: 0;
    transition: opacity 180ms ease;
    text-overflow: ellipsis;
}

.share-status.visible {
    opacity: 1;
}

.share-fallback {
    width: min(24rem, 45vw);
    min-width: 12rem;
    font-family: var(--st-font);
}

.share-fallback[hidden] {
    display: none;
}
"""

SHARE_TOOLBAR_JS = """
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const button = parentElement.querySelector('.share-button');
    const label = parentElement.querySelector('.share-label');
    const status = parentElement.querySelector('.share-status');
    const link = parentElement.querySelector('.share-link');
    const fallbackInput = parentElement.querySelector('.share-fallback');
    let latestData = {};
    let statusTimer = null;
    let mode = 'create';

    function setStatus(message, temporary = false) {
        status.textContent = message || '';
        status.classList.toggle('visible', Boolean(message));
        if (statusTimer !== null) {
            window.clearTimeout(statusTimer);
            statusTimer = null;
        }
        if (temporary) {
            statusTimer = window.setTimeout(() => {
                setStatus('');
                if (mode === 'copy') {
                    label.textContent = 'Copy';
                }
            }, 1500);
        }
    }

    function revealFallback(message) {
        fallbackInput.value = latestData.url || '';
        fallbackInput.hidden = false;
        fallbackInput.focus();
        fallbackInput.select();
        label.textContent = 'Copy';
        setStatus(message);
    }

    function showCopied() {
        fallbackInput.hidden = true;
        label.textContent = 'Copied';
        setStatus('', true);
    }

    function render(nextData) {
        latestData = nextData || {};
        button.disabled = Boolean(latestData.disabled || latestData.creating);
        fallbackInput.hidden = true;
        fallbackInput.value = latestData.url || '';
        button.title = latestData.url ? 'Copy share link' : 'Share configuration';
        button.setAttribute('aria-label', button.title);
        link.hidden = !latestData.url || Boolean(latestData.creating);
        link.href = latestData.url || '';
        link.textContent = latestData.url || '';
        link.title = latestData.url || '';

        if (latestData.disabled) {
            label.textContent = latestData.creating
                ? 'Creating...'
                : 'Share Configuration';
            setStatus(latestData.message || '');
            mode = 'disabled';
        } else if (latestData.creating) {
            label.textContent = 'Creating...';
            setStatus('');
            mode = 'creating';
        } else if (latestData.url) {
            label.textContent = 'Copy';
            setStatus('');
            mode = 'copy';
        } else {
            label.textContent = 'Share Configuration';
            setStatus(latestData.message || '');
            mode = 'create';
        }
    }

    async function copyUrl() {
        const targetUrl = latestData.url || '';
        if (!targetUrl) {
            return false;
        }
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(targetUrl);
                showCopied();
                return true;
            } catch (error) {
                // Fall through to the selectable-input fallback below.
            }
        }

        revealFallback('Copy blocked. Press Ctrl+C.');
        try {
            if (document.execCommand("copy")) {
                showCopied();
                return true;
            }
        } catch (fallbackError) {
            // Keep the selectable fallback visible.
        }
        revealFallback('Copy blocked. Press Ctrl+C.');
        return false;
    }

    render(data || {});

    button.onclick = async () => {
        if (mode === 'create') {
            label.textContent = 'Creating...';
            button.disabled = true;
            setTriggerValue('create_share', `${Date.now()}-${Math.random()}`);
        } else if (mode === 'copy') {
            await copyUrl();
        }
    };

    return () => {
        if (statusTimer !== null) {
            window.clearTimeout(statusTimer);
        }
        button.onclick = null;
    };
}
"""

ATTACK_CARD_CSS = """
<style>
:root {
    --attack-card-background: color-mix(
        in srgb,
        var(--st-secondary-background-color) 82%,
        var(--st-primary-color) 18%
    );
    --attack-card-border: color-mix(
        in srgb,
        var(--st-border-color) 82%,
        var(--st-primary-color) 18%
    );
    --attack-card-nested-background: color-mix(
        in srgb,
        var(--st-background-color) 88%,
        var(--st-secondary-background-color) 12%
    );
}

@media (prefers-color-scheme: dark) {
    :root {
        --attack-card-background: color-mix(
            in srgb,
            var(--st-secondary-background-color) 90%,
            var(--st-primary-color) 10%
        );
        --attack-card-border: color-mix(
            in srgb,
            var(--st-border-color) 76%,
            var(--st-primary-color) 24%
        );
        --attack-card-nested-background: color-mix(
            in srgb,
            var(--st-background-color) 78%,
            var(--st-secondary-background-color) 22%
        );
    }
}

[class*="st-key-first-attack-"][class*="-card"] [data-testid="stVerticalBlockBorderWrapper"],
[class*="st-key-second-attack-"][class*="-card"] [data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--attack-card-background) !important;
    border-color: var(--attack-card-border) !important;
    border-radius: 14px;
    box-shadow: 0 0.35rem 1rem rgba(0, 0, 0, 0.12);
}

[class*="st-key-first-attack-"][class*="-card"] [data-testid="stVerticalBlockBorderWrapper"] > div,
[class*="st-key-second-attack-"][class*="-card"] [data-testid="stVerticalBlockBorderWrapper"] > div {
    background: var(--attack-card-background) !important;
    border-radius: inherit;
    padding: clamp(0.85rem, 1.4vw, 1.35rem);
}

[class*="st-key-first-attack-"][class*="-card"] [data-testid="stExpander"] details,
[class*="st-key-second-attack-"][class*="-card"] [data-testid="stExpander"] details {
    background: var(--attack-card-nested-background);
    border-color: var(--st-border-color);
}

.attack-card-marker {
    display: none;
}
</style>
"""

ATTACK_TOOLBAR_CSS = """
<style>
[class*="st-key-first-attack-"][class*="-toolbar"],
[class*="st-key-second-attack-"][class*="-toolbar"] {
    display: inline-flex;
    width: max-content;
    max-width: 100%;
    min-height: 0;
    padding: 0;
    margin: 0;
    line-height: 1;
}

:is(
    [class*="st-key-first-attack-"],
    [class*="st-key-second-attack-"]
)[class*="-toolbar"] [data-testid="stVerticalBlockBorderWrapper"] {
    width: max-content;
    max-width: 100%;
    min-height: 0;
    padding: 0 !important;
    margin: 0;
    border-radius: 8px;
    line-height: 1;
}

:is(
    [class*="st-key-first-attack-"],
    [class*="st-key-second-attack-"]
)[class*="-toolbar"] [data-testid="stVerticalBlockBorderWrapper"] > div {
    width: max-content;
    max-width: 100%;
    min-height: 0;
    padding: 2px 4px !important;
    margin: 0;
    line-height: 1;
}

[class*="st-key-first-attack-"][class*="-toolbar"] [data-testid="stVerticalBlock"],
[class*="st-key-second-attack-"][class*="-toolbar"] [data-testid="stVerticalBlock"] {
    display: inline-flex;
    width: max-content;
    max-width: 100%;
    min-height: 0;
    row-gap: 0 !important;
    gap: 0 !important;
    padding: 0 !important;
    margin: 0;
    line-height: 1;
}

[class*="st-key-first-attack-"][class*="-toolbar"] [data-testid="stHorizontalBlock"],
[class*="st-key-second-attack-"][class*="-toolbar"] [data-testid="stHorizontalBlock"] {
    display: inline-flex;
    width: max-content;
    max-width: 100%;
    min-height: 0;
    align-items: center;
    gap: 2px !important;
    padding: 0 !important;
    margin: 0;
    line-height: 1;
}

[class*="st-key-first-attack-"][class*="-toolbar"] [data-testid="stElementContainer"],
[class*="st-key-second-attack-"][class*="-toolbar"] [data-testid="stElementContainer"] {
    width: 32px;
    min-width: 32px;
    max-width: 32px;
    height: 32px;
    min-height: 32px;
    max-height: 32px;
    padding: 0 !important;
    margin: 0;
    line-height: 1;
}

[class*="st-key-first-attack-"][class*="-toolbar"] button[kind="tertiary"],
[class*="st-key-second-attack-"][class*="-toolbar"] button[kind="tertiary"] {
    width: 32px;
    min-width: 32px;
    max-width: 32px;
    height: 32px;
    min-height: 32px;
    max-height: 32px;
    padding: 0 !important;
    margin: 0;
    line-height: 1;
}

/* Keep native Streamlit focus-visible outlines, disabled styling,
   hover behavior, and tooltips intact. */
</style>
"""

CONFIGURATION_TOOLBAR_CSS = """
<style>
.st-key-configuration-toolbar {
    display: inline-flex;
    width: max-content;
    max-width: 100%;
    align-items: center;
    gap: 8px;
}

.st-key-configuration-toolbar [data-testid="stHorizontalBlock"] {
    display: inline-flex;
    width: max-content;
    max-width: 100%;
    align-items: center;
    gap: 8px;
}

.st-key-configuration-toolbar [data-testid="stVerticalBlock"],
.st-key-configuration-toolbar [data-testid="stElementContainer"] {
    width: max-content;
    max-width: 100%;
}

.st-key-configuration-toolbar [data-testid="stPopover"] {
    width: max-content;
}

.st-key-configuration-toolbar [data-testid="stPopover"] button,
.st-key-configuration-toolbar button[kind="secondary"] {
    height: 42px;
    min-height: 42px;
    min-width: 42px;
    box-sizing: border-box;
    padding: 0 0.9rem;
    border: 1px solid var(--st-border-color);
    border-radius: 999px;
    background: var(--st-secondary-background-color);
    color: var(--st-text-color);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
    margin: 0;
}

.st-key-configuration-toolbar [data-testid="stPopover"] button {
    width: 42px;
    padding: 0;
}

.st-key-configuration-toolbar [data-testid="stPopover"] button:hover:not(:disabled),
.st-key-configuration-toolbar button[kind="secondary"]:hover:not(:disabled) {
    border-color: var(--st-primary-color);
    color: var(--st-primary-color);
}

.st-key-configuration-toolbar [data-testid="stPopover"] button:focus-visible,
.st-key-configuration-toolbar button[kind="secondary"]:focus-visible {
    outline: 2px solid var(--st-primary-color);
    outline-offset: 2px;
}
</style>
"""

_SHARE_TOOLBAR_COMPONENT = None


def _get_share_toolbar_component():
    """Register and return the v2 share toolbar component."""
    global _SHARE_TOOLBAR_COMPONENT
    if _SHARE_TOOLBAR_COMPONENT is None:
        import streamlit as st

        components = getattr(st, "components", None)
        if components is None or not hasattr(components, "v2"):
            return lambda **kwargs: None
        _SHARE_TOOLBAR_COMPONENT = st.components.v2.component(
            "share_toolbar",
            html=SHARE_TOOLBAR_HTML,
            css=SHARE_TOOLBAR_CSS,
            js=SHARE_TOOLBAR_JS,
        )
    return _SHARE_TOOLBAR_COMPONENT


PAGE_WIDTH_CSS = """
<style>
    .stApp .block-container {
        width: 90vw;
        max-width: 90vw;
        margin-left: auto;
        margin-right: auto;
        padding-left: clamp(1rem, 2vw, 2.5rem);
        padding-right: clamp(1rem, 2vw, 2.5rem);
        box-sizing: border-box;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px;
        border-color: rgba(128, 128, 128, 0.28);
        box-shadow: 0 0.25rem 0.8rem rgba(0, 0, 0, 0.06);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: clamp(0.75rem, 1.3vw, 1.25rem);
    }

    @media (max-width: 640px) {
        .stApp .block-container {
            width: 100%;
            max-width: 100%;
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
</style>
"""


def configure_page() -> None:
    """Configure Streamlit to use a wide, centered application layout."""
    import streamlit as st

    st.set_page_config(page_title=APP_TITLE, page_icon="🎲", layout="wide")
    st.markdown(PAGE_WIDTH_CSS, unsafe_allow_html=True)
    st.markdown(ATTACK_CARD_CSS, unsafe_allow_html=True)
    st.markdown(ATTACK_TOOLBAR_CSS, unsafe_allow_html=True)


def _render_section_container(key: str | None = None):
    """Return a bordered Streamlit container when available."""
    import streamlit as st

    container = getattr(st, "container", None)
    if container is None:
        return nullcontext()
    try:
        return container(border=True, key=key)
    except TypeError:
        try:
            return container(border=True)
        except TypeError:
            return container()


def _mount_unified_share_component(
    data: dict[str, object], on_create_share_change
) -> object:
    share_toolbar = _get_share_toolbar_component()
    return share_toolbar(
        data=data,
        key="unified-share-configuration",
        on_create_share_change=on_create_share_change,
    )
