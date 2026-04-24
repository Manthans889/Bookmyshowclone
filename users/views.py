from datetime import date
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from .forms import UserRegisterForm, UserUpdateForm,EmailForm
from django.shortcuts import render,redirect
from django.contrib.auth import login,authenticate
from django.contrib.auth.decorators import login_required
from movies.models import Movie , Booking
from django.db.models import Q
from django.views.generic import ListView,FormView
from django.utils.timezone import now

import random
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.contrib import messages
from time import time
def home(request):
    movies= Movie.objects.all()
    
    return render(request,'home.html',{'movies':movies})

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False   # 🔴 KEY LINE
            user.save()

            otp = random.randint(100000, 999999)

            request.session['signup_otp'] = otp
            request.session['signup_user_id'] = user.id
            request.session['otp_created_at'] = time()     # ⏱ timestamp
            request.session['otp_attempts'] = 0             # 🔁 attempt counter

            send_mail(
                subject="Verify your BookMyShow account",
                message=f"Your OTP is {otp}",
                from_email="noreply@bookmyshowclone.com",
                recipient_list=[user.email],
            )

            return redirect('verify-otp')
    else:
        form = UserRegisterForm()

    return render(request, 'users/register.html', {'form': form})




def verify_otp(request):
    if request.method == 'POST':
        entered_otp = request.POST.get('otp')

        session_otp = request.session.get('signup_otp')
        user_id = request.session.get('signup_user_id')
        otp_created_at = request.session.get('otp_created_at')
        attempts = request.session.get('otp_attempts', 0)

        # ❌ Missing session data
        if not session_otp or not user_id or not otp_created_at:
            messages.error(request, "Session expired. Please register again.")
            return redirect('register')

        # ⏱ OTP expiry (5 minutes = 300 seconds)
        if time() - otp_created_at > 300:
            request.session.flush()
            messages.error(request, "OTP expired. Please register again.")
            return redirect('register')

        # 🔁 Attempt limit (max 3)
        if attempts >= 3:
            request.session.flush()
            messages.error(request, "Too many attempts. Please register again.")
            return redirect('register')

        # ❌ Wrong OTP
        if str(entered_otp) != str(session_otp):
            request.session['otp_attempts'] = attempts + 1
            messages.error(request, "Invalid OTP")
            return render(request, 'users/verify_otp.html')

        # ✅ Correct OTP
        user = User.objects.get(id=user_id)
        user.is_active = True
        user.save()

        request.session.flush()
        messages.success(request, "Account verified. Please login.")
        return redirect('login')

    return render(request, 'users/verify_otp.html')



def login_view(request):
    if request.method == 'POST':
        form=AuthenticationForm(request,data=request.POST)
        if form.is_valid():
            user=form.get_user()
            login(request,user)
            return redirect('/')
    else:
        form=AuthenticationForm()
    return render(request,'users/login.html',{'form':form})

@login_required
def profile(request):
    bookings = Booking.objects.filter(
    user=request.user,
    # showtime__time__gte=now()
).select_related('showtime__movie')


    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        if u_form.is_valid():
            u_form.save()
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)

    return render(
        request,
        'users/profile.html',
        {'u_form': u_form, 'bookings': bookings}
    )


@login_required
def reset_password(request):
    if request.method == 'POST':
        form=PasswordChangeForm(user=request.user,data=request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form=PasswordChangeForm(user=request.user)
    return render(request,'users/reset_password.html',{'form':form})

