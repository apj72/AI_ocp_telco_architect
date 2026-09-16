"""docshots scenarios for TPS user guide screenshots."""

config = {
    "base_url": "http://127.0.0.1:8771",
    "output_dir": "docs/screenshots",
    "viewport": [1280, 800],
    "default_wait": "body",
}

# ponytail: partner slug hardcoded — change if your demo partner differs
PARTNER = "nokia"

# ponytail: every partner page has a large terminal at top; scroll past it
SCROLL_TABS = {"js": "document.querySelector('.tab-panel:not([hidden]) .panel-head').scrollIntoView()"}

scenarios = [
    {
        "name": "dashboard",
        "caption": "Dashboard with Partner Cards",
        "url": "/",
        "wait": ".partner-card",
    },
    {
        "name": "jira-config",
        "caption": "Jira Configuration Modal",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"click": ".config-btn"},
            {"wait": "#config-menu:not([hidden])"},
            {"js": "document.querySelector('[onclick*=\"jira-modal\"]')?.click()"},
            {"wait": ".modal:not([hidden])"},
            {"scroll": "#jira-modal"},
        ],
    },
    {
        "name": "partner-overview",
        "caption": "Partner Page Overview",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [SCROLL_TABS],
    },
    {
        "name": "ecops-tickets",
        "caption": "ECOPS Tickets Tab",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"click": "[data-tab='tickets']"},
            {"wait": "#tab-tickets:not([hidden])"},
            SCROLL_TABS,
        ],
    },
    {
        "name": "releases",
        "caption": "Releases Tab with OCP Versions",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"click": "[data-tab='releases']"},
            {"wait": "#tab-releases:not([hidden])"},
            SCROLL_TABS,
        ],
    },
    {
        "name": "knowledge",
        "caption": "Knowledge Tab",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"click": "[data-tab='knowledge']"},
            {"wait": "#tab-knowledge:not([hidden])"},
            SCROLL_TABS,
        ],
    },
    {
        "name": "doc-sources",
        "caption": "Document Sources Tab",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"js": "document.querySelector('.architect-hero').style.display='none'"},
            {"click": "[data-tab='doc-sources']"},
            {"wait": "#tab-doc-sources:not([hidden])"},
        ],
    },
    {
        "name": "review-queue",
        "caption": "Review Queue",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"click": "[data-tab='doc-sources']"},
            {"wait": "#tab-doc-sources:not([hidden])"},
            {"js": "showQueue('backlog')"},
            {"wait": "#queue-container:not([hidden])"},
            {"scroll": "#queue-container"},
        ],
    },
    {
        "name": "topic-expanded",
        "caption": "Expanded Topic",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"click": "[data-tab='topics']"},
            {"wait": "#tab-topics:not([hidden])"},
            SCROLL_TABS,
            {"click": ".topic-card:first-child"},
            {"wait": 800},
            {"js": "document.querySelector('.topic-detail, .topic-expanded, .topic-card:first-child').scrollIntoView()"},
        ],
    },
    {
        "name": "skill-generation",
        "caption": "Skill Generation Result",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "actions": [
            {"click": ".config-btn"},
            {"wait": "#config-menu:not([hidden])"},
            {"js": "document.querySelector('[onclick*=\"doGenerate\"]')?.click()"},
            {"wait": 3000},
        ],
    },
    {
        "name": "architect-terminal",
        "caption": "Architect Terminal",
        "url": f"/partner/{PARTNER}",
        "wait": ".tabs",
        "viewport": [1280, 900],
    },
]
