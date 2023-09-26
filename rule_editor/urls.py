"""
URL configuration for rule_editor project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, reverse_lazy, re_path
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from django.conf import settings

admin.site.site_header = "Witty Works Rule Editor"
admin.site.site_title = "Rule Editor"
admin.site.index_title = "Welcome to Witty Works Rule Editor"

urlpatterns = [
    path("", RedirectView.as_view(url=reverse_lazy("admin:index"))),
    path("admin/", admin.site.urls),
    path("__debug__/", include("debug_toolbar.urls")),
]

from ajax_select import urls as ajax_select_urls

admin.autodiscover()

urlpatterns = [
    # place it at whatever base url you like
    re_path(r"^ajax_select/", include(ajax_select_urls)),
    re_path(r"^admin/", include(admin.site.urls)),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
