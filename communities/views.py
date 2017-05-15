from django.contrib import messages
from django.contrib.auth.mixins import(
    LoginRequiredMixin,
    PermissionRequiredMixin
)
from django.contrib.auth.models import Group, Permission
from django.core.urlresolvers import reverse, reverse_lazy
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views import generic

from braces.views import PrefetchRelatedMixin, SelectRelatedMixin


from . import models


class CreateCommunity(LoginRequiredMixin, generic.CreateView):
    fields = ("name", "description")
    model = models.Community

    def form_valid(self, form):
        resp = super().form_valid(form)
        models.CommunityMember.objects.create(
            community=self.object,
            user=self.request.user,
            role=3
        )
        return resp


class SingleCommunity(PrefetchRelatedMixin, generic.DetailView):
    model = models.Community
    prefetch_related = ("members",)


class AllCommunities(generic.ListView):
    model = models.Community


class JoinCommunity(LoginRequiredMixin, generic.RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        return reverse("communities:single",
                       kwargs={"slug": self.kwargs.get("slug")})

    def get(self, request, *args, **kwargs):
        community = get_object_or_404(models.Community,
                                      slug=self.kwargs.get("slug"))

        try:
            if community.members.count() is 0:
                models.CommunityMember.objects.create(
                    user=self.request.user,
                    community=community,
                    role=3
                )
                print("hits this")

            else:
               models.CommunityMember.objects.create(
                    user=self.request.user,
                    community=community,
                    role=1
               )
        except IntegrityError:
            messages.warning(
                self.request,
                ("You were already a member of <b>{}</b>.  "
                 "Don't be sneaky!").format(
                    community.name
                )
            )
        else:
            messages.success(
                self.request,
                "You're now a member of <b>{}</b>!".format(community.name)
            )
        return super().get(request, *args, **kwargs)


class LeaveCommunity(LoginRequiredMixin, generic.RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        return reverse("communities:single",
                       kwargs={"slug": self.kwargs.get("slug")})

    def get(self, request, *args, **kwargs):
        try:
            membership = models.CommunityMember.objects.filter(
                user=self.request.user,
                community__slug=self.kwargs.get("slug")
            ).exclude(role=3).get()

        except models.CommunityMember.DoesNotExist:
            messages.warning(
                self.request,
                "You can't leave this group."
            )
        else:
            membership.delete()
            messages.success(
                self.request,
                "You've left the group!"
            )
        return super().get(request, *args, **kwargs)


class ChangeStatus(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    generic.RedirectView
):
    permission_required = "communities.ban_member"
    
    def has_permission(self):
        return any([
            super().has_permission(),
            self.request.user.id in self.get_object().admins
        ])
    
    def get_object(self):
        return get_object_or_404(
            models.Community,
            slug=self.kwargs.get("slug")
        )
    
    def get_redirect_url(self, *args, **kwargs):
        return self.get_object().get_absolute_url()
    
    def get(self, request, *args, **kwargs):
        role = int(self.kwargs.get("status"))
        membership = get_object_or_404(
            models.CommunityMember,
            community__slug=self.kwargs.get("slug"),
            user__id=self.kwargs.get("user_id")
        )
        membership.role = role
        membership.save()
        if membership.role is 0:
            try:
                membership = models.CommunityMember.objects.filter(
                    user=self.request.user,
                    community__slug=self.kwargs.get("slug")
                ).exclude(role=3).get()
            except models.CommunityMember.DoesNotExist:
                messages.warning(
                    self.request,
                    "You can't leave this group."
                )
            else:
                membership.delete()
                messages.success(
                    self.request,
                    "You've been banned from the group!"
                )

        
        try:
            moderators = Group.objects.get(name__iexact="moderators")
        except Group.DoesNotExist:
            moderators = Group.objects.create(name="Moderators")
            moderators.permissions.add(
                # Global_Bug: What is this?
                Permissions.objects.get(codename="ban_members")
            )
        
        if role in [2, 3]:
            membership.user.groups.add(moderators)
        else:
            membership.user.groups.remove(moderators)
        
        messages.success(request, "@{} is now {}".format(
            membership.user.username,
            membership.get_role_display()
        ))
        
        return super().get(request, *args, **kwargs)


class DeleteCommunity(LoginRequiredMixin, SelectRelatedMixin, generic.DeleteView):
    model = models.Community
    select_related = ("community")
    success_url = reverse_lazy("posts:all")

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user_id=self.request.user.id)

    def get_object(self, queryset=None):
        if self.request.user.is_superuser:
            slug = self.kwargs.get(self.slug_url_kwarg, None)
            queryset = models.Community.objects.filter(slug=slug)
            try:
                obj = queryset.get()
            except models.Community.ObjectDoesNotExist:
                raise Http404(_(u"No %(verbose_name)s found matching the query") %
                              {'verbose_name': queryset.model._meta.verbose_name})
            return obj
        else:
            raise Http404(_(u"Not a mod, can't delete other's communities"))

    def delete(self, *args, **kwargs):
        if self.request.user.is_superuser:
            self.object = self.get_object()
            self.object.delete()
            return HttpResponseRedirect(self.get_success_url())

        messages.success(self.request, "Message successfully deleted")
        return super().delete(*args, **kwargs)
