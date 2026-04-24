from django.urls import path
from . import views
urlpatterns=[
    path('',views.movie_list,name='movie_list'),
    path('<int:movie_id>/theaters',views.theater_list,name='theater_list'),
    path('<int:movie_id>/details',views.details,name='details'),
    path('theater/<int:showtime_id>/seats/book/',views.book_seats,name='book_seats'),
    path('showtime/<int:showtime_id>/create-order/', views.create_order,name='create_order'),
    path('verify-payment/',views.verify_payment,name='verify_payment'),
    path('webhook/razorpay/',views.razorpay_webhook, name='razorpay_webhook'),
    path('release-seats/',views.release_seats,name='release_seats'),
    path('payment/success/', views.payment_success, name='payment_success'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
]
    
