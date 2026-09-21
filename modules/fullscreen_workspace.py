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
  const target = componentHost.closest(`.${data.targetClass}`)
  if (!button || !target) return

  const previous = {
    background: target.style.background,
    boxSizing: target.style.boxSizing,
    height: target.style.height,
    overflow: target.style.overflow,
    padding: target.style.padding,
    width: target.style.width,
  }

  const update = () => {
    const active = document.fullscreenElement === target
    button.textContent = active ? "Exit full screen" : "Open full screen"
    button.setAttribute("aria-pressed", active ? "true" : "false")
    if (active) {
      target.style.background = "var(--st-background-color, #0e1117)"
      target.style.boxSizing = "border-box"
      target.style.height = "100vh"
      target.style.overflow = "auto"
      target.style.padding = "1rem"
      target.style.width = "100vw"
    } else {
      Object.assign(target.style, previous)
    }
  }

  button.onclick = async () => {
    try {
      if (document.fullscreenElement === target) {
        await document.exitFullscreen()
      } else {
        await target.requestFullscreen()
      }
    } catch (error) {
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
