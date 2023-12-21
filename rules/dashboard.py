"""
This file was generated with the customdashboard management command and
contains the class for the main dashboard.

To activate your index dashboard add the following to your settings.py::
    GRAPPELLI_INDEX_DASHBOARD = 'rule-editor.dashboard.CustomIndexDashboard'
"""

from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from grappelli.dashboard import modules, Dashboard
from grappelli.dashboard.utils import get_admin_site_name


class CustomIndexDashboard(Dashboard):
    """
    Custom index dashboard for www.
    """

    def init_with_context(self, context):
        self.children.append(
            modules.AppList(
                _("Applications"),
                column=1,
                collapsible=False,
                exclude=("django.contrib.*",),
            ),
        )
        self.children.append(
            modules.AppList(
                _("Administration"),
                column=1,
                collapsible=False,
                models=("django.contrib.*",),
            ),
        )

        # append a recent actions module
        self.children.append(
            modules.RecentActions(
                _("Recent actions"),
                limit=10,
                collapsible=False,
                column=2,
            ),
        )
