"""
Company branding and display strings. Change this file to rebrand the app for a different company.
All templates and the app use these values so you only need to update one place.
"""

# Display name shown in header and page titles
COMPANY_APP_NAME = "Novelis"

# Short line under the main title (e.g. data source or product line)
COMPANY_SUBTITLE = "SAP and QAD gold data"

# Suffix for browser tab title: "COMPANY_APP_NAME | COMPANY_PAGE_TITLE_SUFFIX"
COMPANY_PAGE_TITLE_SUFFIX = "Supply Chain"

# Footer text (one line)
COMPANY_FOOTER = "Data from Unity Catalog gold tables. Comments stored in Postgres."

# Actions page subtitle (under the app name on /actions)
COMPANY_ACTIONS_SUBTITLE = "Actions by role"

# Primary brand color (hex). Novelis burgundy/dark red from brand palette.
COMPANY_PRIMARY_COLOR = "#8B0304"


def get_company():
    """Return a dict of all company/branding values for templates."""
    return {
        "name": COMPANY_APP_NAME,
        "subtitle": COMPANY_SUBTITLE,
        "page_title_suffix": COMPANY_PAGE_TITLE_SUFFIX,
        "footer": COMPANY_FOOTER,
        "actions_subtitle": COMPANY_ACTIONS_SUBTITLE,
        "primary_color": COMPANY_PRIMARY_COLOR,
    }
