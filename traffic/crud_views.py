from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import MonitoringPointForm, TrafficSnapshotForm
from .models import MonitoringPoint, TrafficSnapshot


class TrafficPermissionRequiredMixin(PermissionRequiredMixin):
    """
    Exige la permission spécifiée :
    - Si l'utilisateur n'est pas connecté : redirection vers le login (302).
    - Si l'utilisateur est connecté mais sans permission : refus 403 (PermissionDenied).
    """
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(self.get_permission_denied_message())



# ==============================================================================
# 1. MonitoringPoint CRUD
# ==============================================================================
class PointListView(LoginRequiredMixin, ListView):
    model = MonitoringPoint
    template_name = 'traffic/crud/point_list.html'
    context_object_name = 'points'
    paginate_by = 20

    def get_queryset(self):
        qs = MonitoringPoint.objects.all().order_by('name')
        active_filter = self.request.GET.get('active')
        if active_filter in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        elif active_filter in ('0', 'false', 'False'):
            qs = qs.filter(is_active=False)
        return qs


class PointDetailView(LoginRequiredMixin, DetailView):
    model = MonitoringPoint
    template_name = 'traffic/crud/point_detail.html'
    context_object_name = 'point'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['recent_snapshots'] = self.object.snapshots.order_by('-timestamp')[:10]
        ctx['total_snapshots'] = self.object.snapshots.count()
        return ctx


class PointCreateView(TrafficPermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = MonitoringPoint
    form_class = MonitoringPointForm
    template_name = 'traffic/crud/form.html'
    permission_required = 'traffic.add_monitoringpoint'
    success_message = _("Le point de surveillance « %(name)s » a été créé avec succès.")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = _("Nouveau point de surveillance")
        ctx['back_url'] = reverse_lazy('traffic:point_list')
        return ctx

    def get_success_url(self):
        return reverse_lazy('traffic:point_detail', kwargs={'pk': self.object.pk})


class PointUpdateView(TrafficPermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = MonitoringPoint
    form_class = MonitoringPointForm
    template_name = 'traffic/crud/form.html'
    permission_required = 'traffic.change_monitoringpoint'
    success_message = _("Le point de surveillance « %(name)s » a été modifié avec succès.")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = _("Modifier le point « %(name)s »") % {'name': self.object.name}
        ctx['back_url'] = reverse_lazy('traffic:point_detail', kwargs={'pk': self.object.pk})
        return ctx

    def get_success_url(self):
        return reverse_lazy('traffic:point_detail', kwargs={'pk': self.object.pk})


class PointDeleteView(TrafficPermissionRequiredMixin, DeleteView):
    model = MonitoringPoint
    template_name = 'traffic/crud/confirm_delete.html'
    permission_required = 'traffic.delete_monitoringpoint'
    success_url = reverse_lazy('traffic:point_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['snapshot_count'] = self.object.snapshots.count()
        ctx['cancel_url'] = reverse_lazy('traffic:point_detail', kwargs={'pk': self.object.pk})
        return ctx

    def form_valid(self, form):
        point_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, _("Le point de surveillance « %(name)s » a été supprimé.") % {'name': point_name})
        return response


# ==============================================================================
# 2. TrafficSnapshot CRUD
# ==============================================================================
class SnapshotListView(LoginRequiredMixin, ListView):
    model = TrafficSnapshot
    template_name = 'traffic/crud/snapshot_list.html'
    context_object_name = 'snapshots'
    paginate_by = 50

    def get_queryset(self):
        qs = TrafficSnapshot.objects.select_related('point').order_by('-timestamp')
        point_id = self.request.GET.get('point')
        if point_id:
            try:
                qs = qs.filter(point_id=int(point_id))
            except (ValueError, TypeError):
                pass
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['points'] = MonitoringPoint.objects.all().order_by('name')
        ctx['selected_point'] = self.request.GET.get('point', '')
        return ctx


class SnapshotDetailView(LoginRequiredMixin, DetailView):
    model = TrafficSnapshot
    template_name = 'traffic/crud/snapshot_detail.html'
    context_object_name = 'snapshot'


class SnapshotCreateView(TrafficPermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = TrafficSnapshot
    form_class = TrafficSnapshotForm
    template_name = 'traffic/crud/form.html'
    permission_required = 'traffic.add_trafficsnapshot'
    success_message = _("La mesure de trafic a été enregistrée avec succès.")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = _("Nouvelle mesure de trafic")
        ctx['back_url'] = reverse_lazy('traffic:snapshot_list')
        return ctx

    def get_success_url(self):
        return reverse_lazy('traffic:snapshot_detail', kwargs={'pk': self.object.pk})


class SnapshotUpdateView(TrafficPermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = TrafficSnapshot
    form_class = TrafficSnapshotForm
    template_name = 'traffic/crud/form.html'
    permission_required = 'traffic.change_trafficsnapshot'
    success_message = _("La mesure de trafic a été mise à jour avec succès.")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = _("Modifier la mesure de trafic #%(id)s") % {'id': self.object.pk}
        ctx['back_url'] = reverse_lazy('traffic:snapshot_detail', kwargs={'pk': self.object.pk})
        return ctx

    def get_success_url(self):
        return reverse_lazy('traffic:snapshot_detail', kwargs={'pk': self.object.pk})


class SnapshotDeleteView(TrafficPermissionRequiredMixin, DeleteView):
    model = TrafficSnapshot
    template_name = 'traffic/crud/confirm_delete.html'
    permission_required = 'traffic.delete_trafficsnapshot'
    success_url = reverse_lazy('traffic:snapshot_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cancel_url'] = reverse_lazy('traffic:snapshot_detail', kwargs={'pk': self.object.pk})
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("La mesure de trafic a été supprimée."))
        return response
