from django.db import models
from django.contrib.auth.models import User 
from urllib.parse import urlparse, parse_qs

class Movie(models.Model):
    
     # GENRE CHOICES
    GENRE_CHOICES = [
        ('ACTION', 'Action'),
        ('COMEDY', 'Comedy'),
        ('DRAMA', 'Drama'),
        ('THRILLER', 'Thriller'),
        ('ROMANCE', 'Romance'),
        ('HORROR', 'Horror'),
        ('SCIENCE FICTION', 'Science Fiction'),
        ('ANIMATION', 'Animation'),
        ('ADVENTURE', 'Adventure'),
        ('FANTASY', 'Fantasy'),
    ]
    
    # LANGUAGE CHOICES
    LANGUAGE_CHOICES = [
        ('hindi', 'Hindi'),
        ('english', 'English'),
        ('tamil', 'Tamil'),
        ('telegu', 'Telugu'),
        ('malayalam', 'Malayalam'),
        ('kanada', 'Kannada'),
        ('bengali', 'Bengali'),
        ('marathi', 'Marathi'),
    ]
    name= models.CharField(max_length=255)
    # image= models.ImageField(upload_to="movies/")
    image = models.URLField(blank=True, null=True, help_text="Paste a direct image URL")

    rating = models.DecimalField(max_digits=3,decimal_places=1)
    cast= models.TextField()
    description= models.TextField(blank=True,null=True) # optional
    genre = models.CharField(max_length=100, choices=GENRE_CHOICES,default="Action")  # or choose a default
    language = models.CharField(max_length=50,choices=LANGUAGE_CHOICES, default="English")
    
    trailer_url = models.URLField(
        blank=True, 
        null=True, 
        help_text="Paste YouTube watch or share link"
    )

    def get_trailer_id(self):
        """Extracts video ID from various YouTube URL formats."""
        if not self.trailer_url:
            return None
        
        url = urlparse(self.trailer_url)
        # Standard watch URL: ://youtube.com
        if "youtube.com" in url.netloc:
            query_params = parse_qs(url.query)
            if "v" in query_params:
                return query_params["v"][0]
            # Handle /shorts/VIDEO_ID
            if "/shorts/" in url.path:
                return url.path.split("/shorts/")[-1]
        
        # Short youtu.be URL
        elif "youtu.be" in url.netloc:
            return url.path.strip("/")
        
        return None

    def get_embed_url(self):
        """Returns sanitized, privacy-enhanced embed URL."""
        video_id = self.get_trailer_id()
        if video_id:
            # ?rel=0 prevents showing related videos from other channels
            # youtube-nocookie.com enhances privacy
            return f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0" # Added /embed/ here
        return None




    
    def __str__(self):
        return self.name

class Theater(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name
    

class Showtime(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="showtimes")
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name="showtimes")
    time=models.DateTimeField()
    price= models.DecimalField(max_digits=6, decimal_places=2,default=199) 

    def __str__(self):
        return f"{self.movie.name} at {self.theater.name} - {self.time}"


class Seat(models.Model):
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="seats")
    seat_number = models.CharField(max_length=10)
    is_booked = models.BooleanField(default=False)
   

    def __str__(self):
        return f"{self.seat_number} - {self.showtime}"
class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE)
    showtime = models.ForeignKey(Showtime,on_delete=models.CASCADE)
    booked_at = models.DateTimeField(auto_now_add=True)
   
    payment_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    status = models.CharField(max_length=20, choices=[('confirmed','Confirmed'),('cancelled','Cancelled')], default='confirmed')


    class Meta:
        indexes = [
            models.Index(fields=['booked_at']),   # revenue queries
            models.Index(fields=['status']),       # cancellation queries
            models.Index(fields=['showtime']),     # movie/theater queries
        ]

    def __str__(self):
        return f"{self.user.username} booked {self.seat.seat_number}"


   


from django.utils import timezone
from datetime import timedelta


class SeatReservation(models.Model):
    seat       = models.OneToOneField(Seat, on_delete=models.CASCADE, related_name='reservation')
    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    showtime   = models.ForeignKey(Showtime, on_delete=models.CASCADE)
    reserved_until = models.DateTimeField()
    status     = models.CharField(max_length=20, choices=[
        ('reserved', 'Reserved'),
        ('confirmed', 'Confirmed'),
        ('expired', 'Expired'),
    ], default='reserved')


    def is_active(self):
        return self.status == 'reserved' and self.reserved_until > timezone.now()
