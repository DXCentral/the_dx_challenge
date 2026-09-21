from __future__ import annotations

import streamlit as st


_FULLSCREEN_CONTROL = st.components.v2.component(
    "dx_map_workspace_fullscreen",
    html="""
<button id="fullscreen-toggle" type="button">Open full screen</button>
""",
    css="""
button {
  width: 100%;
  min-height: 2.45rem;
  border: 1px solid var(--st-border-color, rgba(128, 128, 128, 0.45));
  border-radius: var(--st-button-radius, 0.5rem);
  background: var(--st-secondary-background-color);
  color: var(--st-text-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
button:hover {
  border-color: var(--st-primary-color);
  color: var(--st-primary-color);
}
button:focus-visible {
  outline: 2px solid var(--st-primary-color);
  outline-offset: 2px;
}
""",
    js="""
export default function (component) {
  const { data, parentElement } = component
  const button = parentElement.querySelector("#fullscreen-toggle")
  const componentHost = parentElement.host ?? parentElement
  const targetSelector = `.${CSS.escape(data.targetClass)}`
  const target = componentHost.closest(targetSelector)
  if (!button || !target) return

  const fullscreenRoot = document.body
  const activeClass = "dx-map-workspace-fullscreen-active"
  const styleId = "dx-map-workspace-fullscreen-style"

  const installFullscreenStyles = () => {
    let style = document.getElementById(styleId)
    if (!style) {
      style = document.createElement("style")
      style.id = styleId
      document.head.appendChild(style)
    }
    style.textContent = `
html.${activeClass},
html.${activeClass} body {
  background: var(--st-background-color, #0e1117) !important;
  height: 100% !important;
  margin: 0 !important;
  overflow: hidden !important;
  width: 100% !important;
}
html.${activeClass} ${targetSelector} {
  background: var(--st-background-color, #0e1117) !important;
  border: 0 !important;
  box-sizing: border-box !important;
  height: 100vh !important;
  inset: 0 !important;
  margin: 0 !important;
  max-width: none !important;
  overflow: auto !important;
  padding: 1rem !important;
  position: fixed !important;
  width: 100vw !important;
  z-index: 2147483000 !important;
}
html.${activeClass} [data-baseweb="popover"],
html.${activeClass} [data-baseweb="menu"],
html.${activeClass} [role="listbox"] {
  z-index: 2147483600 !important;
}
`
    document.documentElement.classList.add(activeClass)
  }

  const removeFullscreenStyles = () => {
    document.documentElement.classList.remove(activeClass)
    document.getElementById(styleId)?.remove()
  }

  const update = () => {
    const active = document.fullscreenElement === fullscreenRoot
    button.textContent = active ? "Exit full screen" : "Open full screen"
    button.setAttribute("aria-pressed", active ? "true" : "false")
    if (active) {
      installFullscreenStyles()
    } else {
      removeFullscreenStyles()
    }
  }

  button.onclick = async () => {
    try {
      if (document.fullscreenElement === fullscreenRoot) {
        await document.exitFullscreen()
      } else {
        installFullscreenStyles()
        await fullscreenRoot.requestFullscreen()
      }
    } catch (error) {
      removeFullscreenStyles()
      button.textContent = "Full screen unavailable"
      button.title = String(error)
    }
  }

  document.addEventListener("fullscreenchange", update)
  update()

  return () => {
    button.onclick = null
    document.removeEventListener("fullscreenchange", update)
  }
}
""",
)


def render_fullscreen_control(*, target_key: str, key: str) -> None:
    """Render a browser-fullscreen toggle for a keyed Streamlit container."""

    _FULLSCREEN_CONTROL(
        key=key,
        data={"targetClass": f"st-key-{target_key}"},
        height=42,
        width="stretch",
    )
