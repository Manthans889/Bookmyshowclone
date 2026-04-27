from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from .models import Movie, Theater, Seat, Booking, Showtime, SeatReservation
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q
from datetime import date, timedelta
from django.utils import timezone

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.models import User
from .tasks import send_booking_confirmation

import json
import hmac
import hashlib
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.conf import settings
from .razorpay_client import client 
from datetime import datetime


from .analytics import (
    get_revenue, get_popular_movies, get_busiest_theaters,
    get_peak_hours, get_cancellation_rate, get_revenue_chart
)
def movie_list(request):
    movies = Movie.objects.all()
    
  
    search_query = request.GET.get('search', '').strip()
    genre_filter = request.GET.get('genre', '').strip()
    language_filter = request.GET.get('language', '').strip()
    
    
    if search_query:
        movies = movies.filter(
            Q(name__icontains=search_query) |
            Q(cast__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if genre_filter:
        movies = movies.filter(genre=genre_filter)
    
    if language_filter:
        movies = movies.filter(language=language_filter)
    
    context = {
        'movies': movies,
        'genres': Movie.GENRE_CHOICES,
        'languages': Movie.LANGUAGE_CHOICES,
        'search_query': search_query,
        'selected_genre': genre_filter,
        'selected_language': language_filter,
    }
    
    return render(request, 'movies/movie_list.html', context)




def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)

    today = date.today()

    week_dates = [today + timedelta(days=i) for i in range(7)]

   
    selected_date = request.GET.get("date")
    if selected_date:
        selected_date = date.fromisoformat(selected_date)
    else:
        selected_date = today

   
    showtimes = Showtime.objects.filter(
        movie=movie,
        time__date=selected_date
    ).select_related('theater')
    



    return render(
        request,
        'movies/theater_list.html',
        {
            'movie': movie,
            'showtimes': showtimes,
            'week_dates': week_dates,
            'selected_date': selected_date,
        }
    )
def details(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)

    return render(
        request,
        'movies/details.html',
        {'movie': movie}
    )
    
# okay if my verification failed  this will be useful for  fallback mechanism  : - delete this view the verify payment is working well with create_order
@login_required(login_url='/login/')
def book_seats(request, showtime_id):
  
    showtime = get_object_or_404(Showtime, id=showtime_id)
    seats    = Seat.objects.filter(showtime=showtime)

    now = timezone.now()
    reserved_seat_ids = SeatReservation.objects.filter(
        showtime=showtime,
        status='reserved',
        reserved_until__gt=now
    ).exclude(user=request.user).values_list('seat_id', flat=True)

    if request.method == 'POST':
        selected_seats    = request.POST.getlist('seats')
        error_seats       = []
        successfully_booked = []
        total_amount      = 0

        if not selected_seats:
            messages.error(request, "No seat selected")
            return render(request, "movies/seat_selection.html", {
                'showtime':          showtime,
                'seats':             seats,
                'reserved_seat_ids': list(reserved_seat_ids),
            })

        for seat_id in selected_seats:
            try:
                with transaction.atomic():
                    seat = Seat.objects.select_for_update().get(
                        id=seat_id, showtime=showtime
                    )
                    if seat.is_booked:
                        error_seats.append(seat.seat_number)
                        continue

                    Booking.objects.create(
                        user=request.user,
                        seat=seat,
                        showtime=showtime,
                        amount=showtime.price
                    )
                    seat.is_booked = True
                    seat.save()
                    successfully_booked.append(seat.seat_number)
                    total_amount += showtime.price

            except Seat.DoesNotExist:
                error_seats.append(f"Seat {seat_id}")
            except IntegrityError:
                error_seats.append(f"Seat {seat_id}")

        if successfully_booked:
            messages.success(
                request,
                f"Booked seats: {', '.join(successfully_booked)} | Total: ₹{total_amount}"
            )
            booking_data = {
                'user_email':   request.user.email,
                'user_name':    request.user.get_full_name() or request.user.username,
                'movie_name':   showtime.movie.name,
                'theater_name': showtime.theater.name,
                'showtime':     showtime.time.strftime('%d %b %Y, %I:%M %p'),
                'seat_number':  ', '.join(successfully_booked),
                'amount':       str(total_amount),
                'payment_id':   None,
            }
            send_booking_confirmation.delay(booking_data) #celery needs paid  tier to launch email  so back to normal 

        if error_seats:
            messages.error(request, f"Already booked seats: {', '.join(error_seats)}")

    return render(request, "movies/seat_selection.html", {
        'showtime':          showtime,
        'seats':             seats,
        'reserved_seat_ids': list(reserved_seat_ids),
    })


def details(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)
    return render(request, 'movies/details.html', {'movie': movie})


# trickery why I am getting 400 : solved 
@login_required(login_url='/login/')
def create_order(request, showtime_id):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    data = json.loads(request.body)
    selected_seats = data.get('seats', [])

    if not selected_seats:
        return JsonResponse({'error': 'No seats selected'}, status=400)

    showtime = get_object_or_404(Showtime, id=showtime_id)
    locked = []
    unavailable = []

    for seat_id in selected_seats:
        try:
            with transaction.atomic():
                seat = Seat.objects.select_for_update().get(
                    id=seat_id, showtime=showtime
                )

                if seat.is_booked:
                    unavailable.append(seat.seat_number)
                    continue

                # Someone else has an active reservation
                someone_else = SeatReservation.objects.filter(
                    seat=seat,
                    status='reserved',
                    reserved_until__gt=timezone.now()
                ).exclude(user=request.user).first()

                if someone_else:
                    unavailable.append(seat.seat_number)
                    continue

                # Lock it for 2 minutes
                SeatReservation.objects.update_or_create(
                    seat=seat,
                    user=request.user,
                    defaults={
                        'showtime':       showtime,
                        'reserved_until': timezone.now() + timedelta(minutes=2),
                        'status':         'reserved',
                    }
                )
                locked.append(seat_id)

        except Seat.DoesNotExist:
            unavailable.append(f"Seat {seat_id}")

    if unavailable:
        # Roll back 
        SeatReservation.objects.filter(
            seat_id__in=locked,
            user=request.user,
            status='reserved'
        ).update(status='expired')
        return JsonResponse({
            'error': f"Seats no longer available: {', '.join(str(s) for s in unavailable)}"
        }, status=409)

  
    total_amount = int(showtime.price * len(selected_seats) * 100)  # paise

    order = client.order.create({
        'amount':          total_amount,
        'currency':        'INR',
        'payment_capture': 1,
        'notes': {
            'showtime_id': showtime_id,
            'user_id':     request.user.id,
            'seats':       ','.join(selected_seats),
        }
    })

    request.session['pending_seats']    = selected_seats
    request.session['pending_showtime'] = showtime_id

    return JsonResponse({
        'order_id': order['id'],
        'amount':   total_amount,
        'currency': 'INR',
        'key_id':   settings.RAZORPAY_KEY_ID,
    })



@login_required(login_url='/login/')
def verify_payment(request):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    data = json.loads(request.body)

    razorpay_order_id   = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature  = data.get('razorpay_signature')

  
    msg = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, razorpay_signature):
        return JsonResponse({'error': 'Invalid payment signature'}, status=400)

    selected_seats = request.session.get('pending_seats', [])
    showtime_id    = request.session.get('pending_showtime')
    showtime       = get_object_or_404(Showtime, id=showtime_id)
    successfully_booked = []

    for seat_id in selected_seats:
        try:
            with transaction.atomic():
                seat = Seat.objects.select_for_update().get(
                    id=seat_id, showtime=showtime
                )

                
                reservation = SeatReservation.objects.select_for_update().filter(
                    seat=seat,
                    user=request.user,
                    status='reserved',
                    reserved_until__gt=timezone.now()
                ).first()

                if not reservation:
                 
                    continue

            
                if Booking.objects.filter(payment_id=razorpay_payment_id).exists():
                    continue

                Booking.objects.create(
                    user=request.user,
                    seat=seat,
                    showtime=showtime,
                    amount=showtime.price,
                    payment_id=razorpay_payment_id,
                    status='confirmed',
                )
                seat.is_booked = True
                seat.save()

                reservation.status = 'confirmed'
                reservation.save()

                successfully_booked.append(seat.seat_number)

        except (Seat.DoesNotExist, IntegrityError):
            continue

    # Clear session : - checkout this pay,ent confirmed in razorpay but not in admin panel  ? : solved no related (in future check it out too)
    request.session.pop('pending_seats', None)
    request.session.pop('pending_showtime', None)

    if successfully_booked:
        booking_data = {
            'user_email':   request.user.email,
            'user_name':    request.user.get_full_name() or request.user.username,
            'movie_name':   showtime.movie.name,
            'theater_name': showtime.theater.name,
            'showtime':     showtime.time.strftime('%d %b %Y, %I:%M %p'),
            'seat_number':  ', '.join(successfully_booked),
            'amount':       str(showtime.price * len(successfully_booked)),
            'payment_id':   razorpay_payment_id,
        }
        send_booking_confirmation.delay(booking_data)

    return JsonResponse({'status': 'confirmed', 'seats': successfully_booked})


# its shooting 1 per 200 sec :  60 sec  (dont change it in celery.py) the maths will fail 
@login_required(login_url='/login/')
def release_seats(request):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    selected_seats = request.session.get('pending_seats', [])

    SeatReservation.objects.filter(
        seat_id__in=selected_seats,
        user=request.user,
        status='reserved'
    ).update(status='expired')

    request.session.pop('pending_seats', None)
    request.session.pop('pending_showtime', None)

    return JsonResponse({'status': 'released'})


# useless : see this request again
@csrf_exempt
def razorpay_webhook(request):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    import logging
    logger = logging.getLogger(__name__)

    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    received_sig   = request.headers.get('X-Razorpay-Signature', '')
    payload        = request.body  

    expected_sig = hmac.new(
        webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, received_sig):
        return JsonResponse({'error': 'Invalid webhook signature'}, status=400)

    event      = json.loads(payload)
    event_type = event.get('event')

    if event_type == 'payment.captured':
        payment_id = event['payload']['payment']['entity']['id']
        if Booking.objects.filter(payment_id=payment_id).exists():
            return JsonResponse({'status': 'already processed'})
        logger.info("Webhook confirmed payment: %s", payment_id)

    elif event_type == 'payment.failed':
        payment_id = event['payload']['payment']['entity']['id']
        logger.warning("Payment failed: %s", payment_id)

    return JsonResponse({'status': 'ok'})



@csrf_exempt
def payment_success(request):
    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_order_id   = request.POST.get('razorpay_order_id')
    razorpay_signature  = request.POST.get('razorpay_signature')

    if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
        return redirect('/bookings/')

    msg = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, razorpay_signature):
        return redirect('/bookings/')

    order       = client.order.fetch(razorpay_order_id)
    notes       = order.get('notes', {})
    showtime_id = notes.get('showtime_id')
    seat_ids    = notes.get('seats', '').split(',')
    user_id     = notes.get('user_id')

    showtime = get_object_or_404(Showtime, id=showtime_id)
    user     = get_object_or_404(User, id=user_id)
    successfully_booked = []

    for seat_id in seat_ids:
        if not seat_id:
            continue
        try:
            with transaction.atomic():
                seat = Seat.objects.select_for_update().get(
                    id=seat_id, showtime=showtime
                )

                if Booking.objects.filter(payment_id=razorpay_payment_id).exists():
                    continue

                reservation = SeatReservation.objects.select_for_update().filter(
                    seat=seat,
                    user=user,
                    status='reserved',
                ).first()

                Booking.objects.create(
                    user=user,
                    seat=seat,
                    showtime=showtime,
                    amount=showtime.price,
                    payment_id=razorpay_payment_id,
                    status='confirmed',
                )
                seat.is_booked = True
                seat.save()

                if reservation:
                    reservation.status = 'confirmed'
                    reservation.save()

                successfully_booked.append(seat.seat_number)

        except Seat.DoesNotExist:
            continue
        except IntegrityError:
            continue

    request.session.pop('pending_seats', None)
    request.session.pop('pending_showtime', None)

    if successfully_booked:
        booking_data = {
            'user_email':   user.email,
            'user_name':    user.get_full_name() or user.username,
            'movie_name':   showtime.movie.name,
            'theater_name': showtime.theater.name,
            'showtime':     showtime.time.strftime('%d %b %Y, %I:%M %p'),
            'seat_number':  ', '.join(successfully_booked),
            'amount':       str(showtime.price * len(successfully_booked)),
            'payment_id':   razorpay_payment_id,
        }
        send_booking_confirmation.delay(booking_data)

    return redirect('/')




# REMOVED LOGIN REQUIRED FOR WEIRD ERROR : ADD AGAIN 
def admin_dashboard(request):
    
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect('/login/')

    context = {
        'revenue_daily':   get_revenue('daily'),
        'revenue_weekly':  get_revenue('weekly'),
        'revenue_monthly': get_revenue('monthly'),
        'popular_movies':  get_popular_movies(),
        'busiest_theaters': get_busiest_theaters(),
        'peak_hours':      get_peak_hours(),
        'cancellation_rate': get_cancellation_rate(),
        'revenue_chart':   get_revenue_chart(),
        'total_bookings':  Booking.objects.filter(status='confirmed').count(),
    }
    return render(request, 'movies/admin_dashboard.html', context)
