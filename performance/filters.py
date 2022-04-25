from django.db.models import Count
from django_filters import rest_framework as filters
from projects.models import Project
from .models import TransactionGroup, avg_transactionevent_time


class TransactionGroupFilter(filters.FilterSet):
    start = filters.IsoDateTimeFilter(
        field_name="transactionevent__created",
        lookup_expr="gte",
        label="Transaction start date",
    )
    end = filters.IsoDateTimeFilter(
        field_name="transactionevent__created",
        lookup_expr="lte",
        label="Transaction end date",
    )
    project = filters.ModelMultipleChoiceFilter(queryset=Project.objects.all())
    query = filters.CharFilter(
        field_name="transaction",
        lookup_expr="icontains",
        label="Transaction text search",
    )

    class Meta:
        model = TransactionGroup
        fields = ["project", "start", "end"]

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        environments = self.request.query_params.getlist("environment")
        if environments:
            queryset = queryset.filter(tags__environment__has_any_keys=environments)

        # This annotation must be applied after any related transactionevent filter
        queryset = queryset.annotate(
            avg_duration=avg_transactionevent_time,
            transaction_count=Count("transactionevent"),
        )

        return queryset
