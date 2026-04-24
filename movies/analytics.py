from django.db.models import Sum, Count, Avg, F
from django.db.models.functions import TruncDate, TruncHour, TruncWeek, TruncMonth
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from .models import Booking, Showtime, Movie, Theater, Seat


def get_revenue(period='daily'):
    cache_key = f'analytics_revenue_{period}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    now = timezone.now()

    if period == 'daily':
        start = now - timedelta(days=1)
    elif period == 'weekly':
        start = now - timedelta(weeks=1)
    else:  
        start = now - timedelta(days=30)

    result = Booking.objects.filter(
        status='confirmed',
        booked_at__gte=start
    ).aggregate(total=Sum('amount'))['total'] or 0

    cache.set(cache_key, result, timeout=900)  # 15 min 
    return result


def get_popular_movies(limit=5):
    cached = cache.get('analytics_popular_movies')
    if cached:
        return cached

    result = list(
        Booking.objects.filter(status='confirmed')
        .values('showtime__movie__name')
        .annotate(total_bookings=Count('id'))
        .order_by('-total_bookings')[:limit]
    )

    cache.set('analytics_popular_movies', result, timeout=900)
    return result


def get_busiest_theaters(limit=5):
    cached = cache.get('analytics_busiest_theaters')
    if cached:
        return cached

    # Total seats per theater vs booked seats 
    result = list(
        Booking.objects.filter(status='confirmed')
        .values('showtime__theater__name')
        .annotate(total_bookings=Count('id'))
        .order_by('-total_bookings')[:limit]
    )

    cache.set('analytics_busiest_theaters', result, timeout=900)
    return result


def get_peak_hours():
    cached = cache.get('analytics_peak_hours')
    if cached:
        return cached

    result = list(
        Booking.objects.filter(status='confirmed')
        .annotate(hour=TruncHour('booked_at'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('-count')[:8]
    )

   
    formatted = [
        {
            'hour': f"{item['hour'].strftime('%I %p') if item['hour'] else 'N/A'}",
            'count': item['count']
        }
        for item in result
    ]

    cache.set('analytics_peak_hours', formatted, timeout=900)
    return formatted


def get_cancellation_rate():
    cached = cache.get('analytics_cancellation_rate')
    if cached:
        return cached

    total = Booking.objects.count()
    if total == 0:
        return 0

    cancelled = Booking.objects.filter(status='cancelled').count()
    rate = round((cancelled / total) * 100, 2)

    cache.set('analytics_cancellation_rate', rate, timeout=900)
    return rate


def get_revenue_chart():

    cached = cache.get('analytics_revenue_chart')
    if cached:
        return cached

    now = timezone.now()
    start = now - timedelta(days=7)

    result = list(
        Booking.objects.filter(
            status='confirmed',
            booked_at__gte=start
        )
        .annotate(day=TruncDate('booked_at'))
        .values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )

    formatted = [
        {
            'day': item['day'].strftime('%d %b') if item['day'] else '',
            'total': float(item['total'] or 0)
        }
        for item in result
    ]

    cache.set('analytics_revenue_chart', formatted, timeout=900)
    return formatted