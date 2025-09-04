from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render


@login_required
def booking_home(request):
    return render(request, 'booking/index.html')

@user_passes_test(lambda u: u.is_staff)
def booking_resources(request):
    return render(request, 'booking/resources.html')

@user_passes_test(lambda u: u.is_staff)
def booking_policies(request):
    return render(request, 'booking/policies.html')
