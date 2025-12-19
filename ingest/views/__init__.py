from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ingest.serializers import IngestaTextoSerializer


class IngestaTextoView(APIView):
    def post(self, request):
        s = IngestaTextoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        texto = s.validated_data['texto']
        # Placeholder de normalización: devolver texto y tokens simples
        tokens = texto.split()
        return Response({
            'ok': True,
            'texto': texto,
            'tokens': tokens,
            'sugerencia': {
                'tipo': 'gasto' if any(t.startswith('#') for t in tokens) else 'ingreso',
            }
        }, status=status.HTTP_200_OK)

