from rest_framework.views import APIView
from rest_framework.response import Response

class MeView(APIView):
    def get(self, request):
        u = request.user
        groups = list(u.groups.values_list("name", flat=True))
        return Response({"id": u.id, "username": u.username, "email": u.email, "groups": groups})
