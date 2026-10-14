"""
Sérialiseurs REST Framework pour l'application Accounts.
"""
from rest_framework import serializers
from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    """Sérialiseur complet pour l'utilisateur GreenMove."""
    eco_badge = serializers.CharField(read_only=True)
    co2_saved_kg = serializers.FloatField(read_only=True)
    avatar_url = serializers.CharField(source='get_avatar_url', read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'role',
            'vehicle_type',
            'vehicle_model',
            'available_seats',
            'eco_points',
            'eco_badge',
            'co2_saved_kg',
            'avatar_url',
            'bio',
            'home_address',
            'home_lat',
            'home_lon',
            'work_address',
            'work_lat',
            'work_lon',
            'departure_time_default',
            'gender',
            'is_smoker',
            'ride_preference',
            'profile_verified',
            'reliability_score',
        )
        read_only_fields = ('id', 'eco_points', 'eco_badge', 'co2_saved_kg', 'profile_verified', 'reliability_score')


class RegisterSerializer(serializers.ModelSerializer):
    """Sérialiseur pour l'inscription via l'API REST."""
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = (
            'username',
            'email',
            'password',
            'first_name',
            'last_name',
            'phone_number',
            'role',
            'vehicle_type',
            'vehicle_model',
            'available_seats',
            'home_address',
            'work_address',
            'gender',
            'is_smoker',
            'ride_preference',
        )

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user
