from __future__ import annotations


THEMES: dict[str, dict[str, str]] = {
    "Midnight blue": {"background": "#0B111A", "surface": "#121C29", "text": "#F4F8FC", "muted": "#A9B8C8", "primary": "#59A8FF", "border": "#29405B"},
    "Deep ocean": {"background": "#06151A", "surface": "#0C252C", "text": "#F1FCFD", "muted": "#A7C9CD", "primary": "#39C6D4", "border": "#24505A"},
    "Aurora": {"background": "#10101B", "surface": "#1A1A2B", "text": "#F8F7FF", "muted": "#BFBAD6", "primary": "#A88BFF", "border": "#403B62"},
    "Ember": {"background": "#17110E", "surface": "#261B15", "text": "#FFF8F2", "muted": "#D6BFAE", "primary": "#F29B5B", "border": "#5E4030"},
    "Daylight blue": {"background": "#F8FAFC", "surface": "#EAF0F7", "text": "#111827", "muted": "#526173", "primary": "#146CC8", "border": "#C7D2E0"},
    "High contrast": {"background": "#000000", "surface": "#111111", "text": "#FFFFFF", "muted": "#F2F2F2", "primary": "#00E5FF", "border": "#FFFFFF"},
}


def theme_css(name: str, large_text: bool = False, reduce_motion: bool = False) -> str:
    palette = THEMES.get(name, THEMES["Midnight blue"])
    base_size = "18px" if large_text else "15px"
    motion = "*, *::before, *::after {animation-duration: 0.01ms !important; transition-duration: 0.01ms !important;}" if reduce_motion else ""
    return f"""
    <style>
    :root {{
      --dx-background: {palette['background']};
      --dx-surface: {palette['surface']};
      --dx-text: {palette['text']};
      --dx-muted: {palette['muted']};
      --dx-primary: {palette['primary']};
      --dx-border: {palette['border']};
    }}
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
      background-color: var(--dx-background) !important;
      color: var(--dx-text) !important;
      font-size: {base_size};
    }}
    [data-testid="stSidebar"], [data-testid="stSidebarContent"],
    [data-testid="stPopoverBody"], [data-testid="stDialog"] > div {{
      background-color: var(--dx-surface) !important;
      color: var(--dx-text) !important;
    }}
    [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
    label, p, h1, h2, h3, h4, h5, h6 {{ color: var(--dx-text) !important; }}
    [data-testid="stCaptionContainer"] {{ color: var(--dx-muted) !important; }}
    [data-testid="stVerticalBlockBorderWrapper"] {{ border-color: var(--dx-border) !important; }}
    button:focus-visible, input:focus-visible, [role="button"]:focus-visible {{
      outline: 3px solid var(--dx-primary) !important;
      outline-offset: 2px !important;
    }}
    a {{ color: var(--dx-primary) !important; }}
    {motion}
    </style>
    """
