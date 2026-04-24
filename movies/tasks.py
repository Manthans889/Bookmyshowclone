import logging
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_booking_confirmation(self, booking_data: dict):
    """
    booking_data keys:
      user_email, user_name, movie_name, theater_name,
      showtime, seat_number, payment_id, amount
    """
    try:
        subject = f"Booking Confirmed — {booking_data['movie_name']}"

        # Render HTML template
        html_body = render_to_string(
            'movies/emails/booking_confirmation.html',
            {'booking': booking_data}
        )
        # Plain text fallback
        text_body = (
            f"Hi {booking_data['user_name']},\n\n"
            f"Your booking is confirmed!\n"
            f"Movie: {booking_data['movie_name']}\n"
            f"Theater: {booking_data['theater_name']}\n"
            f"Show: {booking_data['showtime']}\n"
            f"Seat: {booking_data['seat_number']}\n"
            f"Amount paid: ₹{booking_data['amount']}\n"
            f"Payment ID: {booking_data['payment_id']}\n"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking_data['user_email']],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)

        logger.info("Confirmation email sent to %s for payment %s",
                    booking_data['user_email'], booking_data['payment_id'])

    except Exception as exc:
        logger.error("Email failed for payment %s: %s",
                     booking_data.get('payment_id'), str(exc))
        raise self.retry(exc=exc)  # retries up to 3x, 60s apart
    
    
from celery import shared_task
from django.utils import timezone

@shared_task
def release_expired_reservations():
    from .models import SeatReservation
    expired = SeatReservation.objects.filter(
        status='reserved',
        reserved_until__lt=timezone.now()
    )
    expired.update(status='expired')