from rest_framework.response import Response
from rest_framework import status,exceptions
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken, AuthenticationFailed


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = None
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            return Response({
                'status': True,
                'message': 'Successfully Login',
                'token': serializer.validated_data
            }, status=status.HTTP_200_OK)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        except exceptions.ValidationError:
            return Response(
                {
                    'status': False,
                    'message': 'Login Unsuccessfull!',
                    'errors': {kay: str(value[0]) for kay, value in serializer.errors.items()}
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except AuthenticationFailed as e:
            return Response(
                {
                    'status': False,
                    'message': 'Authentication Field!',
                    'error': str(e)
                }, status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'message': 'Something wrongs!',
                    'error': str(e)
                }, status=status.HTTP_401_UNAUTHORIZED
            )


