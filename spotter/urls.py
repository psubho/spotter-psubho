from django.urls import path

from routes.views import health, plan_route


urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/route/", plan_route, name="plan_route"),
]
