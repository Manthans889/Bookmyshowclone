from django.contrib import admin
from .models import Movie, Theater, Showtime, Seat, Booking, SeatReservation
from django.db import models
from django.forms import DateTimeInput
from django.contrib.admin.widgets import AdminSplitDateTime

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['name', 'rating', 'genre', 'language']
    search_fields = ['name', 'cast']

@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name', 'location']
    search_fields = ['name']


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['seat_number', 'showtime', 'is_booked']
    list_filter = ['showtime', 'is_booked']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user', 'seat', 'showtime', 'booked_at','status']
    list_filter = ['booked_at']


@admin.register(Showtime)
class ShowtimeAdmin(admin.ModelAdmin):
    list_display = ['movie', 'theater', 'time']
    list_filter = ['movie', 'theater']
    ordering = ['time']


@admin.register(SeatReservation)
class SeatReservationAdmin(admin.ModelAdmin):
    list_display = ['user', 'seat', 'showtime', 'status', 'reserved_until']
    list_filter = ['status', 'showtime']
    search_fields = ['user__username', 'seat__seat_number']
    readonly_fields = ['reserved_until']

