from rest_framework import serializers
from tada.models import NegativosJustificacion, POC


class NegativosJustificacionSerializer(serializers.ModelSerializer):
    """
    Complete serializer for NegativosJustificacion.
    """
    duracion_caso = serializers.ReadOnlyField()
    poc_details = serializers.SerializerMethodField()
    created_by_details = serializers.SerializerMethodField()
    
    class Meta:
        model = NegativosJustificacion
        fields = [
            'id',
            'id_ticket',
            'titulo_caso',
            'hora_inicio',
            'hora_fin',
            'justificacion',
            'es_tienda',
            'poc',
            'poc_details',
            'created_by',
            'created_by_details',
            'duracion_caso',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'duracion_caso', 'poc_details', 'created_by', 'created_by_details']
    
    def get_poc_details(self, obj):
        """Return POC details if available."""
        if obj.poc:
            return {
                'id': obj.poc.id,
                'id_poc': obj.poc.id_poc,
                'name': obj.poc.name,
                'city': obj.poc.city,
                'region': obj.poc.region
            }
        return None
    
    def get_created_by_details(self, obj):
        """Return user details if available."""
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'email': obj.created_by.email,
                'first_name': getattr(obj.created_by, 'first_name', ''),
                'last_name': getattr(obj.created_by, 'last_name', '')
            }
        return None


class NegativosJustificacionListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing NegativosJustificacion with summary information.
    """
    duracion_caso = serializers.ReadOnlyField()
    justificacion_preview = serializers.SerializerMethodField()
    poc_name = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()
    
    class Meta:
        model = NegativosJustificacion
        fields = [
            'id',
            'id_ticket',
            'titulo_caso',
            'hora_inicio',
            'hora_fin',
            'justificacion_preview',
            'es_tienda',
            'poc',
            'poc_name',
            'created_by',
            'created_by_email',
            'duracion_caso',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'duracion_caso', 'poc_name', 'created_by', 'created_by_email']
    
    def get_justificacion_preview(self, obj):
        """Return first 100 characters of justification."""
        if obj.justificacion:
            return obj.justificacion[:100] + ('...' if len(obj.justificacion) > 100 else '')
        return None
    
    def get_poc_name(self, obj):
        """Return POC name if available."""
        return obj.poc.name if obj.poc else None
    
    def get_created_by_email(self, obj):
        """Return user email if available."""
        return obj.created_by.email if obj.created_by else None


class NegativosJustificacionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating NegativosJustificacion.
    """
    
    class Meta:
        model = NegativosJustificacion
        fields = [
            'id_ticket',
            'titulo_caso',
            'hora_inicio',
            'hora_fin',
            'justificacion',
            'es_tienda',
            'poc'
        ]
    
    def validate(self, data):
        """
        Validate that hora_fin is after hora_inicio and POC is required if es_tienda is True.
        """
        if data.get('hora_inicio') and data.get('hora_fin'):
            if data['hora_fin'] <= data['hora_inicio']:
                raise serializers.ValidationError({
                    'hora_fin': 'La hora de fin debe ser posterior a la hora de inicio.'
                })
        
        # Validate that if es_tienda is True, poc must be provided
        if data.get('es_tienda') and not data.get('poc'):
            raise serializers.ValidationError({
                'poc': 'El POC es requerido cuando el caso es de tienda.'
            })
        
        # Validate that if es_tienda is False, poc should not be provided
        if not data.get('es_tienda', False) and data.get('poc'):
            raise serializers.ValidationError({
                'poc': 'No se puede asignar un POC si el caso no es de tienda.'
            })
        
        return data


class NegativosJustificacionUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating NegativosJustificacion.
    """
    
    class Meta:
        model = NegativosJustificacion
        fields = [
            'id_ticket',
            'titulo_caso',
            'hora_inicio',
            'hora_fin',
            'justificacion',
            'es_tienda',
            'poc'
        ]
    
    def validate(self, data):
        """
        Validate that hora_fin is after hora_inicio and POC is required if es_tienda is True.
        """
        hora_inicio = data.get('hora_inicio', self.instance.hora_inicio)
        hora_fin = data.get('hora_fin', self.instance.hora_fin)
        
        if hora_inicio and hora_fin:
            if hora_fin <= hora_inicio:
                raise serializers.ValidationError({
                    'hora_fin': 'La hora de fin debe ser posterior a la hora de inicio.'
                })
        
        # Validate that if es_tienda is True, poc must be provided
        es_tienda = data.get('es_tienda', self.instance.es_tienda)
        poc = data.get('poc', self.instance.poc)
        
        if es_tienda and not poc:
            raise serializers.ValidationError({
                'poc': 'El POC es requerido cuando el caso es de tienda.'
            })
        
        # Validate that if es_tienda is False, poc should not be provided
        if not es_tienda and poc:
            raise serializers.ValidationError({
                'poc': 'No se puede asignar un POC si el caso no es de tienda.'
            })
        
        return data


class NegativosJustificacionSimpleSerializer(serializers.ModelSerializer):
    """
    Simple serializer for NegativosJustificacion without nested relationships.
    """
    class Meta:
        model = NegativosJustificacion
        fields = [
            'id',
            'id_ticket',
            'titulo_caso',
            'hora_inicio',
            'hora_fin',
            'justificacion',
            'es_tienda',
            'poc'
        ]
        read_only_fields = ['id']
